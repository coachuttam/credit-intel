"""Joining the pieces of a figure the PDF library reported as several words (PRD FR-005.7, v0.4.35; Appendix B.6 rows 86 to 95; B-306).

Synthetic words only. The region is the claimed column's (x 100 to 130 here); a word outside it is another column's.
"""

import pytest

from credit_intel.extraction.assignment import (
    DEFAULT_SPLIT_FIGURE_GAP_PT,
    ColumnClaim,
    Failure,
    Outcome,
    _raw_without_join_spaces,
    check_column,
    join_split_figures,
)
from credit_intel.extraction.columns import analyse_structure
from credit_intel.extraction.normalise import parse_value
from datetime import date
from credit_intel.extraction.declarations import check_sign
from credit_intel.ingestion.models import PageWords, Word

X0, X1 = 100.0, 130.0


def w(text, x0, x1=None):
    return Word(text, x0, x0 + 5.0 * len(text) if x1 is None else x1, 10.0, 20.0)


def joined(words, gap=2.0):
    out, pieces = join_split_figures(words, X0, X1, gap)
    return [word.text for word in out], [list(chain) for chain in pieces]


# --- what is joined ---------------------------------------------------------------------------------------------------------------


def test_b6_row_86_a_thousands_group_split_off_touching_is_joined():
    assert joined([w("88,", 105, 115), w("136", 115, 130)]) == (["88,136"], [["88,", "136"]])


def test_b6_row_87_a_closing_bracket_split_off_a_little_apart_is_joined():
    assert joined([w("(2,385", 100, 124), w(")", 124.7, 128)]) == (["(2,385)"], [["(2,385", ")"]])


def test_the_joined_word_spans_from_the_first_piece_to_the_last_and_keeps_the_line_height():
    (word,), _ = join_split_figures([w("88,", 105, 115), w("136", 115.5, 130)], X0, X1, 2.0)

    assert (word.text, word.x0, word.x1, word.top, word.bottom) == ("88,136", 105, 130, 10.0, 20.0)


def test_b6_row_93_a_figure_in_three_pieces_is_joined_whole_and_a_far_last_piece_stops_all_of_it():
    assert joined([w("1,", 102, 107), w("24,", 107, 119), w("936", 119, 130)]) == (["1,24,936"], [["1,", "24,", "936"]])
    assert joined([w("1,", 102, 107), w("24,", 107, 119), w("936", 122, 130)]) == (["1,", "24,", "936"], [])  # 3 pt: the chain does not end


def test_words_are_returned_in_order_with_the_others_untouched():
    words = [w("Interest", 10, 40), w("(2,385", 100, 124), w(")", 124.5, 128), w("(2,935", 141, 165), w(")", 165.4, 169)]

    out, pieces = join_split_figures(words, X0, X1, 2.0)

    assert [x.text for x in out] == ["Interest", "(2,385)", "(2,935", ")"] and pieces == (("(2,385", ")"),)  # the next column's pieces are not touched


# --- what is not joined ------------------------------------------------------------------------------------------------------------


def test_b6_row_88_a_gap_over_the_setting_is_not_joined():
    assert joined([w("(2,385", 100, 124), w(")", 126.5, 130)]) == (["(2,385", ")"], [])
    assert joined([w("(2,385", 100, 124), w(")", 126.0, 130)]) == (["(2,385)"], [["(2,385", ")"]])  # exactly the setting still joins


def test_b6_row_89_figures_of_adjacent_columns_are_never_merged_whatever_the_gap():
    # The first piece ends exactly where the claimed region ends and the next column's figure starts 0.5 pt later: close enough to
    # join by distance, but the second word is outside the claimed region, so it belongs to the next column.
    assert joined([w("1,", 120, 130), w("234", 130.5, 145)]) == (["1,", "234"], [])
    assert joined([w("100", 105, 128), w("200", 128.5, 150)]) == (["100", "200"], [])  # and two complete figures are never joined anyway


