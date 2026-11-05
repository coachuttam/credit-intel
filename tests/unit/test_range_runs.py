"""The statement runs of a page range (PRD v0.4.74): the locator's own page rules over the pages given, to find the page whose scale and
currency declaration a continuation page may rely on (FR-005.8). Synthetic page texts only."""

from credit_intel.extraction.runs import range_page_types, run_start
from credit_intel.ingestion.locator import page_statement_types
from credit_intel.ingestion.models import PageText

BS, IS = "balance_sheet", "income_statement"
BALANCE_SHEET = (
    "Balance Sheet as at 31 March 2025\n"
    "Total non-current assets 900.00\nTotal current assets 840.00\nTotal assets 1,740.00\nTotal equity 600.00\nBorrowings 300.00\nTotal current liabilities 1,000.00"
)
BALANCE_SHEET_CONTINUED = (
    "Equity and liabilities (continued)\n"
    "Total non-current liabilities 140.00\nBorrowings 300.00\nTotal current liabilities 1,000.00\nTotal equity and liabilities 1,740.00"
)
PROFIT_AND_LOSS = (
    "Statement of Profit and Loss for the year ended 31 March 2025\n"
    "Revenue from operations 1,482.30\nTotal income 1,510.00\nTotal expenses 1,120.00\nFinance costs 38.50\nProfit before tax 352.70\nTax expense 90.00"
)
NARRATIVE = "Directors report. The company had a good year."


def pages(**texts):
    return [PageText(int(name[1:]), text) for name, text in texts.items()]


def test_a_continuation_page_is_typed_with_the_statement_it_continues():
    types = page_statement_types(pages(p10=BALANCE_SHEET, p11=BALANCE_SHEET_CONTINUED))

    assert types == {10: (BS,), 11: (BS,)}


def test_a_continuation_page_alone_is_not_typed_because_nothing_before_it_was_given():
    assert page_statement_types(pages(p11=BALANCE_SHEET_CONTINUED)) == {}


def test_a_page_that_is_not_next_to_the_first_is_not_a_continuation():
    types = page_statement_types(pages(p10=BALANCE_SHEET, p12=BALANCE_SHEET_CONTINUED))  # page 11 was not given

    assert types == {10: (BS,)}


def test_two_statements_on_neighbouring_pages_are_typed_separately_and_a_narrative_page_has_no_type():
    types = page_statement_types(pages(p10=BALANCE_SHEET, p11=PROFIT_AND_LOSS, p12=NARRATIVE))

    assert types == {10: (BS,), 11: (IS,)}


def test_the_pages_are_taken_in_ascending_order_whatever_the_order_given():
    types = page_statement_types(list(reversed(pages(p10=BALANCE_SHEET, p11=BALANCE_SHEET_CONTINUED))))

    assert types == {10: (BS,), 11: (BS,)}


def test_no_pages_have_no_types():
    assert page_statement_types([]) == {}


def test_the_range_page_types_of_a_mapping_are_those_of_its_pages():
    mapping = {p.page_number: p for p in pages(p10=BALANCE_SHEET, p11=BALANCE_SHEET_CONTINUED)}

    assert range_page_types(mapping) == {10: (BS,), 11: (BS,)}


def test_the_run_starts_at_the_first_page_of_the_type_before_the_page_and_is_none_for_another_type():
    types = {10: (BS,), 11: (BS,), 12: (IS,), 13: (IS,)}

    assert [run_start(types, n, BS) for n in (10, 11)] == [10, 10] and [run_start(types, n, IS) for n in (12, 13)] == [12, 12]
    assert run_start(types, 11, IS) is None and run_start(types, 14, BS) is None and run_start({}, 10, BS) is None


def test_a_gap_starts_a_new_run():
    assert run_start({10: (BS,), 11: (BS,), 13: (BS,)}, 13, BS) == 13
