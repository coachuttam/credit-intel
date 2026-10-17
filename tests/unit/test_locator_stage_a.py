"""Stage A locator amendments (PRD v0.4.6 FR-013, G.0, H.4.6; AC-E-1 to 6, 9 to 31).

Synthetic fixtures only. AC-E-7 is a process control and AC-E-8 is not part of
v0.4, so neither is tested here.
"""

import pytest

from credit_intel.config import LocatorSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.locator import (
    apply_cap_and_chains,
    check_statement_basis,
    is_figure_word,
    is_nil_token,
    is_numeric_token,
    lines_of,
    locate_statements,
    other_statement_title_lines,
    statement_runs,
    title_lines,
)
from credit_intel.ingestion.models import CandidatePage, ExcludedCandidate, PageText

NCA = "Total non-current assets"
CA = "Total current assets"
TA = "Total assets"
EQ = "Total equity"
NCL = "Total non-current liabilities"
CL = "Total current liabilities"
EL = "Total equity and liabilities"
BOR = "Borrowings"
INCOME_ITEMS = [
    "Revenue from operations",
    "Total income",
    "Total expenses",
    "Finance costs",
    "Profit before tax",
]


def page(*lines: str) -> str:
    return "\n".join(lines)


def rows(*names: str) -> list[str]:
    return [f"{name} 1,000.00" for name in names]


def doc(texts: dict[int, str], count: int | None = None) -> list[PageText]:
    count = count or max(texts)
    return [PageText(n, texts.get(n, "")) for n in range(1, count + 1)]


def located(texts: dict[int, str], **settings):
    return locate_statements(doc(texts), LocatorSettings(**settings))


def selected(result) -> list[int]:
    return [c.page_number for c in result.candidates]


def excluded(result) -> list[tuple]:
    return [
        (e.page_number, e.statement_type, e.reason, e.score, e.chain_start_page)
        for e in result.excluded_candidates
    ]


def is_title(*lines: str, settings: LocatorSettings | None = None) -> bool:
    """True if a located-type title line begins at the first of ``lines``;
    a figure line is appended below them."""
    text = page(*lines, "Total assets 1,000.00")
    return any(t.line_index == 0 for t in title_lines(text, settings))


# --- Rule 1: lines, views, G.0 tokens --------------------------------------


@pytest.mark.parametrize(
    "separator", ["\n", "\r\n", "\x0b", "\x0c", "\x85", "\x1c", "\x1d", "\x1e", " ", " ", " \n \t "]
)
def test_line_separators_split_lines(separator):
    assert lines_of(f"Balance Sheet{separator}Total assets 1,000.00") == (
        "Balance Sheet",
        "Total assets 1,000.00",
    )


def test_u001f_is_whitespace_but_not_a_line_separator():
    assert lines_of("Balance\x1fSheet") == ("Balance Sheet",)


def test_lines_collapse_whitespace_have_no_empty_lines_and_apply_nfkc():
    text = "\n\n  Total \t  assets   \n\n\n１,０００.００\n"
    assert lines_of(text) == ("Total assets", "1,000.00")


def test_crlf_gives_two_lines_without_cr_and_a_title_line():
    text = "Balance Sheet\r\nTotal assets 1,000.00"
    assert lines_of(text) == ("Balance Sheet", "Total assets 1,000.00")
    assert [t.line_index for t in title_lines(text)] == [0]


@pytest.mark.parametrize(
    ("word", "numeric", "figure"),
    [
        ("1,000.00", True, True),
        ("(1,000)", True, True),
        ("1.5", True, True),
        ("-1,234.50", True, True),
        ("−1,234.50", True, True),  # U+2212
        ("–1,234.50", True, True),  # U+2013
        ("(5)", True, True),
        ("2024", True, False),
        ("600", True, False),
        ("31,", True, False),
        ("(1", True, False),
        (")", True, False),
        ("$", False, False),
        ("₹1,000.00", False, False),
        ("1,000.00%", False, False),
        ("abc", False, False),
    ],
)
def test_numeric_tokens_and_figure_words(word, numeric, figure):
    assert is_numeric_token(word) is numeric
    assert is_figure_word(word) is figure


@pytest.mark.parametrize(
    ("word", "nil"),
    [("-", True), ("–", True), ("—", True), ("nil", True), ("NIL", True), ("Nil", True),
     ("‐", False), ("--", False), ("0", False), ("nill", False)],
)
def test_nil_tokens(word, nil):
    assert is_nil_token(word) is nil


def test_nil_figure_lines_from_the_prd_regression_list():
    assert lines_of("Net income –")[0].split(" ")[-1] == "–" and is_nil_token("–")
    assert is_nil_token(lines_of("NIL")[0])
    assert not is_nil_token("‐")


