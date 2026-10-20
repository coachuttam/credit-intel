"""The model's real reply to the draft ``extraction-v2`` prompt, replayed offline (Phase 2; B-230).

``tests/fixtures/live_v2_synthetic_reply.json`` is what ``gpt-4o-mini`` returned on 2026-10-20
for the same synthetic balance sheet as the first live run, with the draft v2 prompt. It
needs no key and no network. Together with the first reply it shows what the stronger quote
rule changed: the values were already right, and the quotes are now whole page lines.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.config import PricingSettings
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.llm.provider import FakeProvider, FakeReply
from credit_intel.models import FieldName, PeriodRole, Status

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="ascii"))


@pytest.fixture(scope="module")
def v1():
    return load("live_g4_synthetic_reply.json")


@pytest.fixture(scope="module")
def v2():
    return load("live_v2_synthetic_reply.json")


def replay(recorded, tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "synthetic.pdf")
    reply = FakeReply(recorded["response_text"], recorded["usage"]["input_tokens"], recorded["usage"]["output_tokens"])
    prices = PricingSettings(Decimal("0.15"), Decimal("0.60"))
    result = run_extraction(pdf, FakeProvider(script=[reply]), fx.LLM, cache_dir=tmp_path / "cache", pricing=prices)
    return result, PdfplumberExtractor().extract_pages(pdf)[0].text.split("\n")


def test_the_fixture_is_metadata_and_a_reply_with_no_credentials(v2):
    text = (FIXTURES / "live_v2_synthetic_reply.json").read_text(encoding="ascii")

    assert set(v2) == {"about", "recorded_at", "model_id", "prompt_version", "usage", "response_text"}
    assert v2["model_id"] == "gpt-4o-mini" and v2["prompt_version"] == "extraction-v2"
    assert "sk-" not in text and "Bearer" not in text and "OPENAI_API_KEY" not in text


def test_the_replay_reproduces_the_live_run_exactly(v2, tmp_path):
    result, _ = replay(v2, tmp_path)

    assert result.field_set.counts == {"extracted": 6, "not_found": 18, "conflicting": 0, "requires_review": 0}
    assert (result.stats.llm_calls, result.stats.llm_retries) == (1, 0)
    assert (result.stats.input_tokens, result.stats.output_tokens) == (2060, 634)
    assert result.stats.estimated_cost == Decimal("0.0006894")  # the cost the live test printed


def test_every_quote_is_now_a_whole_page_line(v2, tmp_path):
    result, page_lines = replay(v2, tmp_path)

    for verification in result.verifications:
        assert verification.field.evidence_quote in page_lines, verification.field.evidence_quote


def test_all_six_fields_are_extracted_with_the_right_values_in_base_units(v2, tmp_path):
    result, _ = replay(v2, tmp_path)
    expected = {
        (FieldName.CURRENT_ASSETS, CUR): "14823000000", (FieldName.CURRENT_ASSETS, COMP): "13567500000",
        (FieldName.TOTAL_EQUITY, CUR): "6000000000", (FieldName.TOTAL_EQUITY, COMP): "5000000000",
        (FieldName.CURRENT_LIABILITIES, CUR): "9000000000", (FieldName.CURRENT_LIABILITIES, COMP): "8500000000",
    }  # fmt: skip

    for (name, role), value in expected.items():
        record = result.field_set.get(name, role)
        assert record.status is Status.EXTRACTED and record.value == Decimal(value) and record.currency == "INR"


def test_every_attribute_is_extracted_even_though_the_model_again_gave_entity_name_a_role(v2, tmp_path):
    result, _ = replay(v2, tmp_path)
    reply = json.loads(v2["response_text"])

    entity = next(a for a in reply["attributes"] if a["attribute"] == "entity_name")
    assert entity["period_role"] == "current"  # as in the first live run; the fix ignores it
    assert all(a.status is Status.EXTRACTED for a in result.attributes.all)


def test_the_two_prompts_gave_the_same_values_and_only_the_quotes_changed(v1, v2):
    def values(recorded):
        return {(f["field_name"], f["period_role"]): f["raw_value"] for f in json.loads(recorded["response_text"])["fields"]}

    old, new = json.loads(v1["response_text"])["fields"], json.loads(v2["response_text"])["fields"]

    assert values(v1) == values(v2) and len(old) == len(new) == 6
    # v1 shortened all six quotes; v2 changed all six into the whole page line.
    assert all(a["evidence_quote"] != b["evidence_quote"] for a, b in zip(old, new))
    assert all(len(a["evidence_quote"].strip()) < len(b["evidence_quote"]) for a, b in zip(old, new))


def test_in_the_first_reply_three_shortened_quotes_still_happened_to_be_on_the_page(v1):
    # The current-period quotes were cut at the end, so they were still contiguous parts of the line
    # and verified; the comparative ones skipped the figure in the middle and did not.
    page = fx_page_lines()
    on_page = {(f["field_name"], f["period_role"]): f["evidence_quote"].strip() in "\n".join(page)
               for f in json.loads(v1["response_text"])["fields"]}  # fmt: skip

    assert {k for k, v in on_page.items() if v} == {
        ("current_assets", "current"), ("total_equity", "current"), ("current_liabilities", "current")
    }
    assert {k for k, v in on_page.items() if not v} == {
        ("current_assets", "comparative"), ("total_equity", "comparative"), ("current_liabilities", "comparative")
    }


def fx_page_lines():
    import tempfile

    pdf = fx.balance_sheet_pdf(Path(tempfile.mkdtemp()) / "synthetic.pdf")
    return PdfplumberExtractor().extract_pages(pdf)[0].text.split("\n")


def test_the_v2_run_cost_a_little_more_because_the_prompt_is_longer(v1, v2):
    assert v2["usage"]["input_tokens"] > v1["usage"]["input_tokens"]  # 2,060 against 1,937
    assert v2["usage"]["input_tokens"] - v1["usage"]["input_tokens"] < 200