def test_b6_row_90_a_bracket_in_the_next_columns_region_is_not_joined_to_the_figure_before_it():
    out, pieces = join_split_figures([w("(2,385", 100, 124), w(")", 130.5, 134)], X0, X1, 8.0)  # ")" starts after the region ends; 6.5 pt is within the setting

    assert [x.text for x in out] == ["(2,385", ")"] and pieces == ()
    out, pieces = join_split_figures([w("(2,385", 100, 124), w(")", 126, 129)], X0, X1, 8.0)  # the same bracket inside the region joins

    assert [x.text for x in out] == ["(2,385)"] and pieces == (("(2,385", ")"),)


def test_b6_row_91_two_complete_figures_touching_in_one_column_are_not_joined():
    assert joined([w("100", 100, 115), w("200", 115, 130)]) == (["100", "200"], [])


def test_the_pieces_must_be_a_figure_together():
    assert joined([w("88,", 105, 115), w("13a", 115, 130)]) == (["88,", "13a"], [])  # b6 row 92
    assert joined([w("88,", 105, 115), w("13,", 115, 125), w("5", 125, 130)]) == (["88,", "13,", "5"], [])  # "88,13,5" is not a figure: the chain is left as it was


def test_a_footnote_mark_touching_a_figure_is_not_joined_to_it():
    # "88,136" with a superscript "1": the figure is complete before the mark, so the mark stays a word of its own (b6 row 95).
    out, pieces = join_split_figures([w("88,", 100, 110), w("136", 110, 124), w("1", 124.2, 128)], X0, X1, 2.0)

    assert [x.text for x in out] == ["88,136", "1"] and pieces == (("88,", "136"),)


def test_a_mark_touching_a_whole_figure_is_not_joined_either():
    assert joined([w("88,136", 100, 124), w("1", 124.2, 128)]) == (["88,136", "1"], [])


def test_a_symbol_or_a_word_between_pieces_stops_the_chain():
    assert joined([w("88,", 100, 110), w("$", 110, 113), w("136", 113, 130)]) == (["88,", "$", "136"], [])
    assert joined([w("88,", 100, 110), w("net", 110, 125), w("136", 125, 130)]) == (["88,", "net", "136"], [])


def test_a_piece_outside_the_claimed_region_is_never_joined():
    assert joined([w("88,", 80, 95), w("136", 95, 115)]) == (["88,", "136"], [])  # the first piece is wholly left of the region


def test_words_that_overlap_by_more_than_half_a_point_are_not_neighbours_of_one_figure():
    assert joined([w("88,", 100, 112), w("136", 111.6, 125)]) == (["88,136"], [["88,", "136"]])  # 0.4 pt: rounding
    assert joined([w("88,", 100, 112), w("136", 111.0, 125)]) == (["88,", "136"], [])  # 1 pt


def test_a_gap_of_zero_or_less_turns_joining_off():
    pieces = [w("88,", 100, 110), w("136", 110, 124)]

    assert joined(pieces, gap=0) == (["88,", "136"], []) and joined(pieces, gap=-1) == (["88,", "136"], [])


def test_the_default_gap_is_the_tuning_set_value():
    assert DEFAULT_SPLIT_FIGURE_GAP_PT == 2.0


@pytest.mark.parametrize("text", ["-", "nil", "(", "$", "Total"])
def test_a_non_numeric_word_never_starts_a_chain(text):
    assert joined([w(text, 100, 110), w("136", 110, 124)])[1] == []


# --- the model's raw value as printed ------------------------------------------------------------------------------------------------


def test_the_raw_value_as_printed_with_the_pieces_spaces_is_read_as_the_joined_figure():
    assert _raw_without_join_spaces("88, 136", [("88,", "136")]) == "88,136"
    assert _raw_without_join_spaces("(2,385 )", [("(2,385", ")")]) == "(2,385)"
    assert _raw_without_join_spaces("88,136", [("88,", "136")]) is None  # already joined: nothing to change
    assert _raw_without_join_spaces("99, 999", [("88,", "136")]) is None  # not these pieces
    assert _raw_without_join_spaces("88, 136", []) is None


# --- inside the column check ---------------------------------------------------------------------------------------------------------

Y25, Y24 = date(2025, 3, 31), date(2024, 3, 31)
CHAR = 5.0