@pytest.mark.parametrize("figure", ["−1,234.50", "–1,234.50", "１,０００.００"])
def test_minus_variants_and_fullwidth_digits_make_a_figure_line(figure):
    # A title is a title line only when it lies above a figure line.
    assert [t.line_index for t in title_lines(f"Balance Sheet\nTotal assets {figure}")] == [0]


def test_a_dash_or_integer_only_page_has_no_figure_line_hence_no_title_line():
    assert title_lines("Balance Sheet\nTotal assets 600\nNet income –") == ()


def test_stored_text_is_unchanged_and_results_are_repeatable():
    pages = doc({1: page("Balance Sheet", *rows(NCA, CA))})
    before = [p.text for p in pages]
    first = locate_statements(pages)
    second = locate_statements(pages)
    assert [p.text for p in pages] == before
    assert first == second


# --- Title lines (G.0, P1-1, P1-4, P1-5) -----------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Balance Sheet",
        "BALANCE SHEETS",
        "Consolidated Balance Sheet",
        "Statement of Profit and Loss (contd.)",
        "Standalone statement of financial position as at March 31, 2025",
        "Consolidated income statements",
        "  Balance Sheet",
    ],
)
def test_title_lines(line):
    assert is_title(line)


@pytest.mark.parametrize(
    "line",
    [
        "Comprehensive income statements",  # P1-5
        "Comprehensive income statement",
        "2.28 Function-wise classification of Statement of Profit and Loss",
        "The Balance Sheet is shown below",
        "recognised in the Statement of Profit and Loss",
        "Notes to the balance sheet",
        "Balance Sheet 1,000.00",  # the line itself holds a figure word
        "Balance Sheeting",  # word boundary
    ],
)
def test_not_title_lines(line):
    assert not is_title(line)


def test_title_phrase_below_the_first_figure_line_is_not_a_title_line():
    assert title_lines(page("Total assets 1,000.00", "Balance Sheet")) == ()


def test_page_with_plain_integers_only_has_no_title_line_and_is_not_located():
    text = page("Balance Sheet", "Total assets 1", "Total equity 2")
    assert title_lines(text) == ()
    assert selected(located({1: text})) == []


def test_ac_e_12_plain_integer_page_is_selected_only_as_a_3b_continuation():
    # P1-4: no figure line, so no title line, even though a title phrase starts a line.
    plain = page(
        "Balance Sheet (contd.)",
        "Total non-current liabilities 1",
        "Total current liabilities 2",
        "Borrowings 3",
        "Total equity and liabilities 4",
    )
    statement = page("Balance Sheet", *rows(NCA, CA))
    assert title_lines(plain) == ()

    with_context = located({1: statement, 2: plain})
    assert [(c.page_number, c.statement_types) for c in with_context.candidates] == [
        (1, ("balance_sheet",)),
        (2, ("balance_sheet",)),
    ]
    assert statement_runs(with_context) == (("balance_sheet", (1, 2)),)

    # Same page without a qualifying page before it: not an independent statement.
    assert located({2: plain}).candidates == ()
    # ... and not after a page that does not qualify for the type.
    assert located({1: page("Notes 1,000.00"), 2: plain}).candidates == ()


# --- Prefix sequences (LOC-4) ----------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Consolidated & Separate Balance Sheet",
        "Consolidated and Standalone and Separate Balance Sheet",
        "Consolidated Standalone Balance Sheet",
        "Standalone and Consolidated Balance Sheet",
    ],
)
def test_prefix_sequences_are_title_lines(line):
    assert is_title(line)


@pytest.mark.parametrize(
    "line",
    [
        "Consolidated and audited Balance Sheet",
        "And Balance Sheet",
        "Consolidated and Balance Sheet",
        "Consolidated and and Standalone Balance Sheet",
        "Consolidated and Standalone and Balance Sheet",
        "& Consolidated Balance Sheet",
        "Group Balance Sheet",
    ],
)
def test_malformed_prefix_sequences_are_not_title_lines(line):
    assert not is_title(line)


def _found_bases(pages: list[PageText], page_range: str) -> str:
    """The bases found, via the configured-basis check (``unknown`` is never a
    configured basis, so the bases are read from the error detail)."""
    result = locate_statements(pages, page_range=page_range)
    try:
        return ",".join(check_statement_basis(pages, result, "consolidated"))
    except IngestionError as error:
        assert error.code is ErrorCode.BASIS_UNAVAILABLE
        return str(error.detail).split("bases found: ")[1]


def test_prefix_naming_both_bases_gives_unknown():
    for line in (
        "Consolidated & Separate Balance Sheet",
        "Consolidated and Standalone and Separate Balance Sheet",
    ):
        assert _found_bases(doc({1: page(line, *rows(NCA, CA))}), "1") == "unknown"


