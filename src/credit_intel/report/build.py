"""Making the report for a run, so that it can never fail the run (PRD FR-015 criteria 2, 7 and 8, v0.4.56).

``make_report(memo)`` returns a ``ReportOutcome`` and **never raises**: the memo is the authoritative output, and the PDF is a
presentation layer. The PDF is built and checked in a worker process under a fixed time limit (``RENDER_TIME_LIMIT``, a constant, not a
setting), so a stuck renderer ends as ``timeout`` and the run goes on. If the report is not written, a warning with a fixed reason word
and nothing from the document goes to the log, and the outcome says why, for the manifest. No unchecked or partial PDF is ever returned.
"""

import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata

from credit_intel.report.errors import REASONS

logger = logging.getLogger("credit_intel.report")
RENDER_TIME_LIMIT = 120.0  # seconds; FR-015 criterion 7
WORKER_COMMAND = (sys.executable, "-I", "-m", "credit_intel.report.worker")
PACKAGES = ("reportlab", "markdown-it-py")  # what builds the report; recorded in the manifest


@dataclass(frozen=True)
class ReportOutcome:
    """What happened to the report: ``written`` (with the bytes), ``failed`` (with a reason from ``REASONS``) or ``skipped``."""

    status: str
    pdf: bytes | None = None
    reason: str | None = None

    @classmethod
    def skipped(cls) -> "ReportOutcome":
        return cls("skipped")

    def manifest_entry(self) -> dict:
        """The ``report`` entry of ``manifest.json`` (FR-015 criterion 8)."""
        if self.status == "written" and self.pdf is not None:
            versions = {}
            for name in PACKAGES:
                try:
                    versions[name] = metadata.version(name)
                except metadata.PackageNotFoundError:
                    versions[name] = None
            return {"status": "written", "file": "report.pdf", "size": len(self.pdf), "sha256": hashlib.sha256(self.pdf).hexdigest(), "packages": versions}
        if self.status == "failed":
            return {"status": "failed", "reason": self.reason}
        return {"status": "skipped"}


def _failed(reason: str) -> ReportOutcome:
    assert reason in REASONS
    logger.warning("report not written (%s); memo.md is complete", reason)  # a fixed text: no document text, no path
    return ReportOutcome("failed", reason=reason)


def _stop(process: subprocess.Popen) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - no process groups on this platform
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _run_worker(memo: bytes, command: Sequence[str], time_limit: float) -> ReportOutcome:
    try:
        process = subprocess.Popen(  # noqa: S603 - a fixed command; the memo goes on standard input
            list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=hasattr(os, "killpg"),
        )  # fmt: skip
    except OSError:
        return _failed("render_error")
    try:
        out, _ = process.communicate(memo, timeout=time_limit)
    except subprocess.TimeoutExpired:
        _stop(process)
        process.communicate()
        return _failed("timeout")
    finally:
        if process.poll() is None:
            _stop(process)
            process.wait()
    if process.returncode != 0:
        return _failed("render_error")
    head, _, body = out.partition(b"\n")
    if head == b"OK" and body.startswith(b"%PDF-") and body.rstrip().endswith(b"%%EOF"):
        return ReportOutcome("written", pdf=body)
    reason = head[5:].decode("ascii", "replace") if head.startswith(b"FAIL ") else "render_error"
    return _failed(reason if reason in REASONS else "render_error")


def make_report(memo: str, results: dict | None = None, *, time_limit: float = RENDER_TIME_LIMIT, command: Sequence[str] = WORKER_COMMAND) -> ReportOutcome:
    """The report for ``memo``, with the charts of ``results`` if given: built and checked in a worker under ``time_limit``. Never raises."""
    try:
        memo.encode("utf-8")  # text that cannot be encoded (a lone surrogate) cannot be sent, and is not a report
        data = json.dumps({"memo": memo, "results": results}).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError):
        return _failed("render_error")
    try:
        return _run_worker(data, command, time_limit)
    except Exception:
        return _failed("render_error")
