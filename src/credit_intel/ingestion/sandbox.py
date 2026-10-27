"""The parent side of the parse worker (PRD SEC-12, FR-001 criterion 10; OD-6 option (b), v0.4.50).

``SandboxedExtractor`` implements the same interfaces as ``PdfplumberExtractor`` (``TextExtractor``, ``WordExtractor``,
``ImageCoverageExtractor``), so no other module changes. Each operation runs in a worker process (``parse_worker``) that the parent
watches:

* **One time budget for all parsing in the run.** It starts at the first operation and is shared by every operation; an
  operation that would start after it has run out, or that is still running when it does, ends the run.
* **Memory is polled, not set.** The parent reads the worker's resident memory every ``POLL_SECONDS`` and stops it past the limit,
  because an operating-system limit cannot be set on every platform (it cannot on macOS). A burst between two samples can pass the
  limit briefly: the limit is a bound, not an exact figure.
* **A stop is final.** The worker's process group is killed and reaped; no orphan is left. A limit stop is ``E-INPUT-PARSE-LIMIT``
  naming the limit and the setting; a worker that fails or crashes is ``E-INPUT-CORRUPT``; a catalogued code the worker reports
  (for example ``E-INPUT-ENCRYPTED``) is re-raised as it is. No error, log or temporary file holds document text beyond the result file,
  which is removed at once.

**Rendering for OCR (step 2).** ``render_page`` runs one page's rendering in a worker too, with the same budget, memory watch and kill. The PNG
comes back on the worker's standard output, drained by a thread, so it is held in memory only (FR-001A.6). It can also carry a time
limit of its own (the OCR call's remaining time): passing that is ``E-INPUT-OCR-FAILED``, as before; passing the parse budget or the
memory limit is ``E-INPUT-PARSE-LIMIT``; a render worker that fails or crashes is ``E-INPUT-OCR-FAILED``.

Windows is not tested: the process is started in its own session where the system supports it, and the resident-memory read uses ``ps``.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from credit_intel.config import ParseLimits
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PageImageCoverage, PageText, PageWords, PdfInspection
from credit_intel.ingestion.parse_worker import from_jsonable

POLL_SECONDS = 0.1
WORKER_COMMAND = (sys.executable, "-I", "-m", "credit_intel.ingestion.parse_worker")  # -I: no user site or environment-chosen paths
MAX_RENDER_BYTES = 512 * 1024 * 1024  # a page image bigger than this is treated as a memory-limit breach
TIME_DETAIL = "time limit; raise ingestion.parse_timeout_seconds"
MEMORY_DETAIL = "memory limit; raise ingestion.parse_memory_mb"


def resident_mb(pid: int) -> float | None:
    """The resident memory of ``pid`` in MB, or ``None`` if it cannot be read (the process has gone)."""
    try:
        done = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5, check=False)
        return int(done.stdout.strip()) / 1024 if done.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class _Drain(threading.Thread):
    """Reads a worker's standard output into memory until it closes, giving up (and saying so) past ``MAX_RENDER_BYTES``."""

    def __init__(self, stream, limit: int | None = None) -> None:
        super().__init__(daemon=True)
        self._stream, self._limit = stream, MAX_RENDER_BYTES if limit is None else limit
        self.data = bytearray()
        self.exceeded = False

    def run(self) -> None:
        try:
            while chunk := self._stream.read1(1 << 20):  # read1: what is there now, not a full block
                self.data += chunk
                if len(self.data) > self._limit:
                    self.exceeded = True
                    return
        except (OSError, ValueError):
            return


