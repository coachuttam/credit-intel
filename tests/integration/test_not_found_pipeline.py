"""The reason of a source not_found through the whole extraction (PRD H.2, v0.4.75), on a synthetic balance sheet and a scripted reply."""

import json

import pytest

import pipeline_fixture as fx
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import load_prompt
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis, Status, StatusReason as R

CUR = PeriodRole.CURRENT


def run(pdf, tmp_path, reply, **kw):
    return run_extraction(pdf, FakeProvider(script=[reply]), fx.LLM, cache_dir=tmp_path / "cache", prompt=load_prompt(), **kw)


def without(pdf, *names):
    data = json.loads(fx.good_response(pdf))
    data["fields"] = [f for f in data["fields"] if f["field_name"] not in names]
    return json.dumps(data)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def reason(result, name, role=CUR):
    record = result.field_set.get(name, role)
    assert record.status is Status.NOT_FOUND
    return record.status_reason


def test_a_balance_sheet_alone_says_what_it_can_about_each_missing_field(pdf, tmp_path):
    result = run(pdf, tmp_path, fx.good_response(pdf))

    assert reason(result, F.REVENUE) is R.STATEMENT_NOT_IN_PAGES_SENT  # no income statement was sent
    assert reason(result, F.PROFIT_BEFORE_TAX) is R.STATEMENT_NOT_IN_PAGES_SENT
    assert reason(result, F.BORROWINGS_NON_CURRENT) is R.NO_RECOGNISED_ROW  # the balance sheet prints no borrowings row
    assert reason(result, F.CURRENT_MATURITIES_LONG_TERM_BORROWINGS) is R.NO_RECOGNISED_ROW


def test_a_row_the_list_accepts_that_the_model_did_not_return_is_a_recognised_row_not_read(pdf, tmp_path):
    result = run(pdf, tmp_path, without(pdf, "total_equity"))

    assert reason(result, F.TOTAL_EQUITY) is R.RECOGNISED_ROW_NOT_READ and reason(result, F.TOTAL_EQUITY, PeriodRole.COMPARATIVE) is R.RECOGNISED_ROW_NOT_READ
    assert result.field_set.get(F.CURRENT_ASSETS, CUR).status is Status.EXTRACTED  # the other fields are untouched


def test_the_reason_does_not_change_any_status_or_value(pdf, tmp_path):
    plain = run(pdf, tmp_path, fx.good_response(pdf))
    counts = plain.field_set.counts

    assert counts == {"extracted": 6, "not_found": 18, "conflicting": 0, "requires_review": 0}
    assert all(r.status_reason is None for r in plain.field_set.fields if r.status is Status.EXTRACTED)


def test_a_page_range_gives_the_same_reasons_from_the_pages_given(pdf, tmp_path):
    result = run(pdf, tmp_path, fx.good_response(pdf), page_range="1", assert_basis=StatementBasis.CONSOLIDATED)

    assert reason(result, F.REVENUE) is R.STATEMENT_NOT_IN_PAGES_SENT and reason(result, F.BORROWINGS_CURRENT) is R.NO_RECOGNISED_ROW


def test_every_not_found_record_of_a_run_has_exactly_one_of_the_three_reasons(pdf, tmp_path):
    result = run(pdf, tmp_path, without(pdf, "total_equity"))
    reasons = [r.status_reason for r in result.field_set.fields if r.status is Status.NOT_FOUND]

    assert len(reasons) == 20 and all(x in (R.STATEMENT_NOT_IN_PAGES_SENT, R.NO_RECOGNISED_ROW, R.RECOGNISED_ROW_NOT_READ) for x in reasons)
    assert {r.field_name.value for r in result.field_set.fields if r.status_reason is R.RECOGNISED_ROW_NOT_READ} == {"total_equity"}


def test_the_label_list_given_to_the_run_decides_whether_a_row_is_recognised(pdf, tmp_path):
    from dataclasses import replace

    from credit_intel.config import LabelSettings

    base = LabelSettings()
    list_without_equity = replace(base, rules={**base.rules, "total_equity": replace(base.rules["total_equity"], phrases=("shareholders funds",))})
    default = run(pdf, tmp_path / "a", without(pdf, "total_equity"))
    narrowed = run(pdf, tmp_path / "b", without(pdf, "total_equity"), label_settings=list_without_equity)

    assert reason(default, F.TOTAL_EQUITY) is R.RECOGNISED_ROW_NOT_READ and reason(narrowed, F.TOTAL_EQUITY) is R.NO_RECOGNISED_ROW


def test_the_locator_settings_given_to_a_range_run_decide_which_pages_are_the_statement(pdf, tmp_path):
    from credit_intel.config import LocatorSettings

    no_titles = LocatorSettings(title_phrases={"balance_sheet": ("nothing like this",), "income_statement": ()})
    result = run(pdf, tmp_path, without(pdf, "total_equity"), page_range="1", assert_basis=StatementBasis.CONSOLIDATED, locator_settings=no_titles)

    assert reason(result, F.TOTAL_EQUITY) is R.STATEMENT_NOT_IN_PAGES_SENT


def test_a_derived_field_never_carries_a_not_found_reason():
    from pathlib import Path

    from credit_intel.models import ExtractedField

    golden = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "results_golden.json").read_text(encoding="utf-8"))
    derived = golden["derived_fields"][0]
    assert ExtractedField.model_validate(derived).status_reason is R.MISSING_INPUT
    with pytest.raises(ValueError, match="only a source field that was not found"):
        ExtractedField.model_validate({**derived, "status_reason": "no_recognised_row"})
