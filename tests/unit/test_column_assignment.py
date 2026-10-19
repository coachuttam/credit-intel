"""Assigning a proposed value to a period column (OD-1 step 6c; B-208).

PRD FR-005.7; ``docs/OD-1_period_column_proposal.md`` §3.5-§3.8 and §6. Unit tests
build ``Word`` lists directly; all data is synthetic.
"""

import random
from datetime import date
from decimal import Decimal

import pytest

from credit_intel.extraction.assignment import (
    ColumnCheck,
    ColumnClaim,
    Failure,
    Outcome,
    check_column,
)
from credit_intel.extraction.columns import PageStructure, analyse_structure
from credit_intel.ingestion.models import PageWords, Word
from credit_intel.models import StatusReason, ValueInterpretation

Y25, Y24, Y23 = date(2025, 3, 31), date(2024, 3, 31), date(2023, 3, 31)
CHAR = 5.0
LABEL, PERIOD = StatusReason.LABEL_NOT_RECOGNISED, StatusReason.PERIOD_NOT_VERIFIED


def word(text, x0, row, x1=None):
    top = 100 + 14 * row
    return Word(text, x0, x0 + CHAR * len(text) if x1 is None else x1, top, top + 10)


def page(*rows, rotation=0):
    words = [word(t, x0, i, *rest[:1]) for i, row in enumerate(rows) for t, x0, *rest in row]
    return PageWords(1, 595.0, 842.0, rotation, tuple(words))


def resolve(anchor):
    return {"2025": Y25, "2024": Y24, "2023": Y23}.get(anchor.text)


TITLE = [("Consolidated", 72), ("Balance", 150), ("Sheet", 200)]
HEADER = [("Note", 300), ("2025", 360), ("2024", 440)]  # regions 357-383 and 437-463; note 297-357
ASSETS = [("Total", 72), ("assets", 110), ("14", 305), ("1,740.00", 358), ("1,600.00", 438)]
ASSETS_QUOTE = "Total assets 14 1,740.00 1,600.00"


def structure_of(*rows, **kw) -> PageStructure:
    return analyse_structure(page(TITLE, HEADER, *rows, **kw), resolve)


def claim(raw, quote, period=Y25, label_ok=True) -> ColumnClaim:
    return ColumnClaim(period, raw, quote, label_ok)


def check(rows, raw, quote, period=Y25, label_ok=True) -> ColumnCheck:
    return check_column(structure_of(*rows), claim(raw, quote, period, label_ok))


def passes(result):
    assert result.outcome is Outcome.PASS, (result.failure, result.conditions)
    return result


# --- a value in its column -------------------------------------------------------------


def test_current_and_comparative_values_are_assigned_to_their_columns():
    current = passes(check([ASSETS], "1,740.00", ASSETS_QUOTE, Y25))
    comparative = passes(check([ASSETS], "1,600.00", ASSETS_QUOTE, Y24))

    assert (current.token.text, comparative.token.text) == ("1,740.00", "1,600.00")
    assert current.reasons == () and current.failure is None
    assert current.parsed.value == 1740 and comparative.parsed.value == 1600


def test_a_pass_records_every_condition_the_column_the_anchor_and_the_line():
    result = passes(check([ASSETS], "1,740.00", ASSETS_QUOTE))

    c = result.conditions
    assert (c.structure, c.linked, c.column, c.boundary, c.unique, c.number, c.value_matches, c.row_label) == (True,) * 8
    assert result.column.period_end == Y25
    assert [a.text for a in result.anchors] == ["2025"]
    assert result.figure_line.text == ASSETS_QUOTE
    assert [w.text for w in result.region_words] == ["1,740.00"]


def test_the_note_reference_is_never_a_value_and_does_not_unverify_the_line():
    result = check([ASSETS], "14", ASSETS_QUOTE)

    assert result.failure is Failure.VALUE_DIFFERS
    assert result.conditions.boundary is True


