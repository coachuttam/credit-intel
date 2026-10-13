"""Statement page location and the statement-basis check (PRD FR-013, H.4.6)."""

import pytest

from credit_intel.config import LocatorSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import (
    check_statement_basis,
    locate_statements,
    parse_page_range,
    statement_runs,
)
from credit_intel.ingestion.models import PageText

# Synthetic page texts for PRD Appendix B, Example 5.
CONTENTS = (
    "Contents\n"
    "Balance Sheet 112\n"
    "Statement of Profit and Loss 114\n"
    "Notes to the Financial Statements 116"
)
BALANCE_SHEET = (
    "Balance Sheet as at 31 March 2025\n"
    "Total non-current assets 900.00\n"
    "Total current assets 840.00\n"
    "Total assets 1,740.00\n"
    "Total equity 600.00\n"
    "Borrowings 300.00\n"
    "Total current liabilities 1,000.00"
)
BALANCE_SHEET_CONTINUED = (
    "Equity and liabilities (continued)\n"
    "Total non-current liabilities 140.00\n"
    "Borrowings 300.00\n"
    "Total current liabilities 1,000.00\n"
    "Total equity and liabilities 1,740.00"
)
PROFIT_AND_LOSS = (
    "Statement of Profit and Loss for the year ended 31 March 2025\n"
    "Revenue from operations 1,482.30\n"
    "Total income 1,510.00\n"
    "Total expenses 1,120.00\n"
    "Finance costs 38.50\n"
    "Profit before tax 352.70\n"
    "Tax expense 90.00\n"
    "Profit for the year 262.70"
)
NOTE_21 = "Note 21 Revenue from operations\nSale of products 1,400.00"


def document(page_count: int, texts: dict[int, str]) -> list[PageText]:
    """``page_count`` physical pages; pages not in ``texts`` are blank."""
    return [PageText(n, texts.get(n, "")) for n in range(1, page_count + 1)]


def example_5() -> list[PageText]:
    return document(
        160,
        {3: CONTENTS, 112: BALANCE_SHEET, 113: BALANCE_SHEET_CONTINUED, 114: PROFIT_AND_LOSS, 160: NOTE_21},
    )


def numbers(result) -> list[int]:
    return [c.page_number for c in result.candidates]


def range_error(spec: str, page_count: int = 20, **settings) -> IngestionError:
    with pytest.raises(IngestionError) as excinfo:
        parse_page_range(spec, page_count, LocatorSettings(**settings).max_candidates)
    assert excinfo.value.code is ErrorCode.PAGE_RANGE
    return excinfo.value


# --- AC1: Appendix B, Example 5 ------------------------------------------


def test_example_5_selects_exactly_the_three_statement_pages():
    result = locate_statements(example_5())

    assert result.method == "keywords"
    assert numbers(result) == [112, 113, 114]


def test_example_5_scores_types_and_phrases():
    by_page = {c.page_number: c for c in locate_statements(example_5()).candidates}

    assert by_page[112].score == 9  # 3 x 1 title + 6 line items
    assert by_page[113].score == 5  # rule 3b; "total equity" inside "total equity and liabilities"
    assert by_page[114].score == 10  # 3 x 1 title + 7 line items
    assert by_page[112].statement_types == ("balance_sheet",)
    assert by_page[113].statement_types == ("balance_sheet",)
    assert by_page[114].statement_types == ("income_statement",)
    assert "total equity" in by_page[113].matched_phrases
    assert "balance sheet" in by_page[112].matched_phrases


def test_contents_page_with_titles_only_is_rejected():
    result = locate_statements(document(3, {3: CONTENTS}))

    assert result.candidates == ()


def test_untitled_page_below_the_untitled_threshold_is_rejected():
    # Three line items and no title: rule 3a needs a title, rule 3b needs four.
    notes = "Note 14 Borrowings\nTotal current liabilities 1,000.00\nTotal equity 600.00"

    assert locate_statements(document(1, {1: notes})).candidates == ()
    assert locate_statements(document(1, {1: "Balance Sheet\n" + notes})).candidates != ()