# LOC-4 (owner decision 2026-10-17; PRD wording pending formal revision): a
# connector between two adjacent prefix words is optional.
def test_adjacent_prefix_words_without_a_connector_form_a_prefix_sequence():
    assert is_title("Consolidated Standalone Balance Sheet")
    assert is_title("Consolidated Standalone and Separate Balance Sheet")
    assert is_title("Consolidated and Standalone Separate Balance Sheet")


def test_adjacent_prefix_words_without_a_connector_naming_both_bases_give_unknown():
    for line in (
        "Consolidated Standalone Balance Sheet",
        "Standalone Consolidated Balance Sheet",
        "Consolidated Standalone and Separate Balance Sheet",
    ):
        assert _found_bases(doc({1: page(line, *rows(NCA, CA))}), "1") == "unknown"


def test_a_single_prefix_word_without_a_connector_keeps_its_basis():
    assert _found_bases(doc({1: page("Consolidated Balance Sheet", *rows(NCA, CA))}), "1") == "consolidated"


# --- Split title lines (LOC-3) ---------------------------------------------


def test_split_title_line_is_located_at_the_first_line_and_spans_two():
    (title,) = title_lines(page("Consolidated Balance", "Sheet as at 31 March 2025", "Total assets 1,000.00"))
    assert (title.statement_type, title.line_index, title.line_count) == ("balance_sheet", 0, 2)


def test_split_title_line_across_u2028():
    text = "Consolidated Balance Sheet as at 31 March 2025\nTotal assets 1,000.00"
    (title,) = title_lines(text)
    assert (title.line_index, title.line_count) == (0, 2)


def test_split_without_prefix_and_with_a_longer_phrase():
    assert is_title("Statement of Profit and", "Loss for the year", settings=LocatorSettings())
    text = page("Statement of Profit", "and Loss", "Revenue from operations 1,000.00")
    assert [(t.statement_type, t.line_count) for t in title_lines(text)] == [("income_statement", 2)]


def test_prose_split_is_not_a_title_line():
    assert not is_title("Our balance", "sheet is strong")


def test_split_with_the_second_line_below_the_first_figure_line_is_not_a_title_line():
    text = page("Consolidated Balance", "Total assets 1,000.00", "Sheet")
    assert title_lines(text) == ()


def test_split_where_the_second_line_holds_a_figure_word_is_not_a_title_line():
    assert title_lines(page("Consolidated Balance", "Sheet 1,000.00")) == ()


def test_split_first_line_must_hold_nothing_after_the_opening_words():
    assert not is_title("Consolidated Balance of payments", "Sheet")


def test_a_split_never_spans_more_than_two_lines():
    settings = LocatorSettings(title_phrases={"balance_sheet": ("statement of financial position",)})
    assert not is_title("Statement of", "Financial", "Position", settings=settings)
    assert is_title("Statement of", "Financial Position", settings=settings)
    assert is_title("Statement of Financial", "Position", settings=settings)


def _shape(lines: list[str]) -> list[tuple[str | None, int, int]]:
    text = page(*lines, "Total assets 1,000.00")
    return [(t.statement_type, t.line_index, t.line_count) for t in title_lines(text)]


# AC-E-24 as clarified by the owner (2026-10-17; PRD wording pending formal
# revision): the three lines are not one title line, but the trailing pair is
# evaluated on its own under LOC-3 (empty prefix allowed) and may qualify.
def test_ac_e_24_three_lines_are_not_one_title_line_but_the_trailing_pair_qualifies():
    shape = _shape(["Consolidated", "Balance", "Sheet"])
    assert shape == [("balance_sheet", 1, 2)]  # nothing begins at the first line
    assert all(line_index != 0 for _, line_index, _ in shape)
    assert all(count <= 2 for _, _, count in shape)  # never more than two lines


def test_ac_e_24_basis_of_the_trailing_pair_comes_from_the_basis_only_line_above():
    pages = doc({1: page("Consolidated", "Balance", "Sheet", *rows(NCA, CA))})
    assert _found_bases(pages, "1") == "consolidated"


def test_trailing_pair_after_a_non_basis_line_is_a_title_line_with_unknown_basis():
    assert _shape(["Our company", "Balance", "Sheet"]) == [("balance_sheet", 1, 2)]
    pages = doc({1: page("Our company", "Balance", "Sheet", *rows(NCA, CA))})
    assert _found_bases(pages, "1") == "unknown"


def test_balance_over_sheet_alone_is_a_split_title_line_with_unknown_basis():
    assert _shape(["Balance", "Sheet"]) == [("balance_sheet", 0, 2)]
    assert _found_bases(doc({1: page("Balance", "Sheet", *rows(NCA, CA))}), "1") == "unknown"