def test_proposing_the_comparative_figure_for_the_current_period_fails():
    result = check([ASSETS], "1,600.00", ASSETS_QUOTE, Y25)

    assert result.failure is Failure.VALUE_DIFFERS and result.reasons == (PERIOD,)
    assert result.token is None


def test_comparative_first_layout_assigns_by_period():
    header = [("2024", 360), ("2025", 440)]
    structure = analyse_structure(page(TITLE, header, ASSETS), resolve)

    current = check_column(structure, claim("1,600.00", ASSETS_QUOTE, Y25))
    comparative = check_column(structure, claim("1,740.00", ASSETS_QUOTE, Y24))

    assert current.outcome is comparative.outcome is Outcome.PASS


def test_an_unparsable_proposal_does_not_match():
    assert check([ASSETS], "abc", ASSETS_QUOTE).failure is Failure.QUOTE_NOT_LINKED
    other = [("Total", 72), ("abc", 110), ("1,740.00", 358)]
    assert check([other], "abc", "Total abc 1,740.00").failure is Failure.VALUE_DIFFERS


# --- structure and the claimed column --------------------------------------------------------


@pytest.mark.parametrize("rotation", [0, 90])
def test_invalid_structure_stops_everything_else(rotation):
    rows = [TITLE, HEADER, ASSETS] if rotation == 0 else [TITLE, HEADER, ASSETS]
    structure = analyse_structure(page(*rows, rotation=rotation), lambda a: None if rotation == 0 else resolve(a))

    result = check_column(structure, claim("1,740.00", ASSETS_QUOTE))

    assert result.failure is Failure.STRUCTURE_INVALID and result.reasons == (PERIOD,)
    assert result.conditions.structure is False
    assert result.conditions.linked is None and result.conditions.boundary is None
    assert result.figure_line is None


def test_a_page_with_no_header_has_no_columns_to_assign():
    structure = analyse_structure(page(ASSETS), resolve)

    assert check_column(structure, claim("1,740.00", ASSETS_QUOTE)).failure is Failure.STRUCTURE_INVALID


def test_a_period_with_no_column_on_the_page_is_not_assigned():
    result = check([ASSETS], "1,740.00", ASSETS_QUOTE, Y23)

    assert result.failure is Failure.NO_COLUMN and result.reasons == (PERIOD,)
    assert result.conditions.column is False and result.column is None
    assert result.figure_line is not None


def test_a_one_column_page_has_no_column_for_the_other_period():
    row = [("Total", 72), ("assets", 110), ("1,740.00", 358)]
    structure = analyse_structure(page(TITLE, [("2025", 360)], row), resolve)

    assert check_column(structure, claim("1,740.00", "Total assets 1,740.00", Y24)).failure is Failure.NO_COLUMN
    assert check_column(structure, claim("1,740.00", "Total assets 1,740.00", Y25)).outcome is Outcome.PASS


def test_a_second_figure_on_a_one_column_page_is_a_stray_token():
    structure = analyse_structure(page(TITLE, [("2025", 360)], ASSETS), resolve)

    assert check_column(structure, claim("1,740.00", ASSETS_QUOTE)).failure is Failure.LINE_UNVERIFIED


def test_a_third_year_present_leaves_the_assignments_unchanged():
    header = [("2025", 300), ("2024", 380), ("2023", 460)]
    row = [("Total", 72), ("assets", 110), ("1,740.00", 290), ("1,600.00", 370), ("1,500.00", 450)]
    structure = analyse_structure(page(TITLE, header, row), resolve)
    quote = "Total assets 1,740.00 1,600.00 1,500.00"

    tokens = [
        check_column(structure, claim(raw, quote, period)).token.text
        for raw, period in (("1,740.00", Y25), ("1,600.00", Y24), ("1,500.00", Y23))
    ]

    assert tokens == ["1,740.00", "1,600.00", "1,500.00"]


# --- linking the quote to one line (3.5) -------------------------------------------------------