def test_notes_page_with_one_line_item_is_rejected():
    result = locate_statements(document(160, {160: NOTE_21}))

    assert result.candidates == ()


def test_example_5_statement_runs():
    runs = statement_runs(locate_statements(example_5()))

    assert runs == (("balance_sheet", (112, 113)), ("income_statement", (114,)))


def test_non_consecutive_pages_form_separate_runs():
    pages = document(10, {2: BALANCE_SHEET, 5: BALANCE_SHEET})

    runs = statement_runs(locate_statements(pages))

    assert runs == (("balance_sheet", (2,)), ("balance_sheet", (5,)))


# --- AC2: matching rules -------------------------------------------------


def test_matching_ignores_case_whitespace_and_compatibility_forms():
    text = (
        "BALANCE SHEET\n"  # no-break space
        "TOTAL   CURRENT\tASSETS 1\n"  # runs of whitespace
        "Total\nequity 2\n"  # phrase split across a line break
        "Proﬁt before tax 3"  # "ﬁ" ligature; not a balance-sheet phrase
    )

    candidate = locate_statements([PageText(1, text)]).candidates[0]

    assert "balance sheet" in candidate.matched_phrases
    assert "total current assets" in candidate.matched_phrases
    assert "total equity" in candidate.matched_phrases


def test_fullwidth_characters_are_normalised_before_matching():
    # Only NFKC maps fullwidth letters to ASCII; case-folding alone does not.
    text = "ＢＡＬＡＮＣＥ ＳＨＥＥＴ\nTotal current assets 1\nTotal equity 2"

    candidate = locate_statements([PageText(1, text)]).candidates[0]

    assert "balance sheet" in candidate.matched_phrases


def test_ligature_is_normalised_before_matching():
    text = "Statement of Proﬁt and Loss\nRevenue from operations 1\nProﬁt before tax 2"

    candidate = locate_statements([PageText(1, text)]).candidates[0]

    assert "statement of profit and loss" in candidate.matched_phrases
    assert "profit before tax" in candidate.matched_phrases


@pytest.mark.parametrize(
    ("text", "phrase", "present"),
    [
        ("Total equity and liabilities", "total equity", True),
        ("Total current assets", "total assets", False),
        ("Subtotal equity", "total equity", False),
        ("Total equity2", "total equity", False),
        ("3total equity", "total equity", False),
        ("(Total equity)", "total equity", True),
        ("Total equity: 600", "total equity", True),
        ("Non-current borrowings", "borrowings", True),
    ],
)
def test_phrase_presence_respects_word_boundaries(text, phrase, present):
    # A titled balance sheet page whose remaining line items are fixed, so
    # the only variable is whether ``phrase`` is present in ``text``.
    base = "Balance Sheet\nTotal non-current assets 1\nTotal liabilities\n"
    settings = LocatorSettings(min_line_items_with_title=1)

    candidates = locate_statements([PageText(1, base + text)], settings).candidates

    matched = candidates[0].matched_phrases if candidates else ()
    assert (phrase in matched) is present


def test_repeating_a_phrase_does_not_change_the_score():
    once = "Balance Sheet\nTotal equity 1\nTotal assets 2"
    many = "Balance Sheet\n" + "Total equity 1\n" * 5 + "Total assets 2"

    score_once = locate_statements([PageText(1, once)]).candidates[0].score
    score_many = locate_statements([PageText(1, many)]).candidates[0].score

    assert score_once == score_many == 3 + 2


def test_page_qualifying_for_both_types_scores_both():
    text = BALANCE_SHEET + "\n" + PROFIT_AND_LOSS

    candidate = locate_statements([PageText(1, text)]).candidates[0]

    assert candidate.statement_types == ("balance_sheet", "income_statement")
    assert candidate.score == 9 + 10


