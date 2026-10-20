"""The offline extraction pipeline (Phase 2 step 9a; B-222).

A synthetic balance sheet, a scripted fake provider and no network access.
"""

import hashlib
import logging
from decimal import Decimal

import pytest

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import ExtractionRun, run_extraction
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.config import PricingSettings
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import FieldName, PeriodRole, StatementBasis, Status

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def run(pdf, tmp_path, replies=None, **kw) -> tuple[ExtractionRun, FakeProvider]:
    provider = FakeProvider(script=replies if replies is not None else [fx.good_response(pdf)])
    kw.setdefault("cache_dir", tmp_path / "cache")
    return run_extraction(pdf, provider, fx.LLM, **kw), provider


# --- a clean statement --------------------------------------------------------------------------


def test_a_clean_statement_gives_the_six_fields_and_marks_the_rest_not_found(pdf, tmp_path):
    result, provider = run(pdf, tmp_path)

    fields = result.field_set
    assert fields.counts == {"extracted": 6, "not_found": 18, "conflicting": 0, "requires_review": 0}
    assert fields.get(FieldName.CURRENT_ASSETS, CUR).value == Decimal("14823000000")
    assert fields.get(FieldName.CURRENT_ASSETS, COMP).value == Decimal("13567500000")
    assert fields.get(FieldName.TOTAL_EQUITY, CUR).field_id == "total_equity.2025-03-31.consolidated"
    assert fields.get(FieldName.REVENUE, CUR).status is Status.NOT_FOUND
    assert len(provider.calls) == 1


