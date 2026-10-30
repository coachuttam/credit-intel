"""The one function that runs the pipeline for one document (PRD FR-016, v0.4.59; Phase 6 step 1).

``execute_run`` does what the command line did inline: it reads the settings, builds the parser, the optional page
classifier and the OCR engine, applies the send rule (SEC-10), runs the pipeline and writes the run folder. The command
line (``cli``) and, from step 2, the HTTP API both call it, so the wiring exists once. Nothing here is new behaviour:
the order of the steps, the errors and the files are exactly those of the command line before the move.

The service prints nothing. The one line it has for the person running it (the notice that pages will be sent) goes
to the ``notify`` callback the caller gives, and a failure record is reported by its returned path.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from credit_intel.config import (
    DEFAULT_SETTINGS_PATH,
    LLMSettings,
    load_jev_settings,
    load_llm_settings,
    load_ocr_settings,
    load_parse_limits,
    load_pricing,
    load_step_settings,
)
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, ENV_PRIVATE_APPROVED, file_sha256
from credit_intel.export.manifest import code_version, package_versions
from credit_intel.export.run_export import export_failure, export_run
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import OcrExtractor, TextExtractor
from credit_intel.ingestion.ocr_engine import default_ocr_extractor
from credit_intel.ingestion.sandbox import SandboxedExtractor
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.factory import build_provider
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.factory import ClassifierFactory, build_classifier
from credit_intel.pagefilter.filter import PageFilterSetup
from credit_intel.run import run_pipeline
from credit_intel.send_rule import NOTICE, SendRefusal, check_send
from credit_intel.states import Recorder

DEFAULT_OUTPUT_DIR = Path("runs")
logger = logging.getLogger("credit_intel.service")

ProviderFactory = Callable[[LLMSettings, Mapping[str, str]], LLMProvider]
OcrFactory = Callable[[], OcrExtractor]
ExtractorFactory = Callable[[Path, Mapping[str, str]], TextExtractor]


class LazyProvider:
    """Builds the real provider on the first call, so a cache hit needs no key and a bad key fails in the right stage."""

    def __init__(self, factory: Callable[[], LLMProvider]) -> None:
        self._factory = factory
        self._provider: LLMProvider | None = None

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self._provider is None:
            self._provider = self._factory()
        return self._provider.complete(request)


@dataclass(frozen=True)
class RunRequest:
    """What one run is asked to do: the options of the command line (FR-014 criterion 1), with the folders made explicit."""

    pdf_path: Path
    basis: StatementBasis = StatementBasis.CONSOLIDATED
    pages: str | None = None
    assert_basis: StatementBasis | None = None
    profile: Path | None = None
    output_dir: Path = DEFAULT_OUTPUT_DIR
    cache_dir: Path = DEFAULT_CACHE_DIR
    config: Path = DEFAULT_SETTINGS_PATH
    ocr: bool = False
    confirm_public_document: bool = False
    no_report: bool = False


@dataclass(frozen=True)
class RunServices:
    """The parts a run uses that a test (or a different caller) may replace. The defaults are the real ones."""

    provider_factory: ProviderFactory = build_provider
    classifier_factory: ClassifierFactory = build_classifier
    ocr_factory: OcrFactory = default_ocr_extractor
    extractor_factory: ExtractorFactory | None = None
    assignments: Path = ASSIGNMENTS_PATH


@dataclass
class RunProgress:
    """What a run has learned so far, kept outside ``execute_run`` so that a caller can still record a failure after it raised."""

    recorder: Recorder
    llm: LLMSettings | None = None
    sha256: str | None = None


def sandboxed_extractor(config: Path, env: Mapping[str, str]) -> SandboxedExtractor:
    """The PDF parser of a run: the PDF libraries in a worker process under the required parse limits (SEC-12, v0.4.50)."""
    return SandboxedExtractor(load_parse_limits(config, env))


def ocr_engine(ocr_factory: OcrFactory, extractor: TextExtractor) -> OcrExtractor:
    """The OCR engine of a run. When the parser can render pages in a worker (SEC-12 step 2) the engine renders there, and when it can
    supervise a command (step 3) the engine's own reading is watched for memory."""
    engine = ocr_factory()
    for parser_method, engine_hook in (("render_page", "use_renderer"), ("run_supervised", "use_runner")):
        method, hook = getattr(extractor, parser_method, None), getattr(engine, engine_hook, None)
        if method is not None and hook is not None:
            hook(method)
    return engine


