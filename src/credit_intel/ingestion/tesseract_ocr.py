"""OcrExtractor implementation backed by the Tesseract command (PRD D-15, FR-001A).

This is the only module that runs Tesseract. Pages are rendered in memory at the requested DPI with pypdfium2 (already installed
as pdfplumber's renderer), passed to ``tesseract`` on its standard input as PNG, and read back as TSV: nothing is written to disk
(FR-001A.6). English only (FR-001A.9). The time limit covers the whole call, not each page, so a long range cannot multiply it.
No error carries document text.

The page rendering (pypdfium2, a library that parses the untrusted file) can run in the parse worker, under the run's parse limits
(PRD SEC-12 step 2, v0.4.50): ``use_renderer`` gives the engine a function that renders one page there. Without one, as in the
suite's engine tests, the pages are rendered in this process. The PNG goes from the worker to this process in memory, never
through a file (FR-001A.6).

The engine's own run can be watched too (PRD SEC-12 step 3, v0.4.53): ``use_runner`` gives the page read a function that runs the
command with its resident memory polled against the parse memory limit (``SandboxedExtractor.run_supervised``). Without one, as in
the suite's engine tests, the command is run directly. The two availability checks are always run directly: they read no page.
"""

import io
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from credit_intel.config import OCR_LANGUAGE
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import OcrPage, OcrWord

COMMAND = "tesseract"
_POINTS_PER_INCH = 72.0
_VERSION = re.compile(r"tesseract\s+(\S+)", re.IGNORECASE)
# Page segmentation mode 6, "a single uniform block of text". Tesseract's default mode splits a table into blocks, so a row's label
# and its figures come out on different lines; on the synthetic scans of docs/d15_tesseract_findings.md mode 6 kept 220 of 228 rows whole
# against 36 for the default.
PAGE_SEGMENTATION_MODE = "6"
_TSV_COLUMNS = 12
_WORD_LEVEL = "5"
# One thread keeps the reading the same on every machine and in every run.
_ENVIRONMENT = {"OMP_THREAD_LIMIT": "1"}


# One rendered page: PNG bytes, width and height in points. ``render(path, page, dpi, timeout_seconds=...)``.
PageRenderer = Callable[..., tuple[bytes, float, float]]
# ``run(command, stdin, env=..., timeout_seconds=...)`` returns the finished process (``returncode``, ``stdout``).
EngineRunner = Callable[..., subprocess.CompletedProcess[bytes]]


def open_document(path: Path):
    """The pypdfium2 document for ``path``; ``E-INPUT-OCR-FAILED`` if it cannot be opened."""
    import pypdfium2 as pdfium

    try:
        return pdfium.PdfDocument(str(path))
    except Exception:
        raise IngestionError(ErrorCode.OCR_FAILED) from None


def render_page_png(document, number: int, dpi: int) -> tuple[bytes, float, float]:
    """Render page ``number`` of ``document`` at ``dpi`` in memory: ``(png bytes, width in points, height in points)``."""
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(document):
        raise IngestionError(ErrorCode.PAGE_RANGE)
    try:
        page = document[number - 1]
        width, height = page.get_size()
        image = page.render(scale=dpi / _POINTS_PER_INCH).to_pil().convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except Exception:
        raise IngestionError(ErrorCode.OCR_FAILED) from None
    return buffer.getvalue(), float(width), float(height)


