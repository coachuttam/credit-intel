"""Row-label check (PRD FR-005.10, D-10; H.3; step 7b; B-212)."""

from dataclasses import replace

import pytest

from credit_intel.config import CURRENT, NON_CURRENT, FieldLabelRule, LabelSettings
from credit_intel.extraction.labels import (
    check_label,
    expense_table_heading,
    normalise_label,
    row_label,
    section_heading,
    strip_item_markers,
)

# The H.3 table, spelt out: any change to the initial phrases must change this too.
H3 = {
    "revenue": ["revenue from operations", "revenue", "turnover", "total revenue"],  # "total revenue" and the four phrases below: tuning evidence R2, 2026-10-25
    "net_profit": [
        "profit/(loss) for the year",
        "profit for the year",
        "profit/(loss) for the period",
        "profit for the period",
        "net income",
    ],
    "operating_profit": ["operating profit", "ebit", "operating income"],
    "profit_before_tax": ["profit/(loss) before tax", "profit before tax", "income before income taxes"],
    "interest_expense": ["finance costs", "finance cost", "interest expense"],  # "finance cost" from tuning evidence, 2026-10-22
    "current_assets": ["total current assets"],
    "current_liabilities": ["total current liabilities"],
    "total_borrowings": ["total borrowings"],
    "borrowings_non_current": ["non-current borrowings"],
    "borrowings_current": ["current borrowings"],
    "current_maturities_long_term_borrowings": [
        "current maturities of long-term borrowings",
        "current maturities of long-term debt",
    ],
    "total_equity": ["total equity", "total stockholders' equity"],
}


def ok(field, line, lines=None, index=None):
    return check_label(field, line, lines, index).ok


# --- the initial phrases are the H.3 table --------------------------------------------------------


def test_the_initial_phrases_are_the_h3_table_plus_the_tuning_additions():
    rules = LabelSettings().rules

    assert {name: list(rule.phrases) for name, rule in rules.items()} == H3
    assert rules["borrowings_non_current"].sectioned_phrases == ("borrowings",)
    assert rules["borrowings_non_current"].section == NON_CURRENT
    assert rules["borrowings_current"].sectioned_phrases == ("borrowings",)
    assert rules["borrowings_current"].section == CURRENT
    assert all(not r.sectioned_phrases for n, r in rules.items() if not n.startswith("borrowings_"))


@pytest.mark.parametrize(("field", "phrase"), [(f, p) for f, ps in H3.items() for p in ps])
def test_every_h3_phrase_is_accepted_for_its_field(field, phrase):
    assert ok(field, f"{phrase.capitalize()} 14 1,482.30 1,356.75")
    assert ok(field, phrase.upper() + " 1,482.30")


@pytest.mark.parametrize(
    ("field", "line"),
    [
        ("revenue", "Other income 1,482.30"),
        ("revenue", "Total income 1,482.30"),
        ("revenue", "Total revenue and other income 1,482.30"),
        ("net_profit", "Net income before tax 1.00"),
        ("operating_profit", "Operating income and other 1.00"),
        ("profit_before_tax", "Income before income taxes and other 1.00"),
        ("total_equity", "Total stockholders' equity and liabilities 1.00"),
        ("revenue", "Revenue from operations (Refer note 28) 1,482.30"),
        ("revenue", "Revenue from operations and other income 1,482.30"),
        ("net_profit", "Profit before tax 1.00"),
        ("current_assets", "Total non-current assets 1.00"),
        ("current_assets", "Current assets 1.00"),
        ("current_liabilities", "Total non-current liabilities 1.00"),
        ("total_equity", "Total equity and liabilities 1.00"),
        ("total_equity", "Equity 1.00"),
        ("total_borrowings", "Borrowings 1.00"),
        ("interest_expense", "Finance income 1.00"),
        ("current_maturities_long_term_borrowings", "Current maturities 1.00"),
        ("ebit", "Operating profit 1.00"),
        ("not_a_field", "Revenue 1.00"),
    ],
)
def test_other_labels_are_not_accepted(field, line):
    assert not ok(field, line)


@pytest.mark.parametrize("apostrophe", ["'", "\u2019"])
def test_the_stockholders_equity_label_is_accepted_with_a_straight_or_a_curly_apostrophe(apostrophe):
    assert ok("total_equity", f"Total stockholders{apostrophe} equity 1,482.30 1,356.75")


def test_a_label_is_not_accepted_for_a_different_field():
    assert not ok("revenue", "Total equity 600.00")
    assert not ok("total_equity", "Revenue from operations 600.00")


# --- the label is the text before the first figure -------------------------------------------------------


