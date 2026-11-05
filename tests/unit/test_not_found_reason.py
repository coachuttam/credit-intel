"""The reason of a source not_found: what the code can tell of the pages sent, never that the report presents none (PRD H.2, v0.4.75). Synthetic pages only."""

import pytest

from credit_intel.config import LabelSettings
from credit_intel.extraction.missing import missing_fields
from credit_intel.extraction.notfound import not_found_reason
from credit_intel.ingestion.models import CandidatePage, LocatorResult, PageText
from credit_intel.models import NOT_FOUND_REASONS, ExtractedField, FieldName as F, Origin, SourceDocument, StatementBasis, Status, StatusReason as R, make_field_id
from datetime import date

BS, IS = "balance_sheet", "income_statement"
BALANCE_SHEET = "Consolidated Balance Sheet\nTotal non-current assets 900.00\nTotal current assets 840.00\nTotal assets 1,740.00\nTotal equity 600.00\nTotal current liabilities 1,000.00"
BALANCE_SHEET_NO_EQUITY = "Consolidated Balance Sheet\nTotal non-current assets 900.00\nTotal current assets 840.00\nTotal assets 1,740.00\nTotal current liabilities 1,000.00"
PROFIT_AND_LOSS = "Consolidated Statement of Profit and Loss\nRevenue from operations 1,482.30\nTotal income 1,510.00\nTotal expenses 1,120.00\nFinance costs 38.50\nProfit before tax 352.70\nTax expense 90.00"


def located(*pairs, method="keywords"):
    return LocatorResult(method=method, candidates=tuple(CandidatePage(n, tuple(types), 5, ()) for n, types in pairs))


def pages(**texts):
    return {int(k[1:]): PageText(int(k[1:]), t) for k, t in texts.items()}


def test_the_statement_of_the_field_is_not_among_the_pages_sent():
    result = not_found_reason(F.REVENUE, located((10, [BS])), pages(p10=BALANCE_SHEET))

    assert result is R.STATEMENT_NOT_IN_PAGES_SENT


def test_the_statement_is_sent_and_no_line_has_a_label_the_list_accepts():
    result = not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), pages(p10=BALANCE_SHEET_NO_EQUITY))

    assert result is R.NO_RECOGNISED_ROW


def test_a_recognised_row_is_on_the_statement_pages_and_the_field_was_still_not_read():
    result = not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), pages(p10=BALANCE_SHEET))

    assert result is R.RECOGNISED_ROW_NOT_READ


def test_a_heading_with_the_phrase_but_no_figure_is_not_a_row():
    text = "Consolidated Balance Sheet\nTotal equity\nTotal assets 1,740.00\nTotal current assets 840.00\nTotal current liabilities 1,000.00"

    assert not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), pages(p10=text)) is R.NO_RECOGNISED_ROW


def test_a_row_with_a_nil_dash_is_a_row():
    text = BALANCE_SHEET.replace("Total equity 600.00", "Total equity -")

    assert not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), pages(p10=text)) is R.RECOGNISED_ROW_NOT_READ


def test_a_recognised_row_on_any_statement_page_counts_and_a_row_on_a_page_of_the_other_statement_does_not():
    second = located((10, [BS]), (11, [BS]), (12, [IS]))
    texts = pages(p10=BALANCE_SHEET_NO_EQUITY, p11="Total equity 600.00\nTotal assets 1,740.00\nTotal current assets 840.00", p12=PROFIT_AND_LOSS)

    assert not_found_reason(F.TOTAL_EQUITY, second, texts) is R.RECOGNISED_ROW_NOT_READ
    other = located((10, [BS]), (12, [IS]))
    assert not_found_reason(F.TOTAL_EQUITY, other, pages(p10=BALANCE_SHEET_NO_EQUITY, p12=PROFIT_AND_LOSS + "\nTotal equity 600.00")) is R.NO_RECOGNISED_ROW