def test_raw_value_on_two_quote_lines_is_ambiguous():
    result = check([ASSETS], "1,740.00", ASSETS_QUOTE + "\nTotal assets 14 1,740.00")

    assert result.failure is Failure.QUOTE_AMBIGUOUS and result.reasons == (PERIOD,)
    assert result.conditions.linked is False


def test_raw_value_missing_from_the_quote_is_not_linked():
    assert check([ASSETS], "9,999.00", ASSETS_QUOTE).failure is Failure.QUOTE_NOT_LINKED
    assert check([ASSETS], "", ASSETS_QUOTE).failure is Failure.QUOTE_NOT_LINKED


def test_two_identical_rows_on_the_page_are_ambiguous():
    result = check([ASSETS, ASSETS], "1,740.00", ASSETS_QUOTE)

    assert result.failure is Failure.FIGURE_LINE_AMBIGUOUS


def test_a_quote_that_matches_no_word_line_is_not_assigned():
    result = check([ASSETS], "1,740.00", "Total assets 1,740.00 1,600.00")  # the note reference is missing

    assert result.failure is Failure.NO_FIGURE_LINE


def test_a_label_only_quote_line_is_not_joined_to_the_figure_line():
    label_line = [("Equity", 72), ("and", 110), ("liabilities", 140)]
    quote = "Equity and liabilities\n" + ASSETS_QUOTE

    assert passes(check([label_line, ASSETS], "1,740.00", quote)).token.text == "1,740.00"


def test_quote_whitespace_and_width_forms_are_normalised_before_linking():
    quote = "Total   assets 14  １,740.00 1,600.00"

    assert passes(check([ASSETS], "1,740.00", quote)).token.text == "1,740.00"


def test_a_quote_that_is_part_of_the_page_line_is_linked_to_it():
    assert passes(check([ASSETS], "1,740.00", "1,740.00 1,600.00")).token.text == "1,740.00"


def test_a_quote_longer_than_the_page_line_is_not_linked_to_it():
    result = check([ASSETS], "1,740.00", ASSETS_QUOTE + " and more text")

    assert result.failure is Failure.NO_FIGURE_LINE


def test_the_figure_line_is_chosen_by_the_quote_not_by_the_first_row():
    other = [("Total", 72), ("equity", 110), ("600.00", 358), ("500.00", 438)]
    result = passes(check([ASSETS, other], "600.00", "Total equity 600.00 500.00"))

    assert result.figure_line.text == "Total equity 600.00 500.00" and result.token.text == "600.00"


# --- B: boundary ---------------------------------------------------------------------------------


def test_a_token_overlapping_two_regions_unverifies_the_line_for_every_column():
    row = [("Total", 72), ("assets", 110), ("1,740.00", 358), ("999,999,999", 372, 448)]
    quote = "Total assets 1,740.00 999,999,999"

    first = check([row], "1,740.00", quote, Y25)
    second = check([row], "999,999,999", quote, Y24)

    assert first.failure is second.failure is Failure.LINE_UNVERIFIED
    assert first.conditions.boundary is False and first.reasons == (PERIOD,)


@pytest.mark.parametrize("x", [400, 500])
def test_a_numeric_token_in_a_gutter_or_beyond_the_last_region_unverifies_the_line(x):
    row = [("Total", 72), ("assets", 110), ("1,740.00", 358), ("77.00", x)]
    quote = "Total assets 1,740.00 77.00"

    assert check([row], "1,740.00", quote).failure is Failure.LINE_UNVERIFIED


def test_a_short_right_aligned_nil_dash_that_misses_its_region_unverifies_the_line():
    # NT-1: documents the current result; a known loss of rows, not a requirement.
    row = [("Finance", 72), ("costs", 120), ("-", 392), ("5.00", 440)]

    assert check([row], "5.00", "Finance costs - 5.00", Y24).failure is Failure.LINE_UNVERIFIED


def test_a_token_in_the_note_span_is_a_note_reference_not_a_stray_token():
    assert check([ASSETS], "1,740.00", ASSETS_QUOTE).conditions.boundary is True


