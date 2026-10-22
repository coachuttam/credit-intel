"""Running one tuning document and summarising it by counts (PRD Phase 2 G5, O.2).

``run_tuning_document`` checks the send guard first, then runs the pipeline and returns a
counts-only summary. A catalogued stop (for example ``E-EXTRACT-BASIS-UNAVAILABLE``) is
returned as a result, not raised, because it is a finding. Any other error is raised.
"""

from pathlib import Path

from credit_intel.config import LLMSettings, PricingSettings
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, check_may_send, file_sha256
from credit_intel.evaluation.summary import summarise_run, summarise_stop
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import Prompt
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.provider import LLMProvider
from credit_intel.models import StatementBasis


def run_tuning_document(
    path: Path,
    provider: LLMProvider,
    llm: LLMSettings,
    *,
    basis: StatementBasis = StatementBasis.CONSOLIDATED,
    page_range: str | None = None,
    pricing: PricingSettings | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    synthetic: bool = False,
    prompt: Prompt | None = None,
) -> dict:
    try:
        sha256 = file_sha256(path)
    except OSError:
        raise IngestionError(ErrorCode.NOT_FOUND) from None  # the same code ingestion would give
    document_id = check_may_send(sha256, assignments, synthetic=synthetic)  # raises SendRefused
    try:
        run = run_extraction(
            path, provider, llm, basis=basis, page_range=page_range, cache_dir=cache_dir, pricing=pricing, prompt=prompt
        )
    except IngestionError as error:
        return summarise_stop(error, document_id, sha256)
    return summarise_run(run, document_id)
