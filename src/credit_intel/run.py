"""One run from a PDF to the evaluated risk indicators (PRD FR-011, FR-012.3; Phase 5 step 5c).

``run_pipeline`` chains the committed stages in the FR-011 order: the extraction pipeline
(``received`` to ``validated_fields``), then derived values and the five metrics (``calculated``),
then the risk rules (``rules_evaluated``). It stops there: the memo, the export and the command line
are the later steps of Phase 5.

Every transition goes into a ``Recorder`` (timestamps from an injectable clock) and is logged at INFO
with counts only: no document text, quotes or financial values (FR-012.3). A failure is recorded with
the state it happened in and its error code (``None`` for an internal error), and then re-raised
unchanged, so the caller can write the manifest and choose the exit code. The bad-configuration and
bad-profile cases fail in ``received`` (before it is entered), before any page is read or any model is called.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from credit_intel.calculations.calculate import MetricSet, calculate_metrics
from credit_intel.config import LLMSettings, PricingSettings
from credit_intel.extraction.pipeline import ExtractionRun, run_extraction
from credit_intel.extraction.prompt import Prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.provider import LLMProvider
from credit_intel.models import StatementBasis
from credit_intel.profile import Profile, load_profile
from credit_intel.risk.config import DEFAULT_RULES_PATH, load_risk_rules
from credit_intel.risk.evaluate import RuleSet, evaluate_rules
from credit_intel.risk.results import RuleOutcome
from credit_intel.states import CALCULATED, RECEIVED, RULES_EVALUATED, Recorder

logger = logging.getLogger("credit_intel.run")


@dataclass(frozen=True)
class RunResult:
    extraction: ExtractionRun  # the evidence: fields, verifications, attributes, stats (unchanged)
    metrics: MetricSet
    rules: RuleSet
    profile: Profile | None  # carried through unread: analyst-provided, never evidence (FR-014.7)
    rules_sha256: str  # the rules file's hash, for the manifest (FR-008.5)


def _log(state: str, recorder: Recorder, doc: str, counts: dict[str, object]) -> None:
    first, last = recorder.events[0].at, recorder.events[-1].at
    detail = " ".join(f"{key}={value}" for key, value in counts.items())
    logger.info("stage=%s doc=%s ms=%d %s", state, doc, int((last - first).total_seconds() * 1000), detail)


def run_pipeline(
    path: Path,
    provider: LLMProvider,
    llm: LLMSettings,
    *,
    recorder: Recorder | None = None,
    basis: StatementBasis = StatementBasis.CONSOLIDATED,
    page_range: str | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    prompt: Prompt | None = None,
    pricing: PricingSettings | None = None,
    profile_path: Path | None = None,
    rules_path: Path = DEFAULT_RULES_PATH,
    **extraction_options: object,
) -> RunResult:
    """Run to ``rules_evaluated``. Raises the original error after recording the failure."""
    recorder = recorder if recorder is not None else Recorder()
    try:
        profile = load_profile(profile_path) if profile_path is not None else None
        rules_config = load_risk_rules(rules_path)
        rules_sha256 = hashlib.sha256(rules_path.read_bytes()).hexdigest()
        recorder.enter(RECEIVED)  # the request is accepted once its inputs and configuration are readable

        extraction = run_extraction(
            path, provider, llm, basis=basis, page_range=page_range, cache_dir=cache_dir, prompt=prompt,
            pricing=pricing, observer=recorder.enter, **extraction_options,  # type: ignore[arg-type]
        )  # fmt: skip
        doc = extraction.source_document.sha256[:12]

        metrics = calculate_metrics(extraction.field_set)
        defined = sum(1 for r in metrics.results.values() if r.defined)
        recorder.enter(CALCULATED, {"metrics_defined": defined, "metrics_undefined": len(metrics.results) - defined,
                                    "derived": len(metrics.derived)})  # fmt: skip
        _log(CALCULATED, recorder, doc, dict(recorder.events[-1].counts))

        rule_set = evaluate_rules(extraction.field_set, metrics, rules_config)
        counts = {o.value: sum(1 for r in rule_set.results if r.outcome is o) for o in RuleOutcome}
        recorder.enter(RULES_EVALUATED, {**counts, "disabled": len(rule_set.disabled)})
        _log(RULES_EVALUATED, recorder, doc, dict(recorder.events[-1].counts))
    except Exception as error:
        recorder.fail(error.code.value if isinstance(error, IngestionError) else None)
        raise
    return RunResult(extraction, metrics, rule_set, profile, rules_sha256)
