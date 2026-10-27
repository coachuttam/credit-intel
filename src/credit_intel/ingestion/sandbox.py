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

Windows is not tested: the process is started in its own session where the system supports it, and the resident-memory read uses ``ps``.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from credit_intel.config import ParseLimits
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PageImageCoverage, PageText, PageWords, PdfInspection
from credit_intel.ingestion.parse_worker import from_jsonable

POLL_SECONDS = 0.1
WORKER_COMMAND = (sys.executable, "-I", "-m", "credit_intel.ingestion.parse_worker")  # -I: no user site or environment-chosen paths
TIME_DETAIL = "time limit; raise ingestion.parse_timeout_seconds"
MEMORY_DETAIL = "memory limit; raise ingestion.parse_memory_mb"


def resident_mb(pid: int) -> float | None:
    """The resident memory of ``pid`` in MB, or ``None`` if it cannot be read (the process has gone)."""
    try:
        done = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5, check=False)
        return int(done.stdout.strip()) / 1024 if done.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


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

    # --- one operation in a worker -------------------------------------------------------------------------

    def _run(self, operation: str, path: Path, argument: str | None = None):
        if self._deadline is None:
            self._deadline = self._clock() + self._limits.timeout_seconds
        if self._clock() >= self._deadline:
            raise IngestionError(ErrorCode.PARSE_LIMIT, detail=TIME_DETAIL)
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

    def _watch(self, process: subprocess.Popen) -> None:
        while process.poll() is None:
            if self._deadline is not None and self._clock() >= self._deadline:
                _kill(process)
                raise IngestionError(ErrorCode.PARSE_LIMIT, detail=TIME_DETAIL)
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