def test_split_title_basis_word_on_the_first_line_is_found():
    pages = doc({1: page("Consolidated Balance", "Sheet as at 31 March 2025", *rows(NCA, CA))})
    result = locate_statements(pages)
    assert check_statement_basis(pages, result, "consolidated") == ("consolidated",)


# --- Rules 3a, 3b, 3c -------------------------------------------------------


def test_3a_titled_page_needs_no_continuation_rule():
    assert selected(located({5: page("Balance Sheet", *rows(NCA, CA))})) == [5]


def test_3a_title_with_too_few_items_is_not_selected():
    assert selected(located({5: page("Balance Sheet", *rows(NCA))})) == []


def test_untitled_page_never_qualifies_without_a_preceding_qualifying_page():
    assert selected(located({5: page(*rows(NCA, CA, TA, EQ, NCL))})) == []


def test_untitled_page_qualifies_only_as_a_3b_continuation():
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: page(*rows(NCL, CL, EL, BOR))})
    assert selected(result) == [5, 6]


def test_untitled_continuation_needs_at_least_four_items():
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: page(*rows(NCL, CL, BOR))})
    assert selected(result) == [5]


def test_titled_continuation_with_no_line_items_is_selected():
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: page("Balance Sheet (contd.)", "Note 1.00")})
    assert selected(result) == [5, 6]


def test_continuation_chain_of_three_pages():
    four = rows(NCL, CL, EL, BOR)
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: page(*four), 7: page(*four)})
    assert selected(result) == [5, 6, 7]
    assert statement_runs(result) == (("balance_sheet", (5, 6, 7)),)


def test_a_gap_of_one_page_breaks_the_chain():
    four = rows(NCL, CL, EL, BOR)
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 7: page(*four)})
    assert selected(result) == [5]


def test_chain_does_not_continue_past_a_page_that_does_not_qualify():
    four = rows(NCL, CL, EL, BOR)
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: page("nothing 1,000.00"), 7: page(*four)})
    assert selected(result) == [5]


def test_summary_page_not_following_a_statement_is_rejected():
    assert selected(located({5: page(*rows(NCA, CA, TA, EQ, NCL))})) == []


def test_page_titled_as_another_type_is_never_a_continuation():
    income = page("Statement of Profit and Loss", *rows(*INCOME_ITEMS[:3]))
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: income})
    assert [(c.page_number, c.statement_types) for c in result.candidates] == [
        (5, ("balance_sheet",)),
        (6, ("income_statement",)),
    ]
    # a different-type title line blocks 3b even where it has no 3a items
    thin = page("Statement of Profit and Loss", *rows(NCL, CL, EL, BOR))
    assert selected(located({5: page("Balance Sheet", *rows(NCA, CA)), 6: thin})) == [5]


def test_title_below_the_figures_does_not_stop_a_continuation():
    text = page(*rows(NCL, CL, EL, BOR), "Statement of Profit and Loss")
    result = located({5: page("Balance Sheet", *rows(NCA, CA)), 6: text})
    assert selected(result) == [5, 6]


# Rule 3c (LOC-1)
def test_income_title_p1_5_comprehensive_income_statements_is_not_a_title_line():
    assert not is_title("Comprehensive income statements")
    assert is_title("Consolidated income statements")


def test_other_statement_page_ends_the_chain():
    income = page("Income statements", *rows(*INCOME_ITEMS[:3]))
    other = page("Comprehensive income statements", *rows(*INCOME_ITEMS))
    untitled = page(*rows(*INCOME_ITEMS))
    result = located({1: income, 2: other, 3: untitled})
    assert selected(result) == [1]


@pytest.mark.parametrize(
    ("title_lines_", "line_count"),
    [
        (["Consolidated Comprehensive income", "statements"], 2),  # prefixed and split (LOC-3, LOC-4)
        (["Comprehensive income", "statements as at 31 March 2025"], 2),  # split
        (["Standalone comprehensive income statements"], 1),  # prefixed
    ],
)
def test_rule_3c_split_or_prefixed_other_statement_title_ends_the_chain(title_lines_, line_count):
    income = page("Income statements", *rows(*INCOME_ITEMS[:3]))
    other = page(*title_lines_, *rows(*INCOME_ITEMS))
    untitled = page(*rows(*INCOME_ITEMS))
    found = other_statement_title_lines(other)
    assert [(t.statement_type, t.line_index, t.line_count) for t in found] == [(None, 0, line_count)]

    result = located({1: income, 2: other, 3: untitled})
    assert [(c.page_number, c.statement_types) for c in result.candidates] == [(1, ("income_statement",))]
    assert result.excluded_candidates == ()  # never qualified, so never excluded

    # Control: with an ordinary untitled page in place of the other-statement
    # page, the chain runs on, so the title line is what ends it.
    control = located({1: income, 2: untitled, 3: untitled})
    assert selected(control) == [1, 2, 3]