def test_the_label_ends_at_the_first_figure():
    assert row_label("Total current assets 14 1,482.30 1,356.75") == "Total current assets"
    assert row_label("Total current assets 1,482.30 14") == "Total current assets"


def test_a_note_reference_counts_as_a_figure():
    assert ok("current_assets", "Total current assets 14 1,482.30 1,356.75")
    assert row_label("Total equity 5 600.00") == "Total equity"


def test_a_nil_dash_or_nil_counts_as_a_figure():
    for nil in ("-", "–", "—", "nil", "NIL"):
        assert row_label(f"Finance costs {nil} 5.00") == "Finance costs"
        assert ok("interest_expense", f"Finance costs {nil} 5.00")


def test_bracketed_numbers_and_a_lone_bracket_count_as_figures():
    assert row_label("Loss (245.10) 312.40") == "Loss"
    assert row_label("Loss 5) x") == "Loss"


def test_a_line_with_no_figure_is_all_label():
    assert row_label("Total equity") == "Total equity"
    assert ok("total_equity", "Total equity")


def test_a_number_inside_the_label_ends_it():
    assert row_label("Revenue from operations (note 28) 1,482.30") == "Revenue from operations (note"
    assert not ok("revenue", "Revenue from operations (Refer note 28) 1,482.30")
    assert row_label("Borrowings 2025 5.00") == "Borrowings"


def test_the_label_check_reports_what_it_compared():
    result = check_label("revenue", "I. Revenue from Operations 14 1,482.30")

    assert result.label == "I. Revenue from Operations"
    assert result.normalised == "revenue from operations"
    assert result.matched_phrase == "revenue from operations"


# --- normalisation: FR-013 rule 1 folding and item markers ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Revenue from Operations", "revenue from operations"),
        ("  Revenue   from operations ", "revenue from operations"),
        ("Profit/(Loss) for the year", "profit/(loss) for the year"),
        ("Non‐current borrowings", "non-current borrowings"),
        ("Non−current borrowings", "non-current borrowings"),
        ("Long’term debt", "long'term debt"),
        ("Ｔotal equity", "total equity"),
    ],
)
def test_labels_are_folded_like_the_locator_phrases(raw, expected):
    assert normalise_label(raw) == expected


@pytest.mark.parametrize(
    "label",
    [
        "I. Revenue from operations",
        "I Revenue from operations",
        "i) Revenue from operations",
        "(i) Revenue from operations",
        "(a) Revenue from operations",
        "a. Revenue from operations",
        "a Revenue from operations",
        "1. Revenue from operations",
        "XIV. Revenue from operations",
        "(i) (a) Revenue from operations",
        "I. 1. Revenue from operations",
        "Revenue from operations",
    ],
)
def test_leading_item_markers_are_removed(label):
    assert normalise_label(label) == "revenue from operations"
    assert ok("revenue", label + " 1,482.30")


@pytest.mark.parametrize(
    "label",
    [
        "(a)Revenue from operations",  # no space after the marker
        "Revenue from operations (a)",  # a trailing marker is part of the label
        "( i ) Revenue from operations",  # a lone ")" is a numeric token, so it ends the label
        "1) Revenue from operations",  # "1)" is a numeric token (a note reference counts as a figure)
        "(1) Revenue from operations",
        "12 Revenue from operations",  # a bare number is a figure, so the label is empty
        "ii",
        "(a)",
        "I.",
        "-",
        "",
    ],
)
def test_forms_that_cannot_be_read_as_marker_plus_label_fail_safe(label):
    # FR-005.10 cuts the label at the first figure before removing markers, so a digit
    # marker that is itself a numeric token ends the label and the row is not accepted.
    assert not ok("revenue", label + " 1,482.30")


def test_only_markers_leaves_nothing_to_match():
    assert strip_item_markers("(a)") == ""
    assert strip_item_markers("i.") == ""
    assert not ok("revenue", "(a)")


def test_words_that_start_like_markers_are_not_stripped():
    assert strip_item_markers("interest expense") == "interest expense"
    assert strip_item_markers("total equity") == "total equity"
    assert strip_item_markers("current borrowings") == "current borrowings"
    assert strip_item_markers("ebit") == "ebit"
    assert strip_item_markers("operating profit") == "operating profit"


# --- borrowings: a bare "borrowings" needs its section heading ------------------------------------------------


NON_CURRENT_PAGE = [
    "Equity and liabilities",
    "Non-current liabilities",
    "Financial liabilities",
    "Borrowings 14 500.00 450.00",
    "Total non-current liabilities 500.00 450.00",
    "Current liabilities",
    "Financial liabilities",
    "Borrowings 15 120.00 100.00",
    "Total current liabilities 120.00 100.00",
]


