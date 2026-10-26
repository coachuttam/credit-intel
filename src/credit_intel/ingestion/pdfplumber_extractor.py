"""TextExtractor implementation backed by pdfplumber.

This is the only module that imports pdfplumber or pdfminer (PRD D-01).
"""

from collections.abc import Sequence
from itertools import islice
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError, PDFPasswordIncorrect
from pdfplumber.page import Page

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PageImageCoverage, PageText, PageWords, PdfInspection, Word

_ENCRYPTION_ERRORS = (PDFPasswordIncorrect, PDFEncryptionError)

# Pinned explicitly, equal to the values extract_text uses, so a library default
# change cannot silently move the word grouping away from the page text (AC-OD1-25).
WORD_X_TOLERANCE = 3
WORD_Y_TOLERANCE = 3


def _is_encryption_error(exc: BaseException) -> bool:
    """True if ``exc`` or anything it wraps is a pdfminer encryption error.

    pdfplumber wraps pdfminer errors in ``PdfminerException``, so the
    original error may be in the exception chain or in ``args``.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, _ENCRYPTION_ERRORS):
            return True
        pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)
        pending.extend(a for a in current.args if isinstance(a, BaseException))
    return False


# The input is untrusted, so any failure inside the PDF library while
# *parsing* it means the file cannot be processed. Each try block below wraps
# exactly one parsing call; everything else (e.g. our own attribute access)
# is outside, so programming errors are not disguised as corrupt input. The
# original exception is kept as __cause__.


def _open(path: Path) -> pdfplumber.PDF:
    try:
        return pdfplumber.open(path)
    except Exception as exc:
        code = ErrorCode.ENCRYPTED if _is_encryption_error(exc) else ErrorCode.CORRUPT
        raise IngestionError(code) from exc


def _load_pages(pdf: pdfplumber.PDF) -> list[Page]:
    try:
        return list(pdf.pages)  # parses the page tree
    except Exception as exc:
        raise IngestionError(ErrorCode.CORRUPT) from exc


def _page_labels(doc: PDFDocument, page_count: int) -> list[str | None]:
    """The document's page-label metadata, or ``None`` for every page.

    Labels are optional (FR-002.2): a missing or unreadable label tree
    never rejects the document.
    """
    try:
        # get_page_labels() yields indefinitely; take one per page.
        labels = list(islice(doc.get_page_labels(), page_count))
    except Exception:  # PDFNoPageLabels, or a malformed label tree
        return [None] * page_count
    return labels + [None] * (page_count - len(labels))


def union_area(rectangles: Sequence[tuple[float, float, float, float]]) -> float:
    """The area covered by ``(x0, top, x1, bottom)`` rectangles, overlaps counted once."""
    rects = sorted(set(rectangles))
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        spans = sorted((r[1], r[3]) for r in rects if r[0] <= left and r[2] >= right)
        covered, end = 0.0, float("-inf")
        for top, bottom in spans:
            top = max(top, end)
            if bottom > top:
                covered += bottom - top
                end = bottom
        total += covered * (right - left)
    return total


class PdfplumberExtractor:
    def inspect(self, path: Path) -> PdfInspection:
        with _open(path) as pdf:
            # Encrypted PDFs with an empty user password open without
            # error; the trailer's /Encrypt entry is the only signal.
            is_encrypted = pdf.doc.encryption is not None
            page_count = len(_load_pages(pdf))
        return PdfInspection(page_count=page_count, is_encrypted=is_encrypted)

    def extract_pages(self, path: Path) -> list[PageText]:
        with _open(path) as pdf:
            pages = _load_pages(pdf)
            labels = _page_labels(pdf.doc, len(pages))
            result = []
            for page_number, (page, label) in enumerate(zip(pages, labels), start=1):
                try:
                    text = page.extract_text()
                except Exception as exc:
                    raise IngestionError(ErrorCode.CORRUPT) from exc
                result.append(PageText(page_number=page_number, text=text or "", page_label=label))
        return result

    def extract_words(self, path: Path, page_numbers: Sequence[int]) -> list[PageWords]:
        requested = list(page_numbers)
        if not requested or len(set(requested)) != len(requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        with _open(path) as pdf:
            pages = _load_pages(pdf)
            if any(isinstance(n, bool) or not isinstance(n, int) for n in requested) or not all(
                1 <= n <= len(pages) for n in requested
            ):
                raise IngestionError(ErrorCode.PAGE_RANGE)
            result = []
            for page_number in sorted(requested):
                page = pages[page_number - 1]
                try:
                    raw_words = page.extract_words(
                        x_tolerance=WORD_X_TOLERANCE,
                        y_tolerance=WORD_Y_TOLERANCE,
                        keep_blank_chars=False,
                        use_text_flow=False,
                    )
                except Exception as exc:
                    raise IngestionError(ErrorCode.CORRUPT) from exc
                words = sorted(
                    (
                        Word(
                            text=w["text"],
                            x0=float(w["x0"]),
                            x1=float(w["x1"]),
                            top=float(w["top"]),
                            bottom=float(w["bottom"]),
                        )
                        for w in raw_words
                    ),
                    key=lambda w: (w.top, w.x0, w.text),
                )
                result.append(
                    PageWords(
                        page_number=page_number,
                        width=float(page.width),
                        height=float(page.height),
                        rotation=int(page.rotation) % 360,
                        words=tuple(words),
                    )
                )
        return result

    def image_coverage(self, path: Path) -> list[PageImageCoverage]:
        with _open(path) as pdf:
            result = []
            for page_number, page in enumerate(_load_pages(pdf), start=1):
                width, height = float(page.width), float(page.height)
                try:
                    images = page.images
                except Exception as exc:
                    raise IngestionError(ErrorCode.CORRUPT) from exc
                clipped = [
                    (
                        max(float(i["x0"]), 0.0),
                        max(float(i["top"]), 0.0),
                        min(float(i["x1"]), width),
                        min(float(i["bottom"]), height),
                    )
                    for i in images
                ]
                area = width * height
                share = union_area(clipped) / area if area > 0 else 0.0
                result.append(PageImageCoverage(page_number=page_number, area_share=share, native_dpi=_native_dpi(images)))
        return result


def _native_dpi(images: list[dict]) -> int | None:
    """Pixels per inch of the largest image (by displayed area) across its displayed width; ``None`` if it cannot be read."""
    best: tuple[float, int] | None = None
    for image in images:
        try:
            width_pt = float(image["x1"]) - float(image["x0"])
            height_pt = float(image["bottom"]) - float(image["top"])
            pixels = int(image["srcsize"][0])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if width_pt <= 0 or height_pt <= 0 or pixels <= 0:
            continue
        if best is None or width_pt * height_pt > best[0]:
            best = (width_pt * height_pt, max(1, round(pixels * 72.0 / width_pt)))
    return None if best is None else best[1]