def _kill(process: subprocess.Popen) -> None:
    """Stop the worker and anything it started, and reap it."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - no process groups on this platform
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - a killed process is reaped at once
        process.kill()


class SandboxedExtractor:
    def __init__(
        self,
        limits: ParseLimits,
        *,
        command: Sequence[str] = WORKER_COMMAND,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        memory_reader: Callable[[int], float | None] = resident_mb,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._limits = limits
        self._command = tuple(command)
        self._clock = clock
        self._sleep = sleep
        self._memory = memory_reader
        self._poll = poll_seconds
        self._deadline: float | None = None  # set at the first operation: one budget for the run

    # --- the interfaces --------------------------------------------------------------------------------------

    def inspect(self, path: Path) -> PdfInspection:
        return self._run("inspect", path)

    def extract_pages(self, path: Path) -> list[PageText]:
        return self._run("extract_pages", path)

    def extract_words(self, path: Path, page_numbers: Sequence[int]) -> list[PageWords]:
        return self._run("extract_words", path, json.dumps(list(page_numbers)))

    def image_coverage(self, path: Path) -> list[PageImageCoverage]:
        return self._run("image_coverage", path)

    def render_page(self, path: Path, page: int, dpi: int, *, timeout_seconds: float | None = None) -> tuple[bytes, float, float]:
        """Render one page for OCR in a worker: ``(png bytes, width in points, height in points)`` (PRD SEC-12 step 2)."""
        self._start_budget()
        command = [*self._command, "render_page", str(path), "-", str(self._limits.memory_mb), json.dumps({"page": page, "dpi": dpi})]
        own = None if timeout_seconds is None else self._clock() + timeout_seconds
        try:
            process = subprocess.Popen(  # noqa: S603 - a fixed command; the path is an argument, never a shell string
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=hasattr(os, "killpg"),
            )  # fmt: skip
        except OSError as exc:
            raise IngestionError(ErrorCode.OCR_FAILED) from exc
        drain = _Drain(process.stdout)
        drain.start()
        try:
            self._watch(process, own, drain)
        finally:
            if process.poll() is None:
                _kill(process)
            drain.join(timeout=10)
            process.stdout.close()
        return self._render_result(process.returncode, bytes(drain.data), drain.exceeded)

    @staticmethod
    def _render_result(returncode: int | None, data: bytes, exceeded: bool) -> tuple[bytes, float, float]:
        if exceeded:
            raise IngestionError(ErrorCode.PARSE_LIMIT, detail=MEMORY_DETAIL)
        if returncode != 0:
            raise IngestionError(ErrorCode.OCR_FAILED)
        try:
            line, _, png = data.partition(b"\n")
            header = json.loads(line)
            if header.get("memory"):
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=MEMORY_DETAIL)
            if not header["ok"]:
                raise IngestionError(ErrorCode(header["code"]))
            if not png:
                raise ValueError("no image")
            return png, float(header["width"]), float(header["height"])
        except IngestionError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise IngestionError(ErrorCode.OCR_FAILED) from exc

    def _start_budget(self) -> None:
        if self._deadline is None:
            self._deadline = self._clock() + self._limits.timeout_seconds
        if self._clock() >= self._deadline:
            raise IngestionError(ErrorCode.PARSE_LIMIT, detail=TIME_DETAIL)

    # --- one operation in a worker -------------------------------------------------------------------------

    def _run(self, operation: str, path: Path, argument: str | None = None):
        self._start_budget()
        with tempfile.TemporaryDirectory(prefix="credit-intel-parse-") as scratch:
            output = Path(scratch) / "result.json"
            command = [*self._command, operation, str(path), str(output), str(self._limits.memory_mb)]
            if argument is not None:
                command.append(argument)
            try:
                process = subprocess.Popen(  # noqa: S603 - a fixed command; the path is an argument, never a shell string
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=hasattr(os, "killpg"),
                )  # fmt: skip
            except OSError as exc:
                raise IngestionError(ErrorCode.CORRUPT) from exc
            try:
                self._watch(process)
            finally:
                if process.poll() is None:
                    _kill(process)
            return self._result(operation, process.returncode, output)

    def _watch(self, process: subprocess.Popen, own_deadline: float | None = None, drain: _Drain | None = None) -> None:
        while process.poll() is None:
            if self._deadline is not None and self._clock() >= self._deadline:
                _kill(process)
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=TIME_DETAIL)
            if own_deadline is not None and self._clock() >= own_deadline:
                _kill(process)
                raise IngestionError(ErrorCode.OCR_FAILED)  # the OCR call's own time limit, not the parse budget
            if drain is not None and drain.exceeded:
                _kill(process)
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=MEMORY_DETAIL)
            used = self._memory(process.pid)
            if used is not None and used > self._limits.memory_mb:
                _kill(process)
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=MEMORY_DETAIL)
            self._sleep(self._poll)

    @staticmethod
    def _result(operation: str, returncode: int | None, output: Path):
        if returncode != 0:
            raise IngestionError(ErrorCode.CORRUPT)
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
            if payload.get("memory"):
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=MEMORY_DETAIL)  # the worker's own backstop fired
            if not payload["ok"]:
                raise IngestionError(ErrorCode(payload["code"]))
            return from_jsonable(operation, payload["result"])
        except IngestionError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:  # no output, or output that is not the contract
            raise IngestionError(ErrorCode.CORRUPT) from exc