def test_other_statement_page_may_still_qualify_under_3a():
    text = page(
        "Income statements",
        "Comprehensive income statements",
        *rows(*INCOME_ITEMS[:3]),
    )
    result = located({1: text})
    assert [(c.page_number, c.statement_types) for c in result.candidates] == [(1, ("income_statement",))]
    assert [t.statement_type for t in other_statement_title_lines(text)] == [None]


def test_other_statement_phrase_in_prose_does_not_stop_a_continuation():
    prose = page("as presented in the comprehensive income statements", *rows(*INCOME_ITEMS[:4]))
    income = page("Income statements", *rows(*INCOME_ITEMS[:3]))
    assert selected(located({1: income, 2: prose})) == [1, 2]


def test_other_statement_phrase_below_the_first_figure_line_has_no_effect():
    below = page(*rows(*INCOME_ITEMS[:4]), "Comprehensive income statements")
    income = page("Income statements", *rows(*INCOME_ITEMS[:3]))
    assert selected(located({1: income, 2: below})) == [1, 2]
    assert other_statement_title_lines(below) == ()


# --- Rule 2, rule 1(c) matching -------------------------------------------


def test_curly_apostrophe_matches_the_configured_straight_apostrophe():
    text = page("Balance Sheet", "Total stockholders’ equity 1,000.00", "Long-term debt 2,000.00")
    (candidate,) = located({1: text}).candidates
    assert "total stockholders' equity" in candidate.matched_phrases


@pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "―", "−"])
def test_dash_variants_fold_to_a_hyphen(dash):
    text = page("Balance Sheet", f"Total non{dash}current assets 1,000.00", "Total current assets 2,000.00")
    (candidate,) = located({1: text}).candidates
    assert "total non-current assets" in candidate.matched_phrases


def test_configured_phrases_go_through_the_same_folding():
    settings = LocatorSettings(line_item_phrases={"balance_sheet": ("Total Stockholders’ Equity", "Total assets")})
    result = locate_statements(
        doc({1: page("Balance Sheet", "total stockholders' equity 1,000.00", "total assets 2,000.00")}), settings
    )
    assert selected(result) == [1]


def test_v04_phrases_are_configured():
    s = LocatorSettings()
    assert "income statements" in s.title_phrases["income_statement"]
    assert "balance sheets" in s.title_phrases["balance_sheet"]
    assert s.title_prefix_words == ("consolidated", "standalone", "separate")
    assert s.prefix_connectors == ("and", "&")
    assert s.other_statement_title_phrases == ("comprehensive income statements",)
    # "finance cost" must not match "Finance costs" (word boundary)
    result = located({1: page("Income statements", *rows("Finance costs", "Total income"))})
    assert "finance cost" not in result.candidates[0].matched_phrases


# --- P1-2: cap, chain cut, excluded candidates ------------------------------

_E5 = {
    3: "Contents\nBalance Sheet 112\nStatement of Profit and Loss 114\nNotes to the Financial Statements 116",
    112: page(
        "Balance Sheet as at 31 March 2025",
        "Total non-current assets 900.00",
        "Total current assets 840.00",
        "Total assets 1,740.00",
        "Total equity 600.00",
        "Borrowings 300.00",
        "Total current liabilities 1,000.00",
    ),
    113: page(
        "Equity and liabilities (continued)",
        "Total non-current liabilities 140.00",
        "Borrowings 300.00",
        "Total current liabilities 1,000.00",
        "Total equity and liabilities 1,740.00",
    ),
    114: page(
        "Statement of Profit and Loss for the year ended 31 March 2025",
        "Revenue from operations 1,482.30",
        "Total income 1,510.00",
        "Total expenses 1,120.00",
        "Finance costs 38.50",
        "Profit before tax 352.70",
        "Tax expense 90.00",
        "Profit for the year 262.70",
    ),
    160: "Note 21 Revenue from operations\nSale of products 1,400.00",
}


def test_example_5_still_selects_112_to_114_with_the_same_scores():
    result = locate_statements(doc(_E5, 160))
    assert [(c.page_number, c.score) for c in result.candidates] == [(112, 9), (113, 5), (114, 10)]
    assert result.excluded_candidates == ()


def test_example_5_with_max_candidates_2():
    result = locate_statements(doc(_E5, 160), LocatorSettings(max_candidates=2))
    assert selected(result) == [112, 114]
    assert result.excluded_candidates == (ExcludedCandidate(113, "balance_sheet", "cap", 5, 112),)


