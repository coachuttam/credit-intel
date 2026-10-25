"""Live run on one tuning document, counts only (Phase 2 G5). Opt-in; costs money; sends pages.

Skipped unless CREDIT_INTEL_LIVE=1 and OPENAI_API_KEY are set (tests/conftest.py) and
CREDIT_INTEL_DOCUMENT names the PDF. It runs the whole pipeline through the real provider
and prints ONE line of counts: candidate page numbers, statuses by reason, tokens and cost,
never document text, quotes or values. A run that stops on a catalogued error (for example
E-EXTRACT-BASIS-UNAVAILABLE) is a result and passes.

The send guard runs first (PRD SEC-10, the owner's G2 rule): only a document recorded as a
tuning document in tests/eval/assignments.jsonl may be sent. Anything else, including a
held-out document, is refused before any request. The page text of a run is kept in the
git-ignored response cache .cache/llm (the accepted G2 risk); delete that directory to clear it.

    CREDIT_INTEL_DOCUMENT=/path/to/report.pdf CREDIT_INTEL_LIVE=1 \\
    CREDIT_INTEL_TOKEN_CEILING=120000 CREDIT_INTEL_MAX_OUTPUT_TOKENS=8192 \\
    uv run --locked pytest tests/live/test_live_tuning.py -q -s

CREDIT_INTEL_BASIS (consolidated or standalone, default consolidated), CREDIT_INTEL_PAGES
(a page range), CREDIT_INTEL_ASSERT_BASIS (consolidated or standalone; the analyst's assertion for the pages of a range
that name no basis, PRD H.4.6 v0.4.24; needs CREDIT_INTEL_PAGES) and CREDIT_INTEL_PROMPT (a name under prompts/, default
the application's default) are optional.
"""

import os
from pathlib import Path

import pytest

from credit_intel.config import load_llm_settings, load_pricing
from credit_intel.evaluation.runner import run_tuning_document, tuning_options
from credit_intel.evaluation.summary import to_line
from credit_intel.extraction.prompt import DEFAULT_PROMPT, load_prompt
from credit_intel.llm.factory import build_provider

pytestmark = pytest.mark.live


def test_one_tuning_document_by_counts():
    document = os.environ.get("CREDIT_INTEL_DOCUMENT", "").strip()
    if not document:
        pytest.skip("set CREDIT_INTEL_DOCUMENT to the PDF to run")
    settings = load_llm_settings()

    summary = run_tuning_document(
        Path(document),
        build_provider(settings),
        settings,
        **tuning_options(os.environ),
        pricing=load_pricing(),
        prompt=load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT)),
    )

    print("\n" + to_line("tuning run", summary))
    assert summary["outcome"] in ("completed", "stopped")
    if summary["outcome"] == "completed":
        assert summary["tokens_in"] + summary["tokens_out"] <= settings.token_ceiling