def page_filter(request: RunRequest, llm: LLMSettings, env: Mapping[str, str], factory: ClassifierFactory) -> PageFilterSetup | None:
    """The optional page classifier of a run (PRD v0.4.31), or ``None`` when ``USE_JEV`` is not "true". Never raises for the classifier."""
    jev = load_jev_settings(request.config, env)
    if not jev.enabled:
        return None
    load_step_settings(request.config, llm.provider)  # a bad [steps] table is a configuration error, as any other setting is
    try:
        classifier = factory(jev, env)
    except Exception:
        logger.debug("the page classifier could not be built", exc_info=True)
        return PageFilterSetup(jev, None, "error")
    return PageFilterSetup(jev, classifier, None if classifier is not None else "no_key")


def execute_run(request: RunRequest, progress: RunProgress, services: RunServices, env: Mapping[str, str], notify: Callable[[str], None]) -> Path:
    """Run the pipeline for one document and return the run folder. Raises ``IngestionError`` (a catalogued failure) or another exception."""
    progress.llm = llm = load_llm_settings(request.config, env)
    pricing = load_pricing(request.config, env)
    ocr = load_ocr_settings(request.config, request.ocr)
    extractor = (services.extractor_factory or sandboxed_extractor)(request.config, env)  # the required parse limits are read here (E-CONFIG-INVALID)
    classifier_setup = page_filter(request, llm, env, services.classifier_factory)
    try:
        progress.sha256 = file_sha256(request.pdf_path)
    except OSError:
        raise IngestionError(ErrorCode.NOT_FOUND) from None
    # The send rule applies to every provider that would receive page text: the extraction model and the classifier (v0.4.31).
    classifier = classifier_setup.classifier if classifier_setup is not None else None
    external = llm.provider != "fake" or (classifier is not None and classifier.sends_off_machine)
    try:
        check_send(progress.sha256, external=external, confirmed=request.confirm_public_document, assignments=services.assignments,
                   path=request.pdf_path, private_approved=env.get(ENV_PRIVATE_APPROVED) == "1")  # fmt: skip
    except SendRefusal as refusal:  # a catalogued failure before `received`: exit 3, a fixed reason word, no failure record (G.1, v0.4.27)
        raise IngestionError(ErrorCode.SEND_REFUSED, detail=refusal.reason) from None
    if external:
        notify(NOTICE)
    result = run_pipeline(
        request.pdf_path, LazyProvider(lambda: services.provider_factory(llm, env)), llm, recorder=progress.recorder, basis=request.basis,
        page_range=request.pages, pricing=pricing, profile_path=request.profile, extractor=extractor, ocr_settings=ocr,
        ocr_extractor=ocr_engine(services.ocr_factory, extractor) if ocr.enabled else None, assert_basis=request.assert_basis,
        page_filter=classifier_setup, cache_dir=request.cache_dir,
    )  # fmt: skip
    return export_run(request.output_dir, result, progress.recorder, llm, requested_basis=request.basis, version=code_version(), packages=package_versions(),
                      profile_file_name=request.profile.name if request.profile else None, report=not request.no_report)  # fmt: skip


def record_failure(request: RunRequest, progress: RunProgress, error: BaseException) -> Path | None:
    """Make sure the recorder shows the failure and, if the run was recorded, leave a manifest-only folder (best effort).

    Returns the folder written, or ``None`` when the run was not far enough along to be recorded or the record could not be written."""
    recorder = progress.recorder
    if not recorder.events or progress.sha256 is None or progress.llm is None:
        return None
    if not recorder.failed:
        recorder.fail(error.code.value if isinstance(error, IngestionError) else None)
    if isinstance(error, IngestionError) and error.code is ErrorCode.EXPORT_FAILED:
        return None  # the output location is what failed
    try:
        return export_failure(request.output_dir, recorder, progress.llm, requested_basis=request.basis, version=code_version(),
                              packages=package_versions(), input_file_name=request.pdf_path.name, input_sha256=progress.sha256,
                              profile_file_name=request.profile.name if request.profile else None, asserted_basis=request.assert_basis)  # fmt: skip
    except Exception:
        logger.debug("the failure record could not be written", exc_info=True)
        return None