def line_word(text, x0, row, x1=None):
    top = 100 + 14 * row
    return Word(text, x0, x0 + CHAR * len(text) if x1 is None else x1, top, top + 10)


def structure(*figure_words):
    rows = [
        [("Consolidated", 72, None), ("Balance", 150, None), ("Sheet", 200, None)],
        [("Note", 300, None), ("2025", 360, None), ("2024", 440, None)],
        [("Interest", 72, None), ("expense", 110, None), *figure_words],
    ]
    words = [line_word(t, x0, i, x1) for i, row in enumerate(rows) for t, x0, x1 in row]
    return analyse_structure(PageWords(1, 595.0, 842.0, 0, tuple(words)), lambda a: {"2025": Y25, "2024": Y24}.get(a.text))


def column_check(figure_words, raw, quote, period=Y25, gap=2.0):
    return check_column(structure(*figure_words), ColumnClaim(period, raw, quote, True), gap)


SPLIT_2025 = [("(2,385", 350, 374), (")", 374.7, 378), ("(2,935", 430, 454), (")", 454.9, 458)]  # regions 357-383 and 437-463
QUOTE = "Interest expense (2,385 ) (2,935 )"


def test_a_split_figure_passes_the_column_check_as_one_cell_and_records_the_pieces():
    result = column_check(SPLIT_2025, "(2,385 )", QUOTE)

    assert result.outcome is Outcome.PASS and result.token.text == "(2,385)" and result.parsed.value == -2385
    assert result.joined_pieces == (("(2,385", ")"),) and result.raw_figure == "(2,385)" and result.conditions.unique is True


def test_the_other_column_of_the_same_line_is_joined_on_its_own_claim():
    result = column_check(SPLIT_2025, "(2,935 )", QUOTE, period=Y24)

    assert result.outcome is Outcome.PASS and result.token.text == "(2,935)" and result.joined_pieces == (("(2,935", ")"),)


def test_without_the_join_the_same_line_is_not_a_unique_cell():
    result = column_check(SPLIT_2025, "(2,385 )", QUOTE, gap=0)

    assert result.outcome is Outcome.FAIL and result.failure is Failure.CELL_NOT_UNIQUE and result.joined_pieces == ()


def test_b6_row_94_a_value_whose_bracket_the_model_dropped_matches_the_cell_but_fails_the_sign_check():
    result = column_check(SPLIT_2025, "2,385", QUOTE)

    assert result.outcome is Outcome.PASS and result.parsed.negative_marker is True  # the joined token carries the page's bracket
    assert check_sign(parse_value("2,385"), result.parsed).ok is False
    assert check_sign(parse_value(result.raw_figure or "2,385"), result.parsed).ok is False


def test_the_model_s_figure_with_its_bracket_passes_the_sign_check_after_the_join():
    result = column_check(SPLIT_2025, "(2,385 )", QUOTE)

    assert check_sign(parse_value(result.raw_figure), result.parsed).ok is True


def test_a_raw_value_that_is_not_the_printed_text_is_still_not_linked_after_the_join():
    result = column_check(SPLIT_2025, "(2,000 )", QUOTE)

    assert result.outcome is Outcome.FAIL and result.failure is Failure.QUOTE_NOT_LINKED and result.joined_pieces == ()


def test_b6_row_95_a_footnote_mark_after_a_split_figure_leaves_the_cell_not_unique():
    words = [("88,", 350, 358), ("136", 358, 374), ("1", 374.2, 378)]

    result = column_check(words, "88, 136", "Interest expense 88, 136 1")

    assert result.outcome is Outcome.FAIL and result.failure is Failure.CELL_NOT_UNIQUE and result.joined_pieces == (("88,", "136"),)


def test_two_complete_figures_touching_in_one_cell_are_not_merged_by_the_column_check():
    result = column_check([("100", 350, 365), ("200", 365.2, 380)], "100", "Interest expense 100 200")

    assert result.outcome is Outcome.FAIL and result.failure is Failure.CELL_NOT_UNIQUE and result.joined_pieces == ()