def _chain(scores: dict[int, int]) -> dict[int, str]:
    """Pages 10..12: page 10 titled (score = 3 + items), 11 and 12 untitled
    (score = items). ``scores`` gives the intended rule-4 score of each."""
    order = [NCA, CA, TA, EQ, NCL, CL, BOR, "Total liabilities"]
    return {
        10: page("Balance Sheet", *rows(*order[: scores[10] - 3])),
        11: page(*rows(*order[: scores[11]])),
        12: page(*rows(*order[: scores[12]])),
    }


def test_ac_e_9_cap_removes_the_second_continuation():
    result = located(_chain({10: 7, 11: 5, 12: 4}), max_candidates=2)
    assert selected(result) == [10, 11]
    assert excluded(result) == [(12, "balance_sheet", "cap", 4, 10)]


def test_ac_e_9_cap_removes_the_first_continuation():
    result = located(_chain({10: 7, 11: 4, 12: 5}), max_candidates=2)
    assert selected(result) == [10]
    assert excluded(result) == [
        (11, "balance_sheet", "cap", 4, 10),
        (12, "balance_sheet", "chain_cut", 5, 10),
    ]


def test_ac_e_9_cap_removes_the_3a_page_so_the_whole_chain_goes():
    result = located(_chain({10: 5, 11: 6, 12: 7}), max_candidates=2)
    assert selected(result) == []
    assert excluded(result) == [
        (10, "balance_sheet", "cap", 5, 10),
        (11, "balance_sheet", "chain_cut", 6, 10),
        (12, "balance_sheet", "chain_cut", 7, 10),
    ]


def test_ac_e_29_cap_removes_only_page_11_and_page_13_is_not_recorded():
    texts = _chain({10: 7, 11: 4, 12: 5})
    texts[13] = page(*rows(NCA, CA, TA))  # untitled, fewer than 4 items
    result = located(texts, max_candidates=2)
    assert selected(result) == [10]
    assert excluded(result) == [
        (11, "balance_sheet", "cap", 4, 10),
        (12, "balance_sheet", "chain_cut", 5, 10),
    ]


def test_ac_e_29_cap_removes_only_page_10():
    texts = _chain({10: 5, 11: 6, 12: 7})
    texts[13] = page(*rows(NCA, CA, TA))
    result = located(texts, max_candidates=2)
    assert selected(result) == []
    assert excluded(result) == [
        (10, "balance_sheet", "cap", 5, 10),
        (11, "balance_sheet", "chain_cut", 6, 10),
        (12, "balance_sheet", "chain_cut", 7, 10),
    ]


def _ac_e_30() -> dict[int, str]:
    return {
        10: page("Balance Sheet as at 31 March 2025", *rows(NCA, CA, TA)),
        11: page("Balance Sheet (contd.)", *rows(NCL, CL, EL, BOR)),
        12: page(*rows(NCA, CA, TA, NCL, CL, EL, BOR)),
    }


def test_ac_e_30_default_cap_keeps_the_whole_chain():
    result = located(_ac_e_30())
    assert [(c.page_number, c.score) for c in result.candidates] == [(10, 6), (11, 8), (12, 8)]
    assert statement_runs(result) == (("balance_sheet", (10, 11, 12)),)
    assert result.excluded_candidates == ()


def test_ac_e_30_a_3b_page_that_is_also_3a_belongs_to_the_preceding_chain():
    result = located(_ac_e_30(), max_candidates=2)
    assert selected(result) == []
    assert excluded(result) == [
        (10, "balance_sheet", "cap", 6, 10),
        (11, "balance_sheet", "chain_cut", 8, 10),
        (12, "balance_sheet", "chain_cut", 8, 10),
    ]


def test_ac_e_31_cap_takes_precedence_over_chain_cut():
    texts = {
        10: page("Balance Sheet as at 31 March 2025", *rows(NCA, CA)),
        11: page(*rows(NCA, CA, TA, BOR)),
        12: page(*rows(NCA, CA, TA, BOR)),
        13: page(*rows(NCA, CA, TA, NCL, CL)),
    }
    result = located(texts, max_candidates=2)
    assert selected(result) == [10]
    assert excluded(result) == [
        (11, "balance_sheet", "cap", 4, 10),
        (12, "balance_sheet", "cap", 4, 10),
        (13, "balance_sheet", "chain_cut", 5, 10),
    ]
    assert len({(e.page_number, e.statement_type) for e in result.excluded_candidates}) == 3


def test_a_3a_only_page_starts_a_new_chain():
    # Page 20 (titled, 3a only; page 19 does not qualify) starts its own chain.
    texts = _chain({10: 7, 11: 5, 12: 4})
    texts[20] = page("Balance Sheet", *rows(NCA, CA))
    result = located(texts, max_candidates=3)
    assert selected(result) == [10, 11, 20]
    assert excluded(result) == [(12, "balance_sheet", "cap", 4, 10)]