class TesseractExtractor:
    """Reads pages with the ``tesseract`` command. ``command`` can name another executable (a test stub)."""

    name = "tesseract"

    def __init__(self, command: str = COMMAND) -> None:
        self._command = command
        self._version: str | None = None
        self._renderer: PageRenderer | None = None
        self._runner: EngineRunner | None = None

    def use_renderer(self, renderer: PageRenderer | None) -> None:
        """Render pages with ``renderer`` (the parse worker) instead of in this process; ``None`` goes back to this process."""
        self._renderer = renderer

    @property
    def version(self) -> str:
        """The engine's version, read once from ``tesseract --version``; ``E-INPUT-OCR-UNAVAILABLE`` if it cannot be run."""
        if self._version is None:
            self._version = self._check_available()
        return self._version

    def use_runner(self, runner: EngineRunner | None) -> None:
        """Run the engine on a page with ``runner`` (watched for memory) instead of directly; ``None`` goes back to direct."""
        self._runner = runner

    def _run(self, arguments: list[str], *, stdin: bytes | None = None, timeout: float, watched: bool = False) -> subprocess.CompletedProcess[bytes]:
        import os

        if watched and self._runner is not None:
            return self._runner([self._command, *arguments], stdin or b"", env={**os.environ, **_ENVIRONMENT}, timeout_seconds=timeout)

        try:
            return subprocess.run(
                [self._command, *arguments], input=stdin, capture_output=True, timeout=timeout, check=False,
                env={**os.environ, **_ENVIRONMENT},
            )  # fmt: skip
        except FileNotFoundError:
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE) from None
        except PermissionError:
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE) from None
        except subprocess.TimeoutExpired:
            raise IngestionError(ErrorCode.OCR_FAILED) from None
        except OSError:
            raise IngestionError(ErrorCode.OCR_FAILED) from None

    def _check_available(self) -> str:
        done = self._run(["--version"], timeout=30)
        text = (done.stdout + done.stderr).decode("utf-8", "replace")
        found = _VERSION.search(text)
        if done.returncode != 0 or found is None:
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE)
        languages = self._run(["--list-langs"], timeout=30)
        if languages.returncode != 0 or OCR_LANGUAGE not in languages.stdout.decode("utf-8", "replace").split():
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE)  # the English data is not installed
        return found.group(1)

    def ocr_pages(self, path: Path, page_numbers: Sequence[int], *, dpi: Mapping[int, int], timeout_seconds: float) -> list[OcrPage]:
        requested = list(page_numbers)
        self.version  # noqa: B018  (unavailable is reported before a bad page range, as the contract says)
        if not requested or len(set(requested)) != len(requested) or any(n not in dpi for n in requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        deadline = time.monotonic() + timeout_seconds
        result = []
        for number, (png, width, height) in zip(sorted(requested), self._pages(path, sorted(requested), dpi, deadline)):
            page_dpi = dpi[number]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IngestionError(ErrorCode.OCR_FAILED)
            done = self._run(["stdin", "stdout", "-l", OCR_LANGUAGE, "--dpi", str(page_dpi), "--psm", PAGE_SEGMENTATION_MODE, "tsv"], stdin=png, timeout=remaining, watched=True)
            if done.returncode != 0:
                raise IngestionError(ErrorCode.OCR_FAILED)
            result.append(_page_from_tsv(number, done.stdout.decode("utf-8", "replace"), width, height, page_dpi))
        return result

    def _pages(self, path: Path, numbers: list[int], dpi: Mapping[int, int], deadline: float):
        """Yield ``(png, width, height)`` for each page, rendered by the worker if one was given, else in this process."""
        if self._renderer is None:
            yield from self._render(path, numbers, dpi)
            return
        for number in numbers:  # each page in its own worker, bounded by the OCR call's remaining time as well as the parse limits
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IngestionError(ErrorCode.OCR_FAILED)
            yield self._renderer(path, number, dpi[number], timeout_seconds=remaining)

    @staticmethod
    def _render(path: Path, numbers: list[int], dpi: Mapping[int, int]):
        """Yield ``(png bytes, width in points, height in points)`` for each page, rendered in memory at its ``dpi``."""
        document = open_document(path)
        try:
            if any(isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= len(document) for n in numbers):
                raise IngestionError(ErrorCode.PAGE_RANGE)
            for number in numbers:
                yield render_page_png(document, number, dpi[number])
        finally:
            document.close()


def _page_from_tsv(number: int, tsv: str, width: float, height: float, dpi: int) -> OcrPage:
    """An ``OcrPage`` from Tesseract's TSV: word rows (level 5) with a confidence of 0 or more, boxes in points."""
    scale = _POINTS_PER_INCH / dpi
    lines: dict[tuple[str, str, str], list[OcrWord]] = {}
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < _TSV_COLUMNS or cells[0] != _WORD_LEVEL:
            continue
        text = "\t".join(cells[11:]).strip()
        try:
            left, top, w, h, confidence = int(cells[6]), int(cells[7]), int(cells[8]), int(cells[9]), float(cells[10])
        except ValueError:
            raise IngestionError(ErrorCode.OCR_FAILED) from None
        if not text or confidence < 0:
            continue  # a box with no word, or a word the engine gave no confidence
        word = OcrWord(text, left * scale, (left + w) * scale, top * scale, (top + h) * scale, confidence)
        lines.setdefault((cells[2], cells[3], cells[4]), []).append(word)
    ordered = [sorted(words, key=lambda x: x.x0) for _, words in sorted(lines.items(), key=lambda item: tuple(int(k) for k in item[0]))]
    text = "\n".join(" ".join(word.text for word in words) for words in ordered)
    words = tuple(sorted((w for line in ordered for w in line), key=lambda w: (w.top, w.x0, w.text)))
    return OcrPage(page_number=number, width=width, height=height, text=text, words=words, dpi=dpi)