def test_a_figure_reaching_into_the_note_span_from_its_own_region_belongs_to_that_region():
    # A right-aligned figure wider than its header: 330-380 overlaps the note span
    # (297-357) and only 2025's region (357-383), so B is satisfied (FR-005.7).
    row = [("Total", 72), ("assets", 110), ("1,740.00", 330, 380), ("1,600.00", 438)]

    result = passes(check([row], "1,740.00", "Total assets 1,740.00 1,600.00"))

    assert result.token.text == "1,740.00" and result.conditions.boundary is True


def test_a_wide_figure_with_a_note_reference_beside_it_still_verifies():
    row = [("Total", 72), ("assets", 110), ("14", 305), ("1,740.00", 330, 380), ("1,600.00", 438)]

    assert passes(check([row], "1,740.00", "Total assets 14 1,740.00 1,600.00")).token.text == "1,740.00"


def test_a_token_that_reaches_into_the_note_span_and_crosses_two_period_regions_is_unverified():
    row = [("Total", 72), ("assets", 110), ("999,999,999", 330, 450)]

    assert check([row], "999,999,999", "Total assets 999,999,999").failure is Failure.LINE_UNVERIFIED


def test_a_token_wholly_or_partly_in_the_note_span_that_reaches_no_period_region_is_a_note_reference():
    row = [("Total", 72), ("assets", 110), ("14", 340, 355), ("1,740.00", 358)]

    assert passes(check([row], "1,740.00", "Total assets 14 1,740.00")).token.text == "1,740.00"


def test_a_token_that_only_touches_a_region_edge_does_not_overlap_it():
    # 2025's region is 357-383: a token starting at 383 is outside it (a stray token) ...
    right = [("Total", 72), ("assets", 110), ("1,740.00", 358), ("77.00", 383)]
    # ... and a note reference ending at 357 lies wholly in the note span.
    left = [("Total", 72), ("assets", 110), ("14", 347), ("1,740.00", 358)]

    assert check([right], "1,740.00", "Total assets 1,740.00 77.00").failure is Failure.LINE_UNVERIFIED
    assert passes(check([left], "1,740.00", "Total assets 14 1,740.00")).token.text == "1,740.00"


# --- U: uniqueness; blank cells --------------------------------------------------------------------


def test_a_blank_cell_fails_and_the_other_period_is_unchanged():
    row = [("Finance", 72), ("costs", 120), ("250.00", 435)]
    quote = "Finance costs 250.00"

    assert check([row], "250.00", quote, Y25).failure is Failure.CELL_BLANK
    assert passes(check([row], "250.00", quote, Y24)).token.text == "250.00"


def test_two_numbers_in_one_region_are_not_unique():
    row = [("Total", 72), ("assets", 110), ("1,740.00", 358), ("9.00", 380)]

    assert check([row], "1,740.00", "Total assets 1,740.00 9.00").failure is Failure.CELL_NOT_UNIQUE


def test_a_label_word_long_enough_to_reach_a_period_region_is_not_unique():
    row = [("Total", 72), ("assets-and-more-text", 110, 372), ("1,740.00", 376)]

    result = check([row], "1,740.00", "Total assets-and-more-text 1,740.00")

    assert result.failure is Failure.CELL_NOT_UNIQUE


def test_a_detached_minus_and_its_number_are_two_tokens():
    row = [("Loss", 72), ("-", 358), ("1,234", 366)]

    assert check([row], "1,234", "Loss - 1,234").failure is Failure.CELL_NOT_UNIQUE


def test_a_split_bracketed_figure_is_two_tokens():
    row = [("Loss", 72), ("(4,901", 358), (")", 382)]

    assert check([row], "(4,901", "Loss (4,901 )").failure is Failure.CELL_NOT_UNIQUE


def test_a_separate_currency_symbol_is_allowed_in_the_region():
    row = [("Cash", 72), ("$", 358, 363), ("1,234", 366)]

    assert passes(check([row], "1,234", "Cash $ 1,234")).token.text == "1,234"