def test_borrowings_under_the_non_current_heading_is_non_current_only():
    assert ok("borrowings_non_current", NON_CURRENT_PAGE[3], NON_CURRENT_PAGE, 3)
    assert not ok("borrowings_current", NON_CURRENT_PAGE[3], NON_CURRENT_PAGE, 3)


def test_borrowings_under_the_current_heading_is_current_only():
    assert ok("borrowings_current", NON_CURRENT_PAGE[7], NON_CURRENT_PAGE, 7)
    assert not ok("borrowings_non_current", NON_CURRENT_PAGE[7], NON_CURRENT_PAGE, 7)


def test_the_check_reports_the_section_it_found():
    assert check_label("borrowings_current", NON_CURRENT_PAGE[7], NON_CURRENT_PAGE, 7).section == CURRENT
    assert check_label("borrowings_non_current", NON_CURRENT_PAGE[3], NON_CURRENT_PAGE, 3).section == NON_CURRENT


def test_the_explicit_labels_need_no_heading():
    assert ok("borrowings_current", "Current borrowings 5.00")
    assert ok("borrowings_non_current", "Non-current borrowings 5.00")
    assert not ok("borrowings_current", "Non-current borrowings 5.00")


def test_a_bare_borrowings_with_no_page_context_is_not_accepted():
    assert not ok("borrowings_current", "Borrowings 5.00")
    assert not ok("borrowings_current", "Borrowings 5.00", NON_CURRENT_PAGE, None)
    assert not ok("borrowings_current", "Borrowings 5.00", None, 3)


def test_no_heading_above_on_the_page_is_not_accepted():
    lines = ["Particulars Note 2025 2024", "Borrowings 5.00"]

    assert section_heading(lines, 1) is None
    assert not ok("borrowings_current", lines[1], lines, 1)


def test_a_total_of_liabilities_met_first_ends_the_section():
    lines = [
        "Non-current liabilities",
        "Borrowings 14 500.00",
        "Total non-current liabilities 500.00",
        "Borrowings 15 120.00",  # the heading of this section is not on the page
    ]

    assert section_heading(lines, 3) is None
    assert section_heading(lines, 1) == NON_CURRENT


def test_the_nearest_heading_wins():
    lines = ["Current liabilities", "Trade payables 5.00", "Non-current liabilities", "Borrowings 5.00"]

    assert section_heading(lines, 3) == NON_CURRENT


def test_headings_may_carry_markers_and_a_colon_but_must_otherwise_be_exact():
    for heading in ("II. Current liabilities", "(b) Current liabilities:", "CURRENT LIABILITIES"):
        assert section_heading([heading, "Borrowings 5.00"], 1) == CURRENT
    for heading in ("Total current liabilities", "Current liabilities (contd.)", "Other current liabilities"):
        assert section_heading([heading, "Borrowings 5.00"], 1) is None


def test_item_rows_between_the_heading_and_the_row_are_skipped():
    lines = ["Current liabilities", "Trade payables 12 5.00 4.00", "Other payables 6.00", "Borrowings 7.00"]

    assert section_heading(lines, 3) == CURRENT


def test_the_row_itself_is_never_its_own_heading():
    assert section_heading(["Current liabilities 5.00"], 0) is None


# --- settings are replaceable ------------------------------------------------------------------------------------


def test_configured_phrases_replace_the_defaults():
    settings = LabelSettings(rules={"revenue": FieldLabelRule(("net sales",))})

    assert check_label("revenue", "Net sales 1.00", settings=settings).ok
    assert not check_label("revenue", "Revenue 1.00", settings=settings).ok
    assert not check_label("total_equity", "Total equity 1.00", settings=settings).ok


def test_configured_headings_are_used():
    settings = LabelSettings(section_headings={CURRENT: ("short-term liabilities",)})

    assert section_heading(["Short-term liabilities", "Borrowings 1.00"], 1, settings) == CURRENT
    assert section_heading(["Current liabilities", "Borrowings 1.00"], 1, settings) is None


def test_the_singular_finance_cost_row_of_a_real_statement_is_accepted_and_look_alikes_are_not():
    # Tuning-set evidence (R1, consolidated statement of profit and loss): "Finance cost 416 470".
    assert ok("interest_expense", "Finance cost 416 470")
    assert not ok("interest_expense", "Finance income 416 470")
    assert not ok("interest_expense", "Finance costs and other charges 416 470")
    assert not ok("operating_profit", "Finance cost 416 470")


# --- a lone currency sign before the first figure is not part of the label (PRD FR-005.10, v0.4.29; B.6 rows 66 and 67) --------