# --- AC3: ranking, ties, limit, order ------------------------------------


def test_ties_are_broken_by_the_lower_page_number():
    pages = document(9, {9: BALANCE_SHEET, 4: BALANCE_SHEET})

    result = locate_statements(pages, LocatorSettings(max_candidates=1))

    assert numbers(result) == [4]


def test_max_candidates_keeps_the_highest_scores_in_page_order():
    result = locate_statements(example_5(), LocatorSettings(max_candidates=2))

    assert numbers(result) == [112, 114]  # scores 9 and 10; page 113 (5) dropped


def test_result_never_exceeds_max_candidates_and_is_ascending():
    pages = document(30, {n: BALANCE_SHEET for n in range(30, 0, -2)})

    result = locate_statements(pages, LocatorSettings(max_candidates=4))

    assert numbers(result) == [2, 4, 6, 8]


# --- AC5: nothing to find ------------------------------------------------


@pytest.mark.parametrize(
    "pages",
    [
        [],
        document(5, {}),
        document(2, {1: "Directors' report", 2: CONTENTS}),
    ],
)
def test_no_qualifying_page_returns_an_empty_result(pages):
    result = locate_statements(pages)

    assert result.method == "keywords"
    assert result.candidates == ()
    assert result.range_pages_without_text == ()


# --- AC6: read-only and deterministic -------------------------------------


def test_pages_are_unchanged_and_results_repeat():
    pages = example_5()
    snapshot = list(pages)

    first = locate_statements(pages)
    second = locate_statements(pages)

    assert pages == snapshot
    assert first == second


# --- AC4 / rule 7: page ranges ---------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("5", (5,)),
        ("5-7", (5, 6, 7)),
        ("5-5", (5,)),
        ("110-115,120", (110, 111, 112, 113, 114, 115, 120)),
        (" 5 - 7 , 9 ", (5, 6, 7, 9)),
        ("1 - 10", tuple(range(1, 11))),
        ("1-3,2-4", (1, 2, 3, 4)),
        ("9,3,5-6", (3, 5, 6, 9)),
        ("007", (7,)),
    ],
)
def test_valid_page_ranges_parse(spec, expected):
    assert parse_page_range(spec, 120, 15) == expected


@pytest.mark.parametrize(
    "spec",
    ["", "   ", "a", "5-", "-5", "1,,2", "1,", "1-2-3", "1.5", "+3", "1 0", "²", "5–7"],
)
def test_malformed_or_empty_ranges_are_rejected(spec):
    range_error(spec)


def test_reversed_range_is_rejected():
    error = range_error("7-5")

    assert "7-5" in str(error)


@pytest.mark.parametrize("spec", ["0", "0-2", "21", "19-21"])
def test_out_of_document_ranges_are_rejected(spec):
    range_error(spec, page_count=20)


def test_range_larger_than_max_candidates_is_rejected():
    range_error("1-16", page_count=20, max_candidates=15)


def test_range_exactly_at_max_candidates_is_accepted():
    assert len(parse_page_range("1-15", 20, 15)) == 15


def test_overlapping_items_are_merged_before_the_size_check():
    assert len(parse_page_range("1-10,5-15", 20, 15)) == 15


def test_page_range_replaces_keyword_ranking():
    result = locate_statements(example_5(), page_range="160,3")

    assert result.method == "page_range"
    assert numbers(result) == [3, 160]
    assert all(c.score is None for c in result.candidates)
    assert all(c.matched_phrases == () and c.statement_types == () for c in result.candidates)


def test_invalid_range_is_rejected_by_the_locator():
    with pytest.raises(IngestionError) as excinfo:
        locate_statements(example_5(), page_range="200")

    assert excinfo.value.code is ErrorCode.PAGE_RANGE