def test_each_field_is_judged_against_the_statement_it_is_read_from():
    both = located((10, [BS]), (11, [IS]))
    texts = pages(p10=BALANCE_SHEET, p11=PROFIT_AND_LOSS)

    assert not_found_reason(F.PROFIT_BEFORE_TAX, both, texts) is R.RECOGNISED_ROW_NOT_READ
    assert not_found_reason(F.OPERATING_PROFIT, both, texts) is R.NO_RECOGNISED_ROW
    assert not_found_reason(F.CURRENT_ASSETS, both, texts) is R.RECOGNISED_ROW_NOT_READ


def test_the_label_list_in_use_decides_what_is_recognised():
    texts = pages(p10=BALANCE_SHEET)
    default = not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), texts)
    from dataclasses import replace

    base = LabelSettings()
    without = replace(base, rules={**base.rules, "total_equity": replace(base.rules["total_equity"], phrases=("shareholders funds",))})

    assert default is R.RECOGNISED_ROW_NOT_READ and not_found_reason(F.TOTAL_EQUITY, located((10, [BS])), texts, without) is R.NO_RECOGNISED_ROW


def test_the_pages_of_a_range_are_typed_by_the_locators_own_rules_among_the_pages_given():
    continued = "Equity and liabilities (continued)\nTotal equity 600.00\nTotal current liabilities 1,000.00\nTotal non-current liabilities 140.00\nTotal equity and liabilities 1,740.00"
    rng = located((10, []), (11, []), method="page_range")

    assert not_found_reason(F.TOTAL_EQUITY, rng, pages(p10=BALANCE_SHEET_NO_EQUITY, p11=continued)) is R.RECOGNISED_ROW_NOT_READ
    assert not_found_reason(F.REVENUE, rng, pages(p10=BALANCE_SHEET_NO_EQUITY, p11=continued)) is R.STATEMENT_NOT_IN_PAGES_SENT
    assert not_found_reason(F.TOTAL_EQUITY, located((11, []), method="page_range"), pages(p11=continued)) is R.STATEMENT_NOT_IN_PAGES_SENT  # the continuation needs the page before it


def test_no_pages_sent_means_the_statement_is_not_in_them():
    assert not_found_reason(F.TOTAL_EQUITY, located(), {}) is R.STATEMENT_NOT_IN_PAGES_SENT


# --- the records ---------------------------------------------------------------------------------------------------------------------------


def test_missing_fields_carry_the_reason_asked_for_and_none_without_one():
    from credit_intel.extraction.attributes import VerifiedAttributes  # noqa: F401

    class Attributes:
        def period_end(self, role):
            return date(2025, 3, 31) if role.value == "current" else date(2024, 3, 31)

    doc = SourceDocument(file_name="r.pdf", sha256="a" * 64)
    with_reason = missing_fields((), Attributes(), StatementBasis.CONSOLIDATED, doc, lambda name: R.NO_RECOGNISED_ROW if name is F.REVENUE else R.STATEMENT_NOT_IN_PAGES_SENT)
    without = missing_fields((), Attributes(), StatementBasis.CONSOLIDATED, doc)

    assert {r.status_reason for r in with_reason if r.field_name is F.REVENUE} == {R.NO_RECOGNISED_ROW}
    assert {r.status_reason for r in with_reason if r.field_name is F.TOTAL_EQUITY} == {R.STATEMENT_NOT_IN_PAGES_SENT}
    assert all(r.status_reason is None for r in without) and len(with_reason) == len(without) == 24


@pytest.mark.parametrize("reason", NOT_FOUND_REASONS)
def test_only_a_source_field_that_was_not_found_may_carry_a_not_found_reason(reason):
    from calc_records import conflicting, rec

    def with_reason(record):
        return ExtractedField.model_validate({**record.model_dump(mode="json"), "status_reason": reason.value})

    assert with_reason(rec(F.REVENUE, status=Status.NOT_FOUND)).status_reason is reason
    for other in (rec(F.REVENUE, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED), conflicting(F.REVENUE, ["1", "2"]), rec(F.REVENUE, "10")):
        with pytest.raises(ValueError, match="(only a source field that was not found|no status_reason)"):
            with_reason(other)