@pytest.mark.parametrize("sign", ["$", "₹", "€", "£", "¥"])
def test_b6_row_66_a_currency_sign_between_the_label_and_the_first_figure_is_not_part_of_the_label(sign):
    result = check_label("net_profit", f"Net income {sign} 1,482.30 {sign} 1,356.75")

    assert result.ok and result.matched_phrase == "net income"
    assert result.label == f"Net income {sign}"  # the label as printed is kept for the record
    assert result.normalised == "net income"


def test_the_sign_is_dropped_for_every_field_that_has_a_phrase():
    for field_name, phrases in H3.items():
        for phrase in phrases:
            assert check_label(field_name, f"{phrase.capitalize()} $ 1,482.30").ok, (field_name, phrase)


@pytest.mark.parametrize(
    "line",
    [
        "Net income $ before tax 1.00",  # the sign is not the last word
        "Net income USD 1.00",  # a code is not a symbol
        "Net income US$ 1.00",  # nor is a symbol that starts with letters
        "Net income dollars 1.00",  # nor a name
        "Net income Rs. 1.00",
        "Net $ income 1.00",  # a sign inside the label
        "$ Net income 1.00",  # a sign at the start
        "Net income $ $ 1.00",  # only one trailing word is removed
    ],
)
def test_b6_row_67_other_signs_and_trailing_words_leave_the_label_as_printed(line):
    assert not check_label("net_profit", line).ok


def test_a_label_that_is_only_a_sign_is_not_emptied():
    result = check_label("revenue", "$ 1,482.30")

    assert not result.ok and result.label == "$" and result.normalised == "$"


def test_the_sign_rule_follows_the_settings():
    result = check_label("net_profit", "Net income $ 1.00", settings=replace(LabelSettings(), currency_symbols=()))

    assert not result.ok


def test_the_currency_symbols_are_the_non_alphabetic_currency_tokens():
    assert set(LabelSettings().currency_symbols) == {"$", "₹", "€", "£", "¥"}


def test_a_section_heading_row_is_not_affected_by_the_sign_rule():
    assert section_heading(["Current liabilities: $", "Borrowings 1.00"], 1, LabelSettings()) is None


def test_the_sign_before_a_nil_dash_or_a_note_reference_is_dropped_too():
    assert check_label("total_equity", "Total equity $ - 1.00").ok
    assert check_label("total_equity", "Total equity 14 $ 600.00 $ 500.00").ok  # the note reference ends the label before any sign


# --- the heading of an income-and-expense table (PRD v0.4.33, FR-006.5) -----------------------------------------------------------------


NOTE = ["NOTE 3 - OTHER INCOME (EXPENSE), NET", "(In millions)", "Year Ended June 30, 2025 2024", "Interest and dividends income 4,100 3,900", "Interest expense (2,385) (2,935)"]


@pytest.mark.parametrize(
    "heading",
    ["Other income (expense), net", "OTHER INCOME (EXPENSE)", "(Expense)/income", "Income/(expense) summary", "(Expense) income, net", "Income and expense", "Other income and expense"],
)
def test_each_configured_phrase_marks_the_heading(heading):
    assert expense_table_heading([heading, "Interest expense (1.00)"], 1)


def test_a_heading_with_a_note_number_or_a_year_still_counts_because_neither_is_a_figure():
    assert expense_table_heading(NOTE, 4)


@pytest.mark.parametrize("heading", ["Finance costs", "Other income", "Income (net of expense)", "Expenses", "Statement of profit and loss"])
def test_other_headings_do_not(heading):
    assert not expense_table_heading([heading, "Interest expense (1.00)"], 1)


def test_a_line_with_a_figure_is_a_row_not_a_heading():
    assert not expense_table_heading(["Other income (expense), net 4,100.00", "Interest expense (1.00)"], 1)


def test_only_the_window_above_the_row_is_looked_at():
    lines = ["Other income (expense), net", *["a sentence without a figure"] * 8, "Interest expense (1.00)"]

    assert not expense_table_heading(lines, 9) and expense_table_heading(lines, 8)
    assert expense_table_heading(lines, 9, replace(LabelSettings(), expense_heading_window=9))


def test_a_phrase_after_the_row_or_on_the_row_itself_does_not_count():
    assert not expense_table_heading(["Interest expense (1.00)", "Other income (expense), net"], 0)
    assert not expense_table_heading(["Interest expense (1.00)", "Other income (expense), net"], 1 - 1)


def test_the_phrases_are_a_setting_and_an_empty_list_turns_the_rule_off():
    off = replace(LabelSettings(), expense_table_headings=())

    assert not expense_table_heading(NOTE, 4, off) and expense_table_heading(NOTE, 4)