def test_page_range_size_uses_the_configured_limit():
    with pytest.raises(IngestionError) as excinfo:
        locate_statements(example_5(), LocatorSettings(max_candidates=2), page_range="112-114")

    assert excinfo.value.code is ErrorCode.PAGE_RANGE


# --- Rule 8: text inside a page range --------------------------------------


def test_range_with_no_text_is_rejected_even_if_other_pages_have_text():
    pages = document(10, {1: BALANCE_SHEET, 9: PROFIT_AND_LOSS})

    with pytest.raises(IngestionError) as excinfo:
        locate_statements(pages, page_range="5-7")

    assert excinfo.value.code is ErrorCode.NO_TEXT_LAYER
    assert "OCR is not supported" in str(excinfo.value)


def test_whitespace_only_pages_in_a_range_count_as_without_text():
    pages = [PageText(1, "  \n\t"), PageText(2, "")]

    with pytest.raises(IngestionError) as excinfo:
        locate_statements(pages, page_range="1-2")

    assert excinfo.value.code is ErrorCode.NO_TEXT_LAYER


def test_pages_without_text_in_a_valid_range_are_kept_and_listed():
    pages = document(10, {6: BALANCE_SHEET})

    result = locate_statements(pages, page_range="5-7")

    assert numbers(result) == [5, 6, 7]
    assert result.range_pages_without_text == (5, 7)


# --- Physical page numbers, not page labels ----------------------------------


def test_candidates_and_ranges_use_physical_page_numbers(make_pdf):
    # Physical page 3 carries the page label "1".
    path = make_pdf(
        ["Cover", "Contents", BALANCE_SHEET],
        page_labels=[(0, "ROMAN_LOWER", 1), (2, "ARABIC", 1)],
    )
    pages = ingest(path).pages
    assert pages[2].page_label == "1"

    by_keywords = locate_statements(pages)
    by_range = locate_statements(pages, page_range="3")

    assert numbers(by_keywords) == [3]
    assert numbers(by_range) == [3]
    with pytest.raises(IngestionError):
        locate_statements(pages, page_range="4")  # label "2" does not exist as page 4


def test_locator_works_on_ingested_synthetic_pdf(make_pdf):
    path = make_pdf(["Contents\nBalance Sheet 2", BALANCE_SHEET, PROFIT_AND_LOSS, NOTE_21])

    result = locate_statements(ingest(path).pages)

    assert numbers(result) == [2, 3]


# --- H.4.6: statement basis ------------------------------------------------


def titled(prefix: str) -> dict[int, str]:
    return {
        1: f"{prefix}Balance Sheet as at 31 March 2025\n" + BALANCE_SHEET.split("\n", 1)[1],
        2: f"{prefix}Statement of Profit and Loss for the year ended 31 March 2025\n"
        + PROFIT_AND_LOSS.split("\n", 1)[1],
    }


def basis_error(pages, basis: str = "consolidated") -> IngestionError:
    result = locate_statements(pages)
    with pytest.raises(IngestionError) as excinfo:
        check_statement_basis(pages, result, basis)
    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE
    return excinfo.value


def test_configured_basis_present_is_accepted():
    pages = document(2, titled("Consolidated "))

    found = check_statement_basis(pages, locate_statements(pages), "consolidated")

    assert found == ("consolidated",)


def test_only_standalone_statements_with_consolidated_configured_stops():
    error = basis_error(document(2, titled("Standalone ")))

    assert "bases found: standalone" in str(error)
    assert "--basis" in str(error)


def test_standalone_basis_requested_explicitly_is_accepted():
    pages = document(2, titled("Standalone "))

    assert check_statement_basis(pages, locate_statements(pages), "standalone") == ("standalone",)


def test_separate_financial_statements_count_as_standalone():
    pages = document(2, titled("Separate "))

    assert check_statement_basis(pages, locate_statements(pages), "standalone") == ("standalone",)