def test_no_refill_after_a_chain_cut():
    texts = _chain({10: 5, 11: 6, 12: 7})
    texts[20] = page("Balance Sheet", *rows(NCA, CA))  # score 5, ranked last
    result = located(texts, max_candidates=2)
    assert 20 not in selected(result)
    assert len(result.candidates) <= 2


def test_excluded_candidates_are_ordered_deterministic_and_reuse_the_rule_4_score():
    texts = _chain({10: 5, 11: 6, 12: 7})
    first = located(texts, max_candidates=1)
    second = located(texts, max_candidates=1)
    assert first.excluded_candidates == second.excluded_candidates
    keys = [(e.page_number, e.statement_type) for e in first.excluded_candidates]
    assert keys == sorted(keys)
    uncapped = {c.page_number: c.score for c in located(texts).candidates}
    assert all(e.score == uncapped[e.page_number] for e in first.excluded_candidates)
    assert {e.statement_type for e in first.excluded_candidates} <= {"balance_sheet", "income_statement"}


def test_excluded_entries_for_two_types_are_ordered_by_page_then_statement_type():
    both = ["Balance Sheet", "Statement of Profit and Loss"]
    bs4, bs5 = [NCA, CA, TA, EQ], [NCA, CA, TA, EQ, NCL]
    is4, is5 = INCOME_ITEMS[:3] + ["Profit before tax"], INCOME_ITEMS
    texts = {
        1: page(*both, *rows(NCA, CA, *INCOME_ITEMS[:2])),  # 3a for both types, score 5 + 5
        2: page(*rows(*bs4, *is4)),  # untitled, 4 + 4 items: 3b for both types, score 8
        3: page(*rows(*bs5, *is5)),  # untitled, 5 + 5 items: 3b for both types, score 10
    }
    result = located(texts, max_candidates=2)

    assert [(c.page_number, c.statement_types, c.score) for c in result.candidates] == [
        (1, ("balance_sheet", "income_statement"), 10)
    ]
    # Page 2 is removed by the cap for both types; page 3 is kept by the cap but
    # cut from both chains. Order: ascending page, then ascending statement type.
    assert excluded(result) == [
        (2, "balance_sheet", "cap", 8, 1),
        (2, "income_statement", "cap", 8, 1),
        (3, "balance_sheet", "chain_cut", 10, 1),
        (3, "income_statement", "chain_cut", 10, 1),
    ]
    assert result == located(texts, max_candidates=2)


def test_ac_e_10_and_19_one_type_chain_cut_keeps_the_page_for_the_other_type():
    # PURE-FUNCTION TEST ONLY (provisional, owner decision 2026-10-17). It checks
    # apply_cap_and_chains on hand-built qualification inputs; it does NOT show
    # that AC-E-10 or AC-E-19 are reachable from page text, and no page-text
    # coverage is claimed. Reachability limitation: a page is a rule-3b
    # continuation for type T only if it has no title line for any other type,
    # so it can qualify for a second type U only as a 3b continuation too, and
    # then its U chain parallels its T chain. A page cut for one type only has
    # not been constructible from text under rules 3a and 3b as written.
    # Page 2 qualifies for two types; its balance-sheet chain is cut (page 1 is
    # removed by the cap), its income-statement chain is not.
    scored = {
        1: CandidatePage(1, ("balance_sheet",), 1, ()),
        2: CandidatePage(2, ("balance_sheet", "income_statement"), 9, ("x",)),
    }
    chain_start = {(1, "balance_sheet"): 1, (2, "balance_sheet"): 1, (2, "income_statement"): 2}
    candidates, excl = apply_cap_and_chains(scored, chain_start, max_candidates=1)
    assert [(c.page_number, c.statement_types, c.score) for c in candidates] == [
        (2, ("income_statement",), 9)
    ]
    assert excl == (
        ExcludedCandidate(1, "balance_sheet", "cap", 1, 1),
        ExcludedCandidate(2, "balance_sheet", "chain_cut", 9, 1),
    )


def test_matched_phrases_keep_all_detected_phrases_after_a_chain_cut():
    # Owner decision 2026-10-17 (interpretation A): matched_phrases records every
    # phrase detected on the page, including those of a type removed by
    # chain_cut. Pure-function test on hand-built inputs (see the AC-E-10/19
    # note above; this case is not reachable from page text).
    phrases = ("balance sheet", "total assets", "statement of profit and loss", "total income")
    scored = {
        1: CandidatePage(1, ("balance_sheet",), 1, ("balance sheet",)),
        2: CandidatePage(2, ("balance_sheet", "income_statement"), 9, phrases),
    }
    chain_start = {(1, "balance_sheet"): 1, (2, "balance_sheet"): 1, (2, "income_statement"): 2}
    candidates, excl = apply_cap_and_chains(scored, chain_start, max_candidates=1)
    (candidate,) = candidates
    assert candidate.statement_types == ("income_statement",)
    assert candidate.matched_phrases == phrases
    assert [(e.page_number, e.reason) for e in excl] == [(1, "cap"), (2, "chain_cut")]


