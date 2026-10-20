"""Live smoke test against the real OpenAI API (Phase 2 G4). Opt-in; costs money.

Skipped unless CREDIT_INTEL_LIVE=1 and OPENAI_API_KEY are set in the environment of the
person running it (see tests/conftest.py). It sends one small request built from a
synthetic PDF only, never a real document, under the token ceiling taken from
CREDIT_INTEL_TOKEN_CEILING (a required setting). It asserts that the pipeline completes
and its records are consistent; it makes no claim about the model's accuracy, which is
what the tuning-set run is for. Run it deliberately:

    CREDIT_INTEL_LIVE=1 uv run --locked pytest tests/live -q -s

``CREDIT_INTEL_PROMPT`` (a name under ``prompts/``, default ``extraction_v1``) chooses the
prompt, so a drafted prompt can be tried on the synthetic page. It is read by this test
only; the application uses the default prompt unless the caller passes another.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integration"))

import pipeline_fixture as fx  # noqa: E402

from credit_intel.config import load_llm_settings, load_pricing  # noqa: E402
from credit_intel.extraction.pipeline import run_extraction  # noqa: E402
from credit_intel.extraction.prompt import load_prompt  # noqa: E402
from credit_intel.llm.factory import build_provider  # noqa: E402

pytestmark = pytest.mark.live


def test_one_small_synthetic_request_runs_through_the_real_provider(tmp_path):
    settings = load_llm_settings()
    pricing = load_pricing()
    pdf = fx.balance_sheet_pdf(tmp_path / "synthetic.pdf")

    prompt = load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", "extraction_v1"))

    result = run_extraction(
        pdf, build_provider(settings), settings, cache_dir=tmp_path / "cache", pricing=pricing, prompt=prompt
    )

    fields = result.field_set
    print(
        f"\nlive run: model={settings.model_id} prompt={prompt.version} counts={fields.counts} calls={result.stats.llm_calls} "
        f"retries={result.stats.llm_retries} tokens_in={result.stats.input_tokens} "
        f"tokens_out={result.stats.output_tokens} cost_usd={result.stats.estimated_cost}"
    )
    assert len(fields.fields) == 24 and sum(fields.counts.values()) == 24
    assert result.stats.llm_calls >= 1 and result.stats.tokens_used > 0
    assert result.stats.tokens_used <= settings.token_ceiling
