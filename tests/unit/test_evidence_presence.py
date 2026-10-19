"""Evidence presence (PRD FR-005.1, FR-005.2; step 7b; B-211). Appendix B.6 row 2."""

import pytest

from credit_intel.extraction.presence import check_presence, normalise_for_match

PAGE = "Revenue from operations   1,482.30\nTotal income\t1,500.00\n  Finance costs 38.50"
PAGES = {112: PAGE, 113: "Another page"}


def check(quote, raw, page=112, pages=PAGES):
    return check_presence(pages, page, quote, raw)


# --- the quote is on the cited page (FR-005.1) -----------------------------------------------


def test_a_quote_on_the_cited_page_is_verified():
    result = check("Revenue from operations 1,482.30", "1,482.30")

    assert result.evidence_verified and result.value_in_evidence


def test_whitespace_runs_and_line_breaks_are_collapsed_on_both_sides():
    assert check("Revenue   from\noperations 1,482.30", "1,482.30").evidence_verified
    assert check("Total income 1,500.00 Finance costs 38.50", "38.50").evidence_verified


def test_unicode_is_normalised_nfkc_on_both_sides():
    pages = {1: "Café １,234.50 ﬁnance"}  # fullwidth digit, fi ligature

    assert check("Café 1,234.50 finance", "1,234.50", 1, pages).evidence_verified
    assert check("Café １,234.50 ﬁnance", "1,234.50", 1, pages).evidence_verified


def test_a_quote_may_be_a_part_of_a_line():
    assert check("1,482.30", "1,482.30").evidence_verified


def test_there_is_no_other_fuzzy_matching():
    assert not check("revenue from operations 1,482.30", "1,482.30").evidence_verified  # case
    assert not check("Revenue from operations 1,482,30", "1,482,30").evidence_verified  # punctuation
    assert not check("Revenue from operation 1,482.30", "1,482.30").evidence_verified  # a letter
    assert not check("Revenue operations 1,482.30", "1,482.30").evidence_verified  # a missing word


def test_a_quote_that_stops_inside_a_figure_is_still_on_the_page():
    # FR-005.1 asks only that the quote occur in the page text; the column check (OD-1)
    # is what ties a value to one whole cell.
    assert check("Revenue from operations 1,482.3", "1,482.3").evidence_verified


def test_b6_row_2_text_that_is_not_on_the_cited_page_is_not_verified():
    result = check("Profit before tax 352.70", "352.70")

    assert not result.evidence_verified


def test_a_quote_from_another_page_does_not_verify_on_the_cited_page():
    assert not check("Another page", "page", page=112).evidence_verified
    assert check("Another page", "page", page=113).evidence_verified


@pytest.mark.parametrize("page", [0, 999, -1])
def test_a_page_that_is_not_a_candidate_cannot_support_a_quote(page):
    assert not check("Revenue", "Revenue", page=page).evidence_verified


def test_an_empty_or_blank_quote_is_never_verified():
    assert not check("", "x").evidence_verified
    assert not check("  \n\t ", "x").evidence_verified


def test_a_blank_page_supports_nothing():
    assert not check("x", "x", 1, {1: ""}).evidence_verified


# --- the raw value is in the quote (FR-005.2) ---------------------------------------------------------


def test_a_raw_value_outside_the_quote_is_not_in_evidence():
    result = check("Revenue from operations 1,482.30", "1,356.75")

    assert result.evidence_verified and not result.value_in_evidence


def test_the_raw_value_is_compared_after_the_same_normalisation():
    assert check("Profit (245.10)  312.40", "(245.10)", 1, {1: "Profit (245.10) 312.40"}).value_in_evidence
    assert check("Cash １,234", "1,234", 1, {1: "Cash １,234"}).value_in_evidence


def test_an_empty_raw_value_is_never_in_evidence():
    assert not check("Revenue", "").value_in_evidence
    assert not check("Revenue", "  ").value_in_evidence


def test_the_two_checks_are_independent():
    result = check("Not on the page 9.99", "9.99")

    assert not result.evidence_verified and result.value_in_evidence


def test_the_raw_value_must_be_in_the_quote_not_only_on_the_page():
    assert not check("Revenue from operations", "1,482.30").value_in_evidence


def test_the_raw_value_is_found_as_a_substring_of_the_quote():
    # FR-005.2 as written; the column check (OD-1) is what ties it to one cell.
    assert check("Revenue from operations 11,482.30", "1,482.30", 1, {1: "Revenue from operations 11,482.30"}).value_in_evidence


def test_normalisation_is_idempotent_and_collapses_everything():
    assert normalise_for_match("  a   b\n\tc ") == "a b c"
    assert normalise_for_match(normalise_for_match("x  y")) == "x y"