def test_a_page_excluded_for_every_type_is_not_a_candidate():
    scored = {1: CandidatePage(1, ("balance_sheet",), 1, ()), 2: CandidatePage(2, ("balance_sheet",), 9, ())}
    chain_start = {(1, "balance_sheet"): 1, (2, "balance_sheet"): 1}
    candidates, excl = apply_cap_and_chains(scored, chain_start, max_candidates=1)
    assert candidates == ()
    assert [e.reason for e in excl] == ["cap", "chain_cut"]


def test_page_with_both_title_lines_above_the_figures_qualifies_for_both_types():
    text = page(
        "Balance Sheet",
        "Statement of Profit and Loss",
        *rows(NCA, CA, "Revenue from operations", "Total income"),
    )
    (candidate,) = located({1: text}).candidates
    assert candidate.statement_types == ("balance_sheet", "income_statement")
    assert candidate.score == (3 + 2) + (3 + 2)


# --- Page range (AC-E-6, AC-E-20) -------------------------------------------


def test_page_range_skips_qualification_and_records_no_exclusions():
    pages = doc({1: "", 2: page("Balance Sheet", *rows(NCA, CA)), 3: page(*rows(NCA))})
    result = locate_statements(pages, page_range="2-3")
    assert selected(result) == [2, 3]
    assert [c.statement_types for c in result.candidates] == [(), ()]
    assert result.excluded_candidates == ()


def test_page_range_rule_8_still_applies():
    with pytest.raises(IngestionError) as excinfo:
        locate_statements(doc({1: "", 2: ""}), page_range="1-2")
    assert excinfo.value.code is ErrorCode.NO_TEXT_LAYER


def test_page_range_basis_uses_title_lines_only():
    pages = doc(
        {
            1: page("Consolidated Balance Sheet", *rows(NCA, CA)),
            2: page("Balance Sheet", *rows(NCA, CA), "Standalone"),
        }
    )
    result = locate_statements(pages, page_range="2")
    with pytest.raises(IngestionError) as excinfo:
        check_statement_basis(pages, result, "consolidated")
    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE
    assert "bases found: unknown" in str(excinfo.value.detail)
    assert check_statement_basis(pages, locate_statements(pages, page_range="1-2"), "consolidated") == (
        "consolidated",
        "unknown",
    )


# --- Basis from title lines (P1-3, H.4.6; AC-E-11, 22, 26) -------------------


def _bases(*texts: str) -> str:
    return _found_bases(doc(dict(enumerate(texts, start=1))), f"1-{len(texts)}")


def test_basis_in_prose_gives_unknown_or_none():
    prose = page(
        "Statement of Profit and Loss",
        "recognised in the Consolidated Statement of Profit and Loss",
        *rows(*INCOME_ITEMS[:3]),
    )
    assert _bases(prose) == "unknown"


def test_basis_word_below_the_first_figure_line_is_ignored():
    text = page("Balance Sheet", *rows(NCA, CA), "Consolidated")
    assert _bases(text) == "unknown"


def test_title_line_with_a_basis_prefix_gives_that_basis():
    assert _bases(page("Consolidated Balance Sheet", *rows(NCA, CA))) == "consolidated"
    assert _bases(page("Standalone Balance Sheet", *rows(NCA, CA))) == "standalone"


def test_basis_only_line_directly_above_or_below_still_counts():
    assert _bases(page("(Consolidated)", "Balance Sheet", *rows(NCA, CA))) == "consolidated"
    assert _bases(page("Balance Sheet", "(Standalone)", *rows(NCA, CA))) == "standalone"


def test_basis_only_line_around_a_split_title_line():
    above = page("Standalone", "Balance", "Sheet", *rows(NCA, CA))
    below = page("Balance", "Sheet", "(Consolidated)", *rows(NCA, CA))
    assert _bases(above) == "standalone"
    assert _bases(below) == "consolidated"


def test_company_name_containing_a_basis_word_is_not_part_of_the_block():
    text = page("Consolidated Holdings Limited", "Balance Sheet", *rows(NCA, CA))
    assert _bases(text) == "unknown"


def test_page_without_a_title_line_contributes_nothing():
    pages = doc({1: page(*rows(NCA, CA)), 2: page("Consolidated", *rows(NCA, CA))})
    result = locate_statements(pages, page_range="1-2")
    with pytest.raises(IngestionError) as excinfo:
        check_statement_basis(pages, result, "consolidated")
    assert "bases found: none" in str(excinfo.value.detail)
