"""Running one tuning document and summarising it by counts (PRD Phase 2 G5, O.2).

``run_tuning_document`` checks the send guard first, then runs the pipeline and returns a
counts-only summary. A catalogued stop (for example ``E-EXTRACT-BASIS-UNAVAILABLE``) is
returned as a result, not raised, because it is a finding. Any other error is raised.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from credit_intel.config import LLMSettings, PricingSettings
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, check_may_send, check_private_path, file_sha256
from credit_intel.evaluation.summary import summarise_run, summarise_stop
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import Prompt
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.provider import LLMProvider
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.filter import PageFilterSetup


def tuning_options(env: Mapping[str, str]) -> dict:
    """The run options named in the environment of a live tuning run (``tests/live/test_live_tuning.py``).

    ``CREDIT_INTEL_BASIS`` (default consolidated), ``CREDIT_INTEL_PAGES`` (a page range) and ``CREDIT_INTEL_ASSERT_BASIS``
    (consolidated or standalone; H.4.6, v0.4.24), which needs ``CREDIT_INTEL_PAGES``. Raises ``ValueError`` for a value that
    is not allowed, naming the variable and never its value.
    """
    basis = env.get("CREDIT_INTEL_BASIS", "consolidated").strip() or "consolidated"
    pages = env.get("CREDIT_INTEL_PAGES", "").strip() or None
    asserted = env.get("CREDIT_INTEL_ASSERT_BASIS", "").strip() or None
    if basis not in ("consolidated", "standalone"):
        raise ValueError("CREDIT_INTEL_BASIS must be consolidated or standalone")
    if asserted is not None and asserted not in ("consolidated", "standalone"):
        raise ValueError("CREDIT_INTEL_ASSERT_BASIS must be consolidated or standalone")
    if asserted is not None and pages is None:
        raise ValueError("CREDIT_INTEL_ASSERT_BASIS needs CREDIT_INTEL_PAGES")
    return {"basis": StatementBasis(basis), "page_range": pages, "assert_basis": StatementBasis(asserted) if asserted else None}


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
    assert_basis: StatementBasis | None = None,
    env: Mapping[str, str] | None = None,
    page_filter: PageFilterSetup | None = None,
) -> dict:
    try:
        sha256 = file_sha256(path)
    except OSError:
        raise IngestionError(ErrorCode.NOT_FOUND) from None  # the same code ingestion would give
    if not synthetic and llm.provider != "fake":  # a document under private/ needs the owner's approval of this run (v0.4.31)
        check_private_path(path, os.environ if env is None else env)
    document_id = check_may_send(sha256, assignments, synthetic=synthetic)  # raises SendRefused
    try:
        run = run_extraction(
            path, provider, llm, basis=basis, page_range=page_range, cache_dir=cache_dir, pricing=pricing, prompt=prompt,
            assert_basis=assert_basis, page_filter=page_filter,
        )  # fmt: skip
    except IngestionError as error:
        return {"set": "tuning", **summarise_stop(error, document_id, sha256, assert_basis.value if assert_basis else None)}
    return {"set": "tuning", **summarise_run(run, document_id)}
