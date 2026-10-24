"""One run from a PDF to the evaluated risk indicators (PRD FR-011, FR-012.3; Phase 5 step 5c; B-257).

A synthetic balance sheet, a scripted fake provider, an injected clock and no network.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

import pipeline_fixture as fx
from credit_intel.config import LLMSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis
from credit_intel.risk.config import DEFAULT_RULES_PATH
from credit_intel.risk.results import RuleOutcome
from credit_intel.run import RunResult, run_pipeline
from credit_intel.states import FAILED, STATES, Recorder


def clock():
    moments = iter(datetime(2026, 10, 24, 9, 0, 0, tzinfo=UTC) + timedelta(milliseconds=250 * n) for n in range(1000))
    return lambda: next(moments)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def run(pdf, tmp_path, replies=None, recorder=None, **kw):
    provider = FakeProvider(script=replies if replies is not None else [fx.good_response(pdf)])
    kw.setdefault("cache_dir", tmp_path / "cache")
    recorder = recorder or Recorder(clock())
    return run_pipeline(pdf, provider, fx.LLM, recorder=recorder, **kw), provider, recorder


# --- a clean run -----------------------------------------------------------------------------------------------------------------------------------


def test_a_clean_run_goes_through_the_eight_states_to_rules_evaluated(pdf, tmp_path):
    result, provider, recorder = run(pdf, tmp_path)

    assert isinstance(result, RunResult)
    assert [e.state for e in recorder.events] == list(STATES[:8]) and recorder.final_state == "rules_evaluated"
    assert not recorder.failed and len(provider.calls) == 1


def test_every_transition_has_a_timestamp_from_the_clock_and_they_do_not_go_back(pdf, tmp_path):
    _, _, recorder = run(pdf, tmp_path)

    times = [e.at for e in recorder.events]
    assert times == sorted(times) and len(set(times)) == len(times) and all(t.tzinfo is UTC for t in times)


def test_the_extraction_result_is_carried_through_unchanged(pdf, tmp_path):
    result, _, _ = run(pdf, tmp_path)

    assert result.extraction.field_set.counts["extracted"] == 6
    assert result.extraction.source_document.sha256 == hashlib.sha256(pdf.read_bytes()).hexdigest()


def test_the_metrics_and_the_seven_rules_are_computed_from_the_verified_fields(pdf, tmp_path):
    result, _, _ = run(pdf, tmp_path)

    assert result.metrics.get("MET-03", fx_role("current")).value is not None  # current assets and liabilities were extracted
    assert [r.rule_id for r in result.rules.results] == [f"RI-00{n}" for n in range(1, 8)]
    assert result.rules.get("RI-006").outcome is RuleOutcome.TRIGGERED  # most inputs of the metrics were not on this page


def fx_role(name):
    from credit_intel.models import PeriodRole

    return PeriodRole(name)


def test_the_counts_recorded_for_the_last_two_states_match_the_results(pdf, tmp_path):
    result, _, recorder = run(pdf, tmp_path)

    calculated, rules = recorder.events[6], recorder.events[7]
    defined = sum(1 for r in result.metrics.results.values() if r.defined)
    assert calculated.counts["metrics_defined"] == defined and calculated.counts["metrics_undefined"] == len(result.metrics.results) - defined
    assert rules.counts["triggered"] + rules.counts["not_triggered"] + rules.counts["not_evaluable"] == 7 and rules.counts["disabled"] == 0


def test_the_rules_file_hash_is_recorded_for_the_manifest(pdf, tmp_path):
    result, _, _ = run(pdf, tmp_path)

    assert result.rules_sha256 == hashlib.sha256(DEFAULT_RULES_PATH.read_bytes()).hexdigest()


def test_a_second_run_with_the_same_cache_makes_no_model_call_and_gives_the_same_answer(pdf, tmp_path):
    first, p1, _ = run(pdf, tmp_path)
    second, p2, _ = run(pdf, tmp_path)

    assert len(p1.calls) == 1 and p2.calls == [] and second.extraction.stats.cache_hits == 1
    assert first.metrics.results == second.metrics.results and first.rules == second.rules


def test_the_profile_is_carried_through_and_never_changes_a_result(pdf, tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"borrower_name": "Acme", "notes": "revenue 999999999"}), encoding="utf-8")

    with_profile, _, _ = run(pdf, tmp_path, profile_path=path)
    without, _, _ = run(pdf, tmp_path)

    assert with_profile.profile.items() == (("borrower_name", "Acme"), ("notes", "revenue 999999999")) and without.profile is None
    assert with_profile.metrics.results == without.metrics.results and with_profile.rules == without.rules
    assert with_profile.extraction.field_set.counts == without.extraction.field_set.counts


# --- logging: counts only (FR-012.3) -----------------------------------------------------------------------------------------------------------------------


def test_the_log_has_one_line_per_stage_with_counts_and_no_document_text_or_values(pdf, tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        run(pdf, tmp_path)

    text = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("credit_intel"))
    for state in STATES[1:8]:
        assert f"stage={state} " in text
    for secret in ("Acme", "Total current assets", "1,482.30", "14823000000", "statement.pdf", str(tmp_path)):
        assert secret not in text


# --- failures: recorded, then raised unchanged -------------------------------------------------------------------------------------------------------------


def failure(pdf, tmp_path, **kw):
    recorder = Recorder(clock())
    provider = kw.pop("provider", None) or FakeProvider(script=[])  # a call would fail the test: none is expected
    with pytest.raises(Exception) as excinfo:
        run_pipeline(pdf, provider, fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache", **kw)
    return excinfo.value, recorder, provider


def test_a_bad_profile_fails_in_received_before_any_page_is_read_or_any_call_is_made(pdf, tmp_path):
    bad = tmp_path / "profile.json"
    bad.write_text("[]", encoding="utf-8")

    error, recorder, provider = failure(pdf, tmp_path, profile_path=bad)

    assert error.code is ErrorCode.PROFILE_INVALID and recorder.final_state == FAILED
    assert recorder.failed_stage == "received" and recorder.error_code == "E-INPUT-PROFILE-INVALID" and provider.calls == []


def test_a_bad_rules_file_fails_in_received_before_any_call(pdf, tmp_path):
    rules = tmp_path / "rules.toml"
    rules.write_text("not toml [", encoding="utf-8")

    error, recorder, provider = failure(pdf, tmp_path, rules_path=rules)

    assert error.code is ErrorCode.CONFIG_INVALID and recorder.failed_stage == "received" and provider.calls == []


def test_a_missing_input_fails_in_validated(tmp_path):
    error, recorder, provider = failure(tmp_path / "absent.pdf", tmp_path)

    assert error.code is ErrorCode.NOT_FOUND and recorder.failed_stage == "validated"  # G.1: the stage is validated
    assert recorder.state == "received" and provider.calls == []


def test_a_pdf_without_a_text_layer_fails_with_its_code_at_the_stage_reached(tmp_path):
    blank = tmp_path / "scan.pdf"
    page = canvas.Canvas(str(blank), invariant=1)
    page.showPage()
    page.save()

    error, recorder, provider = failure(blank, tmp_path)

    assert error.code is ErrorCode.NO_TEXT_LAYER and recorder.error_code == "E-INPUT-NO-TEXT-LAYER"
    assert recorder.failed_stage == "text_extracted" and recorder.state == "validated" and provider.calls == []  # valid, but no text


def test_a_document_whose_titles_name_no_basis_fails_at_the_basis_gate_before_any_call(tmp_path):
    untitled = fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")

    error, recorder, provider = failure(untitled, tmp_path)

    assert error.code is ErrorCode.BASIS_UNAVAILABLE and recorder.error_code == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert recorder.failed_stage == "statements_located" and provider.calls == []  # G.1: the gate runs while locating


def test_a_document_with_no_statement_pages_fails_in_fields_extracted(tmp_path):
    other = fx.blank_text_pdf(tmp_path / "report.pdf")

    error, recorder, _ = failure(other, tmp_path)

    assert error.code is ErrorCode.NO_STATEMENT_PAGES and recorder.failed_stage == "fields_extracted"


def test_a_model_reply_that_is_invalid_twice_fails_in_fields_extracted_with_its_code(pdf, tmp_path):
    error, recorder, provider = failure(pdf, tmp_path, provider=FakeProvider(script=["not json", "still not json"]))

    assert error.code is ErrorCode.LLM_INVALID_OUTPUT and recorder.error_code == "E-LLM-INVALID-OUTPUT"
    assert recorder.failed_stage == "fields_extracted" and len(provider.calls) == 2


class RefusedKey:
    name = "refused"

    def complete(self, request):
        raise IngestionError(ErrorCode.LLM_AUTH)


def test_an_authentication_failure_keeps_its_code(pdf, tmp_path):
    error, recorder, _ = failure(pdf, tmp_path, provider=RefusedKey())

    assert error.code is ErrorCode.LLM_AUTH and recorder.error_code == "E-LLM-AUTH" and recorder.failed_stage == "fields_extracted"


class Broken:
    name = "broken"

    def complete(self, request):
        raise RuntimeError("a bug")


def test_an_error_not_in_the_catalogue_is_recorded_as_internal_and_raised_unchanged(pdf, tmp_path):
    error, recorder, _ = failure(pdf, tmp_path, provider=Broken())

    assert isinstance(error, RuntimeError) and str(error) == "a bug"
    assert recorder.final_state == FAILED and recorder.error_code is None


def test_a_token_ceiling_that_would_be_exceeded_fails_before_the_call(pdf, tmp_path):
    recorder = Recorder(clock())
    provider = FakeProvider(script=[fx.good_response(pdf)])
    tiny = LLMSettings(provider="fake", model_id="m", token_ceiling=10, max_output_tokens=2000)

    with pytest.raises(IngestionError) as excinfo:
        run_pipeline(pdf, provider, tiny, recorder=recorder, cache_dir=tmp_path / "cache")

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED and provider.calls == [] and recorder.error_code == "E-LLM-BUDGET-EXCEEDED"


def test_a_failed_run_has_no_later_state_than_the_one_it_reached(pdf, tmp_path):
    _, recorder, _ = failure(pdf, tmp_path, provider=FakeProvider(script=["x", "y"]))

    assert [e.state for e in recorder.events] == list(STATES[:4])  # received to statements_located


def test_the_basis_option_is_passed_to_the_extraction(tmp_path):
    two = fx.two_basis_pdf(tmp_path / "two.pdf")
    reply = fx.reply(fx.good_attributes(two), [])

    result, _, _ = run(two, tmp_path, replies=[reply], basis=StatementBasis.STANDALONE)

    assert result.extraction.configured_basis is StatementBasis.STANDALONE


def test_every_failure_stage_matches_the_stage_column_of_the_error_catalogue(pdf, tmp_path):
    from credit_intel.ingestion.errors import CATALOGUE

    cases = [(ErrorCode.NOT_FOUND, tmp_path / "absent.pdf", {}), (ErrorCode.BASIS_UNAVAILABLE, fx.balance_sheet_pdf(tmp_path / "u.pdf", title="Balance Sheet"), {}),
             (ErrorCode.NO_STATEMENT_PAGES, fx.blank_text_pdf(tmp_path / "b.pdf"), {})]  # fmt: skip
    for code, document, options in cases:
        _, recorder, _ = failure(document, tmp_path, **options)
        assert recorder.failed_stage in [part.strip() for part in CATALOGUE[code].stage.split("/")], code