def test_a_currency_symbol_attached_to_the_digits_is_not_assigned():
    # Documented OD-1 limitation (Q10): "$1,234" is not a numeric token.
    row = [("Cash", 72), ("$1,234", 358)]

    result = check([row], "$1,234", "Cash $1,234")

    assert result.failure is Failure.TOKEN_UNPARSABLE and result.reasons == (PERIOD,)


def test_other_words_in_a_region_make_it_not_unique():
    row = [("Cash", 72), ("approx", 358), ("1,234", 372)]

    assert check([row], "1,234", "Cash approx 1,234").failure is Failure.CELL_NOT_UNIQUE


# --- N: number forms ---------------------------------------------------------------------------------


def test_a_decimal_comma_figure_is_not_a_numeric_token():
    row = [("Cash", 72), ("1.234,56", 358)]

    assert check([row], "1.234,56", "Cash 1.234,56").failure is Failure.TOKEN_UNPARSABLE


@pytest.mark.parametrize(
    ("token", "raw"),
    [
        ("(245.10)", "245.10"),
        ("(245.10)", "(245.10)"),
        ("-1,234", "-1,234"),
        ("-1,234", "1,234"),
        ("\u22121,234", "\u22121,234"),
        ("\u22121,234", "1,234"),
        ("\u20131,234", "\u20131,234"),
        ("\u20131,234", "1,234"),
    ],
)
def test_brackets_and_minus_are_ignored_when_comparing_values(token, raw):
    row = [("Loss", 72), (token, 358)]

    result = passes(check([row], raw, f"Loss {token}"))

    assert result.parsed.negative_marker  # the sign check (FR-005.6) is a separate step


def test_the_proposed_value_without_the_marker_still_matches_the_token():
    row = [("Loss", 72), ("(245.10)", 358)]

    result = passes(check([row], "245.10", "Loss (245.10)"))

    assert result.token.text == "(245.10)"  # the sign check (FR-005.6) is a separate step


def test_indian_and_western_grouping_are_both_assigned_on_one_line():
    row = [("Total", 72), ("1,23,456.70", 358), ("1,234,567.89", 438)]
    quote = "Total 1,23,456.70 1,234,567.89"

    assert passes(check([row], "1,23,456.70", quote, Y25)).parsed.value == Decimal("123456.70")
    assert passes(check([row], "1,234,567.89", quote, Y24)).parsed.value == Decimal("1234567.89")


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_a_nil_dash_in_a_period_region_is_a_reported_zero(dash):
    row = [("Finance", 72), ("costs", 120), (dash, 366), ("5.00", 440)]

    result = passes(check([row], dash, f"Finance costs {dash} 5.00"))

    assert result.parsed.interpretation is ValueInterpretation.REPORTED_NIL


def test_the_word_nil_in_a_period_region_is_a_reported_zero():
    row = [("Finance", 72), ("nil", 362), ("5.00", 440)]

    assert passes(check([row], "nil", "Finance nil 5.00")).parsed.value == 0


def test_a_dash_in_the_note_region_is_ignored_and_the_values_still_assign():
    row = [("Finance", 72), ("-", 305), ("4.00", 360), ("5.00", 440)]
    quote = "Finance - 4.00 5.00"

    assert passes(check([row], "4.00", quote, Y25)).token.text == "4.00"
    assert check([row], "-", quote, Y25).failure is Failure.VALUE_DIFFERS


def test_a_dash_inside_a_label_is_ignored():
    row = [("Profit", 72), ("-", 112), ("after", 120), ("tax", 150), ("4.00", 360), ("5.00", 440)]

    assert passes(check([row], "4.00", "Profit - after tax 4.00 5.00")).token.text == "4.00"


def test_a_dash_proposed_where_the_cell_holds_a_number_does_not_match():
    row = [("Finance", 72), ("4.00", 360), ("-", 442)]

    result = check([row], "-", "Finance 4.00 -", Y25)

    assert result.failure is Failure.VALUE_DIFFERS and result.token is None


