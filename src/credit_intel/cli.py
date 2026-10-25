"""The command line: ``credit-intel <pdf_path> [options]`` (PRD FR-014, FR-011.2, FR-011.4; Phase 5 step 5k).

One command runs one document through the whole pipeline and writes ``<output_dir>/<run_id>/`` with
``memo.md``, ``results.json`` and ``manifest.json``.

* Success: exit 0; the run directory path is the only line on standard output.
* A catalogued failure: ``E-...: message and action`` on standard error and the catalogue's exit code. If the run
  got far enough to be recorded, a run folder holding only ``manifest.json`` (state ``failed``, its stage and code)
  is also written on a best-effort basis, and named on standard error. A failure before ``received`` (bad
  settings, bad profile, missing file) has no recorded state and so no manifest.
* A refusal to send a document (``send_rule``) or a bad argument: exit 2. Argument errors are argparse's.
* Anything else: exit 1; the message gives the run ID and never a stack trace (FR-011.4).

Standard output and standard error carry only those lines and the INFO stage log, which has counts and
identifiers only (FR-012.3). The model provider is built on first use, so a run served wholly from the response
cache needs no API key, and a missing key fails in the extraction stage as the catalogue says.
"""

import argparse
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from credit_intel.config import DEFAULT_SETTINGS_PATH, LLMSettings, load_llm_settings, load_pricing
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, file_sha256
from credit_intel.export.manifest import code_version, package_versions, run_id
from credit_intel.export.run_export import export_failure, export_run
from credit_intel.ingestion.errors import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, ErrorCode, IngestionError, exit_code
from credit_intel.llm.factory import build_provider
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse
from credit_intel.models import StatementBasis
from credit_intel.run import run_pipeline
from credit_intel.send_rule import NOTICE, check_send
from credit_intel.states import Clock, Recorder, utc_now

DEFAULT_OUTPUT_DIR = Path("runs")
BASES = [StatementBasis.CONSOLIDATED.value, StatementBasis.STANDALONE.value]  # "unknown" is a finding, never a request
ENV_LOG_LEVEL = "CREDIT_INTEL_LOG_LEVEL"
EXIT_INTERRUPTED = 130
logger = logging.getLogger("credit_intel.cli")

ProviderFactory = Callable[[LLMSettings, Mapping[str, str]], LLMProvider]


class LazyProvider:
    """Builds the real provider on the first call, so a cache hit needs no key and a bad key fails in the right stage."""

    def __init__(self, factory: Callable[[], LLMProvider]) -> None:
        self._factory = factory
        self._provider: LLMProvider | None = None

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self._provider is None:
            self._provider = self._factory()
        return self._provider.complete(request)


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
    p.add_argument("--profile", type=Path, metavar="PROFILE_JSON", help="analyst-provided borrower profile (JSON)")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, metavar="DIR", help="where run folders are written (default: runs)")
    p.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML", help="settings file (default: config/settings.toml)")
    p.add_argument("--confirm-public-document", action="store_true",
                   help="confirm that a document not on the assignment record is public, so its statement pages may be sent to the hosted API")  # fmt: skip
    return p


@dataclass
class _Invocation:
    args: argparse.Namespace
    recorder: Recorder
    llm: LLMSettings | None = None
    sha256: str | None = None


def _level(name: str) -> int:
    level = logging.getLevelName(name.strip().upper())
    return level if isinstance(level, int) else logging.INFO


def _record_failure(call: _Invocation, err: IO[str], error: BaseException) -> None:
    """Make sure the recorder shows the failure and, if the run was recorded, leave a manifest-only folder (best effort)."""
    recorder = call.recorder
    if not recorder.events or call.sha256 is None or call.llm is None:
        return
    if not recorder.failed:
        recorder.fail(error.code.value if isinstance(error, IngestionError) else None)
    if isinstance(error, IngestionError) and error.code is ErrorCode.EXPORT_FAILED:
        return  # the output location is what failed
    try:
        path = export_failure(call.args.output_dir, recorder, call.llm, requested_basis=StatementBasis(call.args.basis), version=code_version(),
                              packages=package_versions(), input_file_name=call.args.pdf_path.name, input_sha256=call.sha256,
                              profile_file_name=call.args.profile.name if call.args.profile else None)  # fmt: skip
    except Exception:
        logger.debug("the failure record could not be written", exc_info=True)
        return
    print(f"Run record: {path}", file=err)


def _execute(call: _Invocation, factory: ProviderFactory, out: IO[str], err: IO[str], assignments: Path, env: Mapping[str, str]) -> int:
    args = call.args
    call.llm = llm = load_llm_settings(args.config, env)
    pricing = load_pricing(args.config, env)
    try:
        call.sha256 = file_sha256(args.pdf_path)
    except OSError:
        raise IngestionError(ErrorCode.NOT_FOUND) from None
    external = llm.provider != "fake"
    check_send(call.sha256, external=external, confirmed=args.confirm_public_document, assignments=assignments)
    if external:
        print(NOTICE, file=err)
    basis = StatementBasis(args.basis)
    result = run_pipeline(
        args.pdf_path, LazyProvider(lambda: factory(llm, env)), llm, recorder=call.recorder, basis=basis, page_range=args.pages,
        pricing=pricing, profile_path=args.profile,
    )  # fmt: skip
    path = export_run(args.output_dir, result, call.recorder, llm, requested_basis=basis, version=code_version(), packages=package_versions(),
                      profile_file_name=args.profile.name if args.profile else None)  # fmt: skip
    print(path, file=out)
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_factory: ProviderFactory = build_provider,
    clock: Clock = utc_now,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run the command and return its exit code. The streams, clock, environment and provider factory can be replaced for tests."""
    out, err = stdout or sys.stdout, stderr or sys.stderr
    environment = os.environ if env is None else env
    try:
        args = build_parser(err).parse_args(argv)
    except SystemExit as stop:  # argparse has printed its message; its code is 2 for a bad argument and 0 for --help
        return stop.code if isinstance(stop.code, int) else EXIT_USAGE

    handler = logging.StreamHandler(err)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    package_logger = logging.getLogger("credit_intel")
    previous = package_logger.level
    handler.setLevel(_level(environment.get(ENV_LOG_LEVEL, "INFO")))
    package_logger.addHandler(handler)
    package_logger.setLevel(handler.level)
    call = _Invocation(args, Recorder(clock))
    try:
        return _execute(call, provider_factory, out, err, assignments, environment)
    except SendRefused as refusal:
        print(f"Refused: {refusal}", file=err)
        return EXIT_USAGE
    except IngestionError as error:
        print(str(error), file=err)
        _record_failure(call, err, error)
        return exit_code(error)
    except KeyboardInterrupt:
        print("Interrupted.", file=err)
        return EXIT_INTERRUPTED
    except Exception as error:
        logger.debug("internal error", exc_info=True)  # the trace is for DEBUG only (FR-011.4)
        _record_failure(call, err, error)
        identifier = run_id(call.recorder.events[0].at, call.sha256) if call.recorder.events and call.sha256 else "unknown"
        print(f"Internal error. Run ID: {identifier}. Re-run, and report it if it persists.", file=err)
        return EXIT_INTERNAL
    finally:
        package_logger.removeHandler(handler)
        package_logger.setLevel(previous)


def run() -> None:
    """The console entry point."""
    raise SystemExit(main())
