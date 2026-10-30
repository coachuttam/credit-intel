"""The command line: ``credit-intel <pdf_path> [options]`` (PRD FR-014, FR-011.2, FR-011.4; Phase 5 step 5k).

One command runs one document through the whole pipeline and writes ``<output_dir>/<run_id>/`` with
``memo.md``, ``results.json`` and ``manifest.json``.

* Success: exit 0; the run directory path is the only line on standard output.
* A catalogued failure: ``E-...: message and action`` on standard error and the catalogue's exit code. If the run
  got far enough to be recorded, a run folder holding only ``manifest.json`` (state ``failed``, its stage and code)
  is also written on a best-effort basis, and named on standard error. A failure before ``received`` (bad
  settings, bad profile, missing file) has no recorded state and so no manifest.
* A bad argument: exit 2 (argparse). A refusal to send a document (``send_rule``) is the catalogued failure ``E-INPUT-SEND-REFUSED``: exit 3,
  a fixed reason word, nothing written.
* Anything else: exit 1; the message gives the run ID and never a stack trace (FR-011.4).

Standard output and standard error carry only those lines and the INFO stage log, which has counts and
identifiers only (FR-012.3). The model provider is built on first use, so a run served wholly from the response
cache needs no API key, and a missing key fails in the extraction stage as the catalogue says.
"""

import argparse
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO, Any

from credit_intel.config import DEFAULT_SETTINGS_PATH
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH
from credit_intel.export.manifest import run_id
from credit_intel.ingestion.errors import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, IngestionError, exit_code
from credit_intel.ingestion.ocr_engine import default_ocr_extractor
from credit_intel.llm.factory import build_provider
from credit_intel.memo.trace import MemoCheckFailed
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.factory import ClassifierFactory, build_classifier
from credit_intel.service import (
    DEFAULT_OUTPUT_DIR,
    ExtractorFactory,
    OcrFactory,
    ProviderFactory,
    RunProgress,
    RunRequest,
    RunServices,
    execute_run,
    record_failure,
)
from credit_intel.states import Clock, Recorder, utc_now

BASES = [StatementBasis.CONSOLIDATED.value, StatementBasis.STANDALONE.value]  # "unknown" is a finding, never a request
ENV_LOG_LEVEL = "CREDIT_INTEL_LOG_LEVEL"
EXIT_INTERRUPTED = 130
logger = logging.getLogger("credit_intel.cli")


class _Parser(argparse.ArgumentParser):
    """argparse, writing its messages to the stream the command was given instead of ``sys.stderr``."""

    def __init__(self, stream: IO[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stream = stream

    def _print_message(self, message: str, file: IO[str] | None = None) -> None:
        if message:
            self._stream.write(message)


def build_parser(stream: IO[str]) -> argparse.ArgumentParser:
    p = _Parser(stream, prog="credit-intel", description="Draft a credit memo from a financial-statements PDF. A draft for human review, not a credit decision.")
    p.add_argument("pdf_path", type=Path, help="the PDF to analyse")
    p.add_argument("--pages", metavar="RANGE", help="statement pages, such as 110-115,120 (replaces the locator)")
    p.add_argument("--basis", choices=BASES, default=StatementBasis.CONSOLIDATED.value, help="statement basis (default: consolidated)")
    p.add_argument("--assert-basis", choices=BASES, metavar="BASIS",
                   help="state the basis (consolidated or standalone) of the pages of --pages whose titles name none; requires --pages")  # fmt: skip
    p.add_argument("--profile", type=Path, metavar="PROFILE_JSON", help="analyst-provided borrower profile (JSON)")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, metavar="DIR", help="where run folders are written (default: runs)")
    p.add_argument("--no-report", action="store_true", help="skip the PDF report (report.pdf is built by default; a failure to build it never fails the run)")
    p.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML", help="settings file (default: config/settings.toml)")
    p.add_argument("--ocr", action="store_true",
                   help="read image-only pages of --pages by OCR (PRD v0.4.44; needs the [ocr] settings and an OCR engine; a scanned document needs --pages)")  # fmt: skip
    p.add_argument("--confirm-public-document", action="store_true",
                   help="confirm that a document not on the assignment record is public, so its statement pages may be sent to the hosted API")  # fmt: skip
    return p


def _level(name: str) -> int:
    level = logging.getLevelName(name.strip().upper())
    return level if isinstance(level, int) else logging.INFO


def _request(args: argparse.Namespace) -> RunRequest:
    return RunRequest(
        pdf_path=args.pdf_path, basis=StatementBasis(args.basis), pages=args.pages,
        assert_basis=StatementBasis(args.assert_basis) if args.assert_basis else None, profile=args.profile,
        output_dir=args.output_dir, config=args.config, ocr=args.ocr, confirm_public_document=args.confirm_public_document,
        no_report=args.no_report,
    )  # fmt: skip


def _report_record(path: Path | None, err: IO[str]) -> None:
    if path is not None:
        print(f"Run record: {path}", file=err)


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_factory: ProviderFactory = build_provider,
    clock: Clock = utc_now,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    env: Mapping[str, str] | None = None,
    classifier_factory: ClassifierFactory = build_classifier,
    ocr_factory: OcrFactory = default_ocr_extractor,
    extractor_factory: ExtractorFactory | None = None,
) -> int:
    """Run the command and return its exit code. The streams, clock, environment and the provider, classifier and OCR engine factories can be replaced for tests."""
    out, err = stdout or sys.stdout, stderr or sys.stderr
    environment = os.environ if env is None else env
    try:
        parser = build_parser(err)
        args = parser.parse_args(argv)
        if args.assert_basis and not args.pages:
            parser.error("--assert-basis requires --pages")  # exit code 2 (FR-014.4)
    except SystemExit as stop:  # argparse has printed its message; its code is 2 for a bad argument and 0 for --help
        return stop.code if isinstance(stop.code, int) else EXIT_USAGE

    handler = logging.StreamHandler(err)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    package_logger = logging.getLogger("credit_intel")
    previous = package_logger.level
    handler.setLevel(_level(environment.get(ENV_LOG_LEVEL, "INFO")))
    package_logger.addHandler(handler)
    package_logger.setLevel(handler.level)
    request = _request(args)
    progress = RunProgress(Recorder(clock))
    services = RunServices(provider_factory, classifier_factory, ocr_factory, extractor_factory, assignments)
    try:
        path = execute_run(request, progress, services, environment, lambda line: print(line, file=err))
        print(path, file=out)
        return EXIT_OK
    except IngestionError as error:
        print(str(error), file=err)
        _report_record(record_failure(request, progress, error), err)
        return exit_code(error)
    except KeyboardInterrupt:
        print("Interrupted.", file=err)
        return EXIT_INTERRUPTED
    except Exception as error:
        logger.debug("internal error", exc_info=True)  # the trace is for DEBUG only (FR-011.4)
        _report_record(record_failure(request, progress, error), err)
        identifier = run_id(progress.recorder.events[0].at, progress.sha256) if progress.recorder.events and progress.sha256 else "unknown"
        # A memo that failed its check before export (FR-010 criterion 5) is reported with the number of problems and never their text.
        detail = f" The memo failed its traceability check ({error.count} {'problem' if error.count == 1 else 'problems'})." if isinstance(error, MemoCheckFailed) else ""
        print(f"Internal error. Run ID: {identifier}.{detail} Re-run, and report it if it persists.", file=err)
        return EXIT_INTERNAL
    finally:
        package_logger.removeHandler(handler)
        package_logger.setLevel(previous)


def run() -> None:
    """The console entry point."""
    raise SystemExit(main())