def test_a_nil_dash_is_not_matched_by_a_proposed_zero_and_a_zero_is_not_matched_by_a_dash():
    zero_then_dash = [("Finance", 72), ("0.00", 358), ("-", 442)]
    dash_then_zero = [("Finance", 72), ("-", 362), ("0.00", 438)]

    assert check([zero_then_dash], "-", "Finance 0.00 -", Y25).failure is Failure.VALUE_DIFFERS
    assert check([dash_then_zero], "0.00", "Finance - 0.00", Y25).failure is Failure.VALUE_DIFFERS
    assert passes(check([zero_then_dash], "0.00", "Finance 0.00 -", Y25)).token.text == "0.00"


# --- R: the row label; labels left of the limit -----------------------------------------------------------


def test_a_label_that_is_not_recognised_gives_no_assignment():
    result = check([ASSETS], "1,740.00", ASSETS_QUOTE, label_ok=False)

    assert result.outcome is Outcome.FAIL and result.failure is Failure.LABEL_NOT_RECOGNISED
    assert result.reasons == (LABEL,) and result.token is None and result.parsed is None
    assert result.conditions.row_label is False
    assert result.conditions.value_matches is True


def test_label_and_column_failures_are_both_reported_with_the_label_first():
    result = check([ASSETS], "1,600.00", ASSETS_QUOTE, Y25, label_ok=False)

    assert result.failure is Failure.VALUE_DIFFERS
    assert result.reasons == (LABEL, PERIOD)


def test_the_label_result_is_recorded_even_when_the_structure_is_invalid():
    structure = analyse_structure(page(ASSETS), resolve)

    result = check_column(structure, claim("1,740.00", ASSETS_QUOTE, label_ok=False))

    assert result.reasons == (LABEL, PERIOD) and result.conditions.row_label is False


MICROSOFT_ROW = [
    ("outstanding", 72),
    ("7,434", 90, 105),  # a label number wholly left of the label limit
    ("and", 108),
    ("7,434", 126, 141),
    ("109,095", 358),
    ("100,923", 438),
]
MICROSOFT_QUOTE = "outstanding 7,434 and 7,434 109,095 100,923"


def test_label_numbers_left_of_the_limit_are_never_values_but_the_figures_are_found():
    current = passes(check([MICROSOFT_ROW], "109,095", MICROSOFT_QUOTE, Y25))
    comparative = passes(check([MICROSOFT_ROW], "100,923", MICROSOFT_QUOTE, Y24))

    assert (current.token.text, comparative.token.text) == ("109,095", "100,923")
    assert current.conditions.boundary is True


def test_proposing_the_label_number_is_not_accepted():
    result = check([MICROSOFT_ROW], "7,434", MICROSOFT_QUOTE, Y25)

    assert result.failure is Failure.VALUE_DIFFERS and result.token is None


def test_end_to_end_the_wrapped_label_fragment_gives_label_not_recognised_first():
    result = check([MICROSOFT_ROW], "7,434", MICROSOFT_QUOTE, Y25, label_ok=False)

    assert result.reasons[0] is LABEL and result.outcome is Outcome.FAIL


@pytest.mark.parametrize("above", [[("24", 100)], [("Authorised", 72), ("24,000", 100, 130)]])
def test_a_label_only_line_above_is_not_joined(above):
    quote = " ".join(t for t, *_ in above) + "\n" + ASSETS_QUOTE

    assert passes(check([above, ASSETS], "1,740.00", quote)).token.text == "1,740.00"


# --- determinism ------------------------------------------------------------------------------------------


def test_results_do_not_depend_on_word_order():
    base = page(TITLE, HEADER, ASSETS)
    expected = check_column(analyse_structure(base, resolve), claim("1,740.00", ASSETS_QUOTE))
    rng = random.Random(11)
    for _ in range(10):
        words = list(base.words)
        rng.shuffle(words)
        shuffled = PageWords(1, 595.0, 842.0, 0, tuple(words))
        assert check_column(analyse_structure(shuffled, resolve), claim("1,740.00", ASSETS_QUOTE)) == expected