def test_both_bases_present_reports_both_and_never_switches():
    pages = document(4, {**titled("Standalone "), **{n + 2: t for n, t in titled("Consolidated ").items()}})

    found = check_statement_basis(pages, locate_statements(pages), "consolidated")

    assert found == ("consolidated", "standalone")


def test_title_naming_no_basis_is_unknown_and_never_assumed():
    # OD-10 is open: an untitled-basis statement is not treated as standalone.
    error = basis_error(document(2, titled("")), basis="standalone")

    assert "bases found: unknown" in str(error)


def test_basis_word_on_a_split_title_line_is_found():
    pages = document(
        1, {1: "Consolidated Balance\nSheet as at 31 March 2025\n" + BALANCE_SHEET.split("\n", 1)[1]}
    )

    assert check_statement_basis(pages, locate_statements(pages), "consolidated") == ("consolidated",)


BS_BODY = BALANCE_SHEET.split("\n", 1)[1]


@pytest.mark.parametrize(
    ("title_block", "basis"),
    [
        ("STANDALONE\nBALANCE SHEET AS AT 31 MARCH 2025", "standalone"),  # basis line above
        ("Balance Sheet as at 31 March 2025\n(Consolidated)", "consolidated"),  # basis line below
        ("  Consolidated  \nBalance Sheet", "consolidated"),
    ],
)
def test_basis_on_an_adjacent_basis_only_line_is_part_of_the_title(title_block, basis):
    pages = document(1, {1: title_block + "\n" + BS_BODY})

    assert check_statement_basis(pages, locate_statements(pages), basis) == (basis,)


@pytest.mark.parametrize(
    "title_block",
    [
        "Consolidated Industries Limited\nBalance Sheet as at 31 March 2025",  # company name
        "Consolidated\nAnnual Report 2025\nBalance Sheet",  # basis word two lines away
        "Consolidated figures\nBalance Sheet",  # adjacent line is not basis-only
    ],
)
def test_basis_word_outside_the_title_block_is_ignored(title_block):
    error = basis_error(document(1, {1: title_block + "\n" + BS_BODY}))

    assert "bases found: unknown" in str(error)


def test_adjacent_basis_line_conflicting_with_the_title_is_unknown():
    pages = document(1, {1: "Consolidated\nStandalone Balance Sheet\n" + BS_BODY})

    error = basis_error(pages)

    assert "bases found: unknown" in str(error)


def test_absent_consolidated_evidence_is_never_read_as_standalone():
    pages = document(1, {1: "Balance Sheet as at 31 March 2025\n" + BS_BODY})

    with pytest.raises(IngestionError) as excinfo:
        check_statement_basis(pages, locate_statements(pages), "standalone")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE


def test_title_naming_both_bases_is_unknown():
    pages = document(1, {1: "Consolidated and Standalone Balance Sheet\n" + BALANCE_SHEET.split("\n", 1)[1]})

    error = basis_error(pages)

    assert "bases found: unknown" in str(error)


def test_continuation_pages_without_titles_do_not_count_as_a_basis():
    pages = document(113, {113: BALANCE_SHEET_CONTINUED})

    error = basis_error(pages)

    assert "bases found: none" in str(error)


def test_basis_word_outside_the_title_line_is_ignored():
    text = "Balance Sheet\n" + BALANCE_SHEET.split("\n", 1)[1] + "\nRefer to the consolidated notes"

    error = basis_error(document(1, {1: text}))

    assert "bases found: unknown" in str(error)


def test_basis_check_uses_page_range_candidates():
    pages = document(4, {**titled("Standalone "), **{n + 2: t for n, t in titled("Consolidated ").items()}})
    result = locate_statements(pages, page_range="1-2")

    with pytest.raises(IngestionError) as excinfo:
        check_statement_basis(pages, result, "consolidated")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE


def test_unknown_basis_setting_is_a_programming_error():
    pages = document(2, titled("Consolidated "))

    with pytest.raises(ValueError):
        check_statement_basis(pages, locate_statements(pages), "group")