def test_the_attributes_are_verified_and_the_basis_matches(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    assert all(a.status is Status.EXTRACTED for a in result.attributes.all)
    assert result.attribute_basis_differs is False
    assert result.configured_basis is StatementBasis.CONSOLIDATED


def test_the_run_identifies_the_document_and_the_pages(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    assert result.source_document.sha256 == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert result.source_document.file_name == "statement.pdf"
    assert result.page_count == 1
    assert [c.page_number for c in result.located.candidates] == [1]
    assert result.extraction.prompt_version == "extraction-v2" and result.extraction.attempts == 1


def test_the_statistics_count_calls_tokens_and_the_cache(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    assert result.stats.llm_calls == 1 and result.stats.tokens_used > 0
    assert (result.stats.cache_hits, result.stats.cache_misses) == (0, 1)


def test_every_verification_is_kept_beside_the_field_set(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    assert len(result.verifications) == 6 and all(v.field is not None for v in result.verifications)


def test_a_second_run_with_the_same_cache_makes_no_provider_call_and_gives_the_same_result(pdf, tmp_path):
    first, _ = run(pdf, tmp_path)
    second, provider = run(pdf, tmp_path, replies=[])

    assert provider.calls == [] and second.stats.llm_calls == 0
    assert (second.stats.cache_hits, second.stats.cache_misses) == (1, 0) and second.stats.tokens_used == 0
    assert second.field_set == first.field_set and second.attributes == first.attributes


# --- the configured basis ---------------------------------------------------------------------------


def test_b6_row_9_a_configured_basis_the_document_lacks_stops_before_any_call(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, basis=StatementBasis.STANDALONE, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE and provider.calls == []


def test_a_basis_that_is_not_consolidated_or_standalone_is_refused_before_the_file_is_read(tmp_path):
    with pytest.raises(ValueError):  # not an IngestionError for the missing file
        run_extraction(tmp_path / "absent.pdf", FakeProvider(), fx.LLM, basis=StatementBasis.UNKNOWN)


def test_the_model_reading_another_basis_is_recorded_and_blocks_nothing(pdf, tmp_path):
    reply = fx.good_response(pdf).replace('"normalised_value": "consolidated"', '"normalised_value": "standalone"')

    result, _ = run(pdf, tmp_path, replies=[reply])

    assert result.attribute_basis_differs is False  # the attribute failed verification, so it is not extracted
    assert result.attributes.statement_basis.status is Status.REQUIRES_REVIEW


# --- only the candidate pages are used -----------------------------------------------------------------


def test_a_quote_from_a_page_that_is_not_a_candidate_is_not_verified(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "two.pdf", narrative_page="The company reported 1,482.30 crore")
    cited = {"page_number": 2, "evidence_quote": "The company reported 1,482.30 crore"}

    result, _ = run(pdf, tmp_path, replies=[fx.good_response(pdf, field_changes={0: cited})])

    assert [c.page_number for c in result.located.candidates] == [1]
    assert result.verifications[0].reasons[0].value == "evidence_not_verified"
    kept = [r for r in result.field_set.fields if r.field_name is FieldName.CURRENT_ASSETS and r.period_role is CUR]
    assert [r.status for r in kept] == [Status.REQUIRES_REVIEW]  # reported, not silently dropped
    assert kept[0].statement_basis is StatementBasis.UNKNOWN  # a page that is not a statement has no basis


# --- the token ceiling ---------------------------------------------------------------------------------------


def test_a_ceiling_the_call_would_exceed_stops_the_run_before_any_call(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])
    small = fx.LLM.__class__(provider="fake", model_id="m", token_ceiling=100, max_output_tokens=2000)

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, small, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED and provider.calls == []


# --- failures propagate -----------------------------------------------------------------------------------


def test_a_missing_file_is_a_catalogued_error(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        run_extraction(tmp_path / "absent.pdf", FakeProvider(), fx.LLM, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_a_document_with_no_statement_pages_stops_before_any_call(tmp_path):
    pdf = fx.blank_text_pdf(tmp_path / "report.pdf")
    provider = FakeProvider(script=["unused"])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.NO_STATEMENT_PAGES and provider.calls == []


# --- logging (FR-011.1, FR-012.3) -----------------------------------------------------------------------------------


def stage_records(caplog):
    return [r for r in caplog.records if r.name == "credit_intel.pipeline"]


def test_each_stage_is_logged_in_order_with_counts_and_durations(pdf, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="credit_intel.pipeline"):
        run(pdf, tmp_path)

    messages = [r.getMessage() for r in stage_records(caplog)]
    stages = [m.split()[0] for m in messages]
    assert stages == ["stage=received", "stage=validated", "stage=text_extracted", "stage=statements_located",
                      "stage=fields_extracted", "stage=validated_fields"]  # fmt: skip
    assert "pages=1" in messages[1] and "candidates=1" in messages[3]
    assert "attempts=1" in messages[4] and "llm_calls=1" in messages[4]
    assert "extracted=6" in messages[5] and "ignored=0" in messages[5] and "unplaced=0" in messages[5]
    assert all(" ms=" in m for m in messages)
    assert all(r.levelno == logging.INFO and r.created for r in stage_records(caplog))


def test_info_logs_carry_no_document_text_quotes_values_or_file_names(pdf, tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        run(pdf, tmp_path)

    text = "\n".join(r.getMessage() for r in caplog.records)
    for secret in ("Acme", "Total current assets", "1,482.30", "14823000000", "Rs. in crore", "statement.pdf", str(tmp_path)):
        assert secret not in text, secret
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()[:12] in text


def test_a_failure_is_logged_with_its_stage_and_code_and_no_text(tmp_path, caplog):
    pdf = fx.blank_text_pdf(tmp_path / "report.pdf")

    with caplog.at_level(logging.INFO), pytest.raises(IngestionError):
        run_extraction(pdf, FakeProvider(), fx.LLM, cache_dir=tmp_path / "c")

    last = stage_records(caplog)[-1].getMessage()
    assert last.startswith("stage=failed") and "after=fields_extracted" in last  # G.1 lists it there
    assert "code=E-EXTRACT-NO-STATEMENT-PAGES" in last and "Directors" not in last


def test_a_missing_configured_basis_is_logged_as_a_statements_located_failure(pdf, tmp_path, caplog):
    with caplog.at_level(logging.INFO), pytest.raises(IngestionError):
        run(pdf, tmp_path, basis=StatementBasis.STANDALONE)

    last = stage_records(caplog)[-1].getMessage()
    assert "after=statements_located" in last and "code=E-EXTRACT-BASIS-UNAVAILABLE" in last
    assert "stage=fields_extracted" not in "\n".join(r.getMessage() for r in stage_records(caplog))


def test_a_missing_file_is_logged_as_failed_after_validation(tmp_path, caplog):
    with caplog.at_level(logging.INFO), pytest.raises(IngestionError):
        run_extraction(tmp_path / "absent.pdf", FakeProvider(), fx.LLM, cache_dir=tmp_path / "c")

    assert "after=validated" in stage_records(caplog)[-1].getMessage()


# --- token split and estimated cost (D-02, NFR-09) ------------------------------------------------------------------


PRICES = PricingSettings(Decimal("0.15"), Decimal("0.6"))


def test_the_statistics_split_the_provider_reported_tokens_and_total_them(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    stats = result.stats
    assert stats.input_tokens > 0 and stats.output_tokens > 0
    assert stats.input_tokens + stats.output_tokens == stats.tokens_used


def test_no_cost_is_estimated_without_prices(pdf, tmp_path):
    result, _ = run(pdf, tmp_path)

    assert result.stats.estimated_cost is None


def test_the_cost_is_exact_from_the_reported_tokens_and_the_configured_prices(pdf, tmp_path):
    result, _ = run(pdf, tmp_path, pricing=PRICES)

    stats = result.stats
    assert stats.estimated_cost == (stats.input_tokens * Decimal("0.15") + stats.output_tokens * Decimal("0.6")) / 1_000_000
    assert stats.estimated_cost > 0


def test_a_cache_hit_costs_nothing(pdf, tmp_path):
    run(pdf, tmp_path)
    again, _ = run(pdf, tmp_path, replies=[], pricing=PRICES)

    assert again.stats.input_tokens == again.stats.output_tokens == 0 and again.stats.estimated_cost == 0


def test_a_retried_run_costs_only_the_reply_that_arrived(pdf, tmp_path):
    from credit_intel.llm.errors import LLMTransientError
    from credit_intel.llm.retry import RetryingProvider

    class Flaky:
        def __init__(self, inner):
            self.inner, self.fail = inner, 2

        def complete(self, request):
            if self.fail:
                self.fail -= 1
                raise LLMTransientError("HTTP 503")
            return self.inner.complete(request)

    fake = FakeProvider(script=[fx.good_response(pdf)])
    clean, _ = run(pdf, tmp_path, pricing=PRICES, cache_dir=tmp_path / "a")
    retried = run_extraction(pdf, RetryingProvider(Flaky(fake), sleep=lambda _: None), fx.LLM,
                             cache_dir=tmp_path / "b", pricing=PRICES)  # fmt: skip

    assert retried.stats.llm_retries == 2 and retried.stats.estimated_cost == clean.stats.estimated_cost
