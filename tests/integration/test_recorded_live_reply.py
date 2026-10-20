"""The model's real reply from the G4 live test, replayed offline (Phase 2; B-228).

``tests/fixtures/live_g4_synthetic_reply.json`` is what ``gpt-4o-mini`` actually returned on
2026-10-20 for the synthetic balance sheet of ``pipeline_fixture``. Replaying it needs no key
and no network. It characterises the real model's behaviour on a page where every value was
easy: all the values were right, and the deterministic checks caught what was not.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.config import PricingSettings
from credit_intel.llm.provider import FakeProvider, FakeReply
from credit_intel.models import FieldName, PeriodRole, Status, StatusReason as R

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "live_g4_synthetic_reply.json"
CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE


@pytest.fixture(scope="module")
def recorded():
    return json.loads(FIXTURE.read_text(encoding="ascii"))


@pytest.fixture
def replay(recorded, tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "synthetic.pdf")
    reply = FakeReply(recorded["response_text"], recorded["usage"]["input_tokens"], recorded["usage"]["output_tokens"])
    prices = PricingSettings(Decimal("0.15"), Decimal("0.60"))
    return run_extraction(pdf, FakeProvider(script=[reply]), fx.LLM, cache_dir=tmp_path / "cache", pricing=prices)


def test_the_fixture_is_synthetic_metadata_and_a_reply_with_no_credentials(recorded):
    text = FIXTURE.read_text(encoding="ascii")

    assert set(recorded) == {"about", "recorded_at", "model_id", "prompt_version", "usage", "response_text"}
    assert recorded["model_id"] == "gpt-4o-mini" and recorded["prompt_version"] == "extraction-v1"
    assert "sk-" not in text and "Bearer" not in text and "OPENAI_API_KEY" not in text
    assert set(json.loads(recorded["response_text"])) == {"attributes", "fields"}


def test_the_replay_reproduces_the_live_run_exactly(replay):
    assert replay.field_set.counts == {"extracted": 3, "not_found": 18, "conflicting": 0, "requires_review": 3}
    assert (replay.stats.llm_calls, replay.stats.llm_retries) == (1, 0)
    assert (replay.stats.input_tokens, replay.stats.output_tokens) == (1937, 607)
    assert replay.stats.estimated_cost == Decimal("0.00065475")  # the cost the live test printed


def test_every_value_the_model_read_was_right(replay):
    expected = {
        (FieldName.CURRENT_ASSETS, CUR): "1,482.30", (FieldName.CURRENT_ASSETS, COMP): "1,356.75",
        (FieldName.TOTAL_EQUITY, CUR): "600.00", (FieldName.TOTAL_EQUITY, COMP): "500.00",
        (FieldName.CURRENT_LIABILITIES, CUR): "900.00", (FieldName.CURRENT_LIABILITIES, COMP): "850.00",
    }  # fmt: skip

    got = {(v.field.field_name, v.field.period_role): v.field.raw_value for v in replay.verifications}

    assert got == expected


def test_the_three_current_period_fields_are_extracted_in_base_units(replay):
    values = {
        FieldName.CURRENT_ASSETS: Decimal("14823000000"),
        FieldName.TOTAL_EQUITY: Decimal("6000000000"),
        FieldName.CURRENT_LIABILITIES: Decimal("9000000000"),
    }  # fmt: skip

    for name, value in values.items():
        record = replay.field_set.get(name, CUR)
        assert record.status is Status.EXTRACTED and record.value == value and record.currency == "INR"


def test_the_comparative_quotes_the_model_shortened_are_caught_as_not_on_the_page(replay):
    comparative = [v for v in replay.verifications if v.field.period_role is COMP]

    assert len(comparative) == 3
    for verification in comparative:
        assert verification.field.status is Status.REQUIRES_REVIEW
        assert verification.field.status_reason is R.EVIDENCE_NOT_VERIFIED
        assert verification.field.value is None  # never accepted on a quote that is not on the page
    quote = next(v.field.evidence_quote for v in comparative if v.field.field_name is FieldName.CURRENT_ASSETS)
    assert quote == "Total current assets 14 1,356.75 "  # the page says "14 1,482.30 1,356.75"


def test_all_the_document_attributes_are_extracted_even_when_the_model_adds_a_period_role_to_the_name(replay):
    # The model returned entity_name with period_role "current" (strict mode makes the field nullable).
    # An attribute that is not a period-end has no role, so it must not be dropped for having one.
    by_name = {a.attribute.value: a for a in replay.attributes.all if a.period_role is None}

    assert all(a.status is Status.EXTRACTED for a in replay.attributes.all)
    assert by_name["entity_name"].normalised_value == "Acme Industries Limited"
    assert replay.attributes.period_end(CUR).isoformat() == "2025-03-31"
    assert replay.attributes.period_end(COMP).isoformat() == "2024-03-31"
