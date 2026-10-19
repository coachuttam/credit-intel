"""Page structure for the period-column check (OD-1 step 6b; B-207).

Unit tests build ``Word`` lists directly; the AC-OD1-25 tests build PDFs with
reportlab. All data is synthetic. PRD FR-005.7; ``docs/OD-1_period_column_proposal.md`` §3.2-§3.4.
"""

import random
from datetime import date

import pytest
from reportlab.pdfgen import canvas

from credit_intel.config import ColumnSettings
from credit_intel.extraction.columns import (
    KIND_DATE,
    KIND_FINANCIAL_YEAR,
    KIND_YEAR,
    PeriodAnchor,
    StructureProblem,
    analyse_structure,
    find_anchors,
    group_lines,
    header_block,
)
from credit_intel.ingestion.models import PageWords, Word
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

Y25 = date(2025, 3, 31)
Y24 = date(2024, 3, 31)
Y23 = date(2023, 3, 31)

# Character width used by the layout helper; a word's extent is len * CHAR.
CHAR = 5.0


def word(text, x0, row, x1=None, dy=0.0):
    top = 100 + 14 * row + dy
    return Word(text, x0, x0 + CHAR * len(text) if x1 is None else x1, top, top + 10)


def page(*rows, rotation=0, number=1):
    """rows: lists of (text, x0) or (text, x0, x1); the row's index sets its height."""
    words = [word(t, x0, i, *(rest[:1] if rest else ())) for i, row in enumerate(rows) for t, x0, *rest in row]
    return PageWords(number, 595.0, 842.0, rotation, tuple(words))


def resolver(mapping):
    def resolve(anchor):
        return mapping.get(anchor.text)

    return resolve


YEARS = resolver({"2025": Y25, "2024": Y24, "2023": Y23})

# A typical statement: title, a header row with Note and two years, then figures.
TITLE = [("Consolidated", 72), ("Balance", 150), ("Sheet", 200)]
HEADER = [("Note", 300), ("2025", 360), ("2024", 440)]
FIGURES = [("Total", 72), ("assets", 110), ("14", 305), ("1,740.00", 350), ("1,600.00", 430)]
STATEMENT = page(TITLE, HEADER, FIGURES)


# --- lines (3.2) ------------------------------------------------------------------------


def test_words_on_one_height_form_one_line_in_x_order():
    lines = group_lines([word("b", 50, 0), word("a", 10, 0)])

    assert [line.text for line in lines] == ["a b"]


def test_a_new_line_starts_when_the_centre_moves_more_than_the_tolerance():
    same = group_lines([word("a", 10, 0), word("b", 50, 0, dy=3.0)])
    new = group_lines([word("a", 10, 0), word("b", 50, 0, dy=3.01)])

    assert len(same) == 1 and len(new) == 2


def test_comparison_is_with_the_previous_word_so_a_drifting_line_stays_together():
    words = [word("a", 10, 0, dy=0), word("b", 50, 0, dy=3), word("c", 90, 0, dy=6)]

    assert [line.text for line in group_lines(words)] == ["a b c"]


def test_the_tolerance_setting_is_used():
    words = [word("a", 10, 0), word("b", 50, 0, dy=2)]

    assert len(group_lines(words, 1)) == 2 and len(group_lines(words, 3)) == 1


def test_lines_are_ordered_top_to_bottom_and_numbered():
    lines = group_lines([word("low", 10, 2), word("high", 10, 0), word("mid", 10, 1)])

    assert [(l.index, l.text) for l in lines] == [(0, "high"), (1, "mid"), (2, "low")]


def test_text_is_nfkc_normalised_and_empty_words_dropped():
    lines = group_lines([word("２０２５", 10, 0), word("  ", 50, 0), word("a b", 90, 0)])

    assert [line.text for line in lines] == ["2025 a b"]


def test_equal_x_words_are_ordered_by_text():
    assert group_lines([word("b", 10, 0), word("a", 10, 0)])[0].text == "a b"


def test_input_order_does_not_matter():
    words = [word(t, x, r) for r in range(3) for t, x in (("a", 10), ("b", 60), ("c", 110))]
    expected = group_lines(words)
    rng = random.Random(7)
    for _ in range(10):
        shuffled = words[:]
        rng.shuffle(shuffled)
        assert group_lines(shuffled) == expected


def test_no_words_no_lines():
    assert group_lines([]) == ()


# --- the header block ---------------------------------------------------------------------


def test_header_block_is_between_the_last_title_line_and_the_first_figure_line():
    lines = group_lines(STATEMENT.words)

    assert header_block(lines) == (1, 2)


def test_without_a_title_line_the_block_starts_at_the_top():
    lines = group_lines(page(HEADER, FIGURES).words)

    assert header_block(lines) == (0, 1)


def test_without_a_figure_line_the_block_runs_to_the_end():
    lines = group_lines(page([("Notes", 72)], [("2025", 360)]).words)

    assert header_block(lines) == (0, 2)


def test_a_split_title_line_ends_the_block_after_its_second_line():
    split = page([("Consolidated", 72), ("Balance", 150)], [("Sheet", 72)], HEADER, FIGURES)

    assert header_block(group_lines(split.words)) == (2, 3)


# --- anchors ---------------------------------------------------------------------------------


def anchors_of(*words_in_row):
    return find_anchors(group_lines([word(t, x, 0) for t, x in words_in_row]))


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("2025", KIND_YEAR),
        ("FY2025", KIND_FINANCIAL_YEAR),
        ("fy2025", KIND_FINANCIAL_YEAR),
        ("2024-25", KIND_FINANCIAL_YEAR),
        ("FY2024-25", KIND_FINANCIAL_YEAR),
        ("2025-03-31", KIND_DATE),
        ("31.03.2025", KIND_DATE),
        ("31/03/2025", KIND_DATE),
        ("31-03-2025", KIND_DATE),
    ],
)
def test_single_word_forms(text, kind):
    (anchor,) = anchors_of((text, 100))

    assert (anchor.text, anchor.kind) == (text, kind)


@pytest.mark.parametrize("text", ["12", "123", "12345", "20255", "Note", "(2025)", "2025,", "1,740.00", "FY25"])
def test_other_words_are_not_anchors(text):
    assert anchors_of((text, 100)) == ()


@pytest.mark.parametrize(
    "words",
    [
        ("31", "March", "2025"),
        ("March", "31,", "2025"),
        ("March", "31", "2025"),
        ("31st", "March", "2025"),
        ("Mar", "31,", "2025"),
        ("Sept", "30,", "2025"),
        ("30", "JUNE", "2025"),
    ],
)
def test_written_dates_of_three_adjacent_words_are_one_anchor(words):
    x = 100.0
    touching = []
    for t in words:
        touching.append((t, x))
        x += CHAR * len(t) + 2
    (anchor,) = anchors_of(*touching)

    assert anchor.text == " ".join(words) and anchor.kind == KIND_DATE
    assert (anchor.x0, anchor.x1) == (100.0, touching[-1][1] + CHAR * len(words[-1]))


def test_a_date_whose_words_are_far_apart_is_not_joined_and_only_the_year_is_an_anchor():
    # R2 pattern: "Year Ended June 30," at the left, 2025 far right.
    anchors = anchors_of(("Year", 72), ("Ended", 110), ("June", 160), ("30,", 200), ("2025", 440))

    assert [a.text for a in anchors] == ["2025"]


def test_adjacency_threshold_is_the_mean_character_width():
    # 5 pt characters: the allowed gap is 5 pt; 5 passes, 5.1 does not.
    def date_with_gap(gap):
        x = 100.0
        placed = []
        for t in ("31", "March", "2025"):
            placed.append(word(t, x, 0))
            x += CHAR * len(t) + gap
        return find_anchors(group_lines(placed))

    assert [a.kind for a in date_with_gap(5.0)] == [KIND_DATE]
    assert [a.kind for a in date_with_gap(5.1)] == [KIND_YEAR]


@pytest.mark.parametrize(("gap", "kinds"), [(5.0, [KIND_DATE]), (6.0, [KIND_DATE]), (6.1, [KIND_YEAR])])
def test_adjacency_uses_the_mean_of_the_two_character_widths(gap, kinds):
    # "31" has 10 pt characters and "March" 2 pt characters: the mean is 6, the larger 10, the smaller 2.
    words = [
        Word("31", 100, 120, 100, 110),
        Word("March", 120 + gap, 130 + gap, 100, 110),
        Word("2025", 132 + gap, 142 + gap, 100, 110),
    ]

    assert [a.kind for a in find_anchors(group_lines(words))] == kinds


def test_overlapping_words_count_as_adjacent():
    words = [Word("31", 100, 120, 100, 110), Word("March", 105, 135, 100, 110), Word("2025", 130, 150, 100, 110)]

    assert [a.kind for a in find_anchors(group_lines(words))] == [KIND_DATE]


def test_fy_prefix_joins_an_adjacent_year_form():
    near = find_anchors(group_lines([word("FY", 100, 0), word("2024-25", 115, 0)]))
    far = find_anchors(group_lines([word("FY", 100, 0), word("2024-25", 200, 0)]))
    plain = find_anchors(group_lines([word("FY", 100, 0), word("2025", 115, 0)]))

    assert [(a.text, a.kind) for a in near] == [("FY 2024-25", KIND_FINANCIAL_YEAR)]
    assert [a.text for a in far] == ["2024-25"]
    assert [(a.text, a.kind) for a in plain] == [("FY 2025", KIND_FINANCIAL_YEAR)]


def test_two_year_columns_are_two_anchors_in_x_order_with_extents():
    first, second = anchors_of(("2025", 360), ("2024", 440))

    assert (first.text, first.x0, first.x1) == ("2025", 360, 380)
    assert (second.text, second.x0, second.x1) == ("2024", 440, 460)
    assert first.line_index == second.line_index == 0


def test_anchors_carry_their_line_and_box():
    block = group_lines(page([("x", 10)], [("2025", 360)]).words)

    (anchor,) = find_anchors(block[1:])

    assert (anchor.line_index, anchor.top, anchor.bottom) == (1, 114.0, 124.0)


# --- columns, note span, label limit (AC-OD1-1 to 5) ----------------------------------------------


def test_aligned_columns_with_a_note_column():
    structure = analyse_structure(STATEMENT, YEARS)

    assert structure.valid and structure.problems == ()
    assert [(c.period_end, c.x0, c.x1) for c in structure.columns] == [
        (Y25, 357, 383),
        (Y24, 437, 463),
    ]
    assert (structure.note_span.x0, structure.note_span.x1) == (297, 357)
    assert structure.label_limit == 297


def test_the_note_span_ends_exactly_where_the_first_region_starts():
    structure = analyse_structure(STATEMENT, YEARS)

    assert structure.note_span.x1 == structure.columns[0].x0


def test_without_a_note_header_there_is_no_note_span_and_the_limit_is_the_first_region():
    structure = analyse_structure(page(TITLE, [("2025", 360), ("2024", 440)], FIGURES), YEARS)

    assert structure.note_span is None
    assert structure.label_limit == 357


def test_note_and_notes_in_any_case_define_the_span():
    for label in ("Notes", "NOTE", "notes"):
        header = [(label, 300), ("2025", 360), ("2024", 440)]
        assert analyse_structure(page(TITLE, header, FIGURES), YEARS).note_span is not None


def test_a_note_word_right_of_the_first_region_defines_no_span():
    header = [("2025", 360), ("Note", 420), ("2024", 440)]

    structure = analyse_structure(page(TITLE, header, FIGURES), YEARS)

    assert structure.note_span is None and structure.label_limit == 357


def test_the_leftmost_note_word_is_used():
    header = [("Note", 250), ("Note", 300), ("2025", 360), ("2024", 440)]

    assert analyse_structure(page(TITLE, header, FIGURES), YEARS).note_span.x0 == 247


def test_a_note_word_below_the_first_figure_line_is_ignored():
    structure = analyse_structure(
        page(TITLE, [("2025", 360), ("2024", 440)], FIGURES, [("Note", 300)]), YEARS
    )

    assert structure.note_span is None


def test_comparative_first_layout_maps_by_period_not_by_order():
    header = [("2024", 360), ("2025", 440)]

    structure = analyse_structure(page(TITLE, header, FIGURES), YEARS)

    assert [c.period_end for c in structure.columns] == [Y24, Y25]
    assert structure.columns[1].x0 == 437 and structure.valid


def test_regions_are_the_anchor_extent_plus_the_margin():
    wide = ColumnSettings(column_margin_pt=10)

    structure = analyse_structure(STATEMENT, YEARS, wide)

    assert (structure.columns[0].x0, structure.columns[0].x1) == (350, 390)
    assert structure.note_span.x0 == 290


def test_header_centred_over_wider_figures_keeps_the_header_extent():
    # The header is only 20 pt wide although the figures below are wider.
    structure = analyse_structure(page(TITLE, [("2025", 380)], [("1,740,000.00", 330, 400)]), YEARS)

    assert (structure.columns[0].x0, structure.columns[0].x1) == (377, 403)


def test_two_line_header_uses_the_years_as_anchors():
    rows = [
        TITLE,
        [("As", 300), ("at", 315), ("March", 330), ("31,", 370)],
        [("2025", 360), ("2024", 440)],
        FIGURES,
    ]
    structure = analyse_structure(page(*rows), YEARS)

    assert [a.text for a in structure.anchors] == ["2025", "2024"] and structure.valid


def test_year_only_anchor_with_the_date_words_far_left():
    rows = [TITLE, [("Year", 72), ("Ended", 110), ("June", 160), ("30,", 200), ("2025", 440)], FIGURES]
    structure = analyse_structure(page(*rows), YEARS)

    assert [a.text for a in structure.anchors] == ["2025"]
    assert [c.period_end for c in structure.columns] == [Y25]


def test_a_date_inside_the_title_line_is_not_a_column():
    rows = [
        [("Balance", 72), ("Sheet", 120), ("as", 160), ("at", 175), ("31", 190), ("March", 210), ("2025", 245)],
        [("2025", 360), ("2024", 440)],
        FIGURES,
    ]
    structure = analyse_structure(page(*rows), YEARS)

    assert [a.text for a in structure.anchors] == ["2025", "2024"]
    assert structure.anchors[0].x0 == 360


def test_anchors_below_the_first_figure_line_are_not_resolved():
    seen = []

    def resolve(anchor):
        seen.append(anchor.text)
        return YEARS(anchor)

    analyse_structure(page(TITLE, HEADER, FIGURES, [("2023", 300)]), resolve)

    assert seen == ["2025", "2024"]


# --- structure validity S (AC-OD1-10, 22, 23, ZA-1) ----------------------------------------------


def test_stacked_anchors_of_one_period_with_overlapping_extent_are_one_column():
    rows = [TITLE, [("2025", 360)], [("31.03.2025", 350)], [("2024", 440)], FIGURES]
    resolve = resolver({"2025": Y25, "31.03.2025": Y25, "2024": Y24})

    structure = analyse_structure(page(*rows), resolve)

    assert structure.valid
    assert len(structure.columns) == 2
    assert len(structure.columns[0].anchors) == 2
    assert (structure.columns[0].x0, structure.columns[0].x1) == (347, 403)


def test_two_columns_for_one_period_are_a_problem():
    rows = [TITLE, [("2025", 360), ("2025", 440)], FIGURES]

    structure = analyse_structure(page(*rows), YEARS)

    assert structure.problems == (StructureProblem.DUPLICATE_PERIOD_COLUMN,)
    assert len(structure.columns) == 2 and not structure.valid


def test_side_by_side_statements_are_a_problem():
    rows = [TITLE, [("2025", 100), ("2024", 160), ("2025", 360), ("2024", 440)], FIGURES]

    structure = analyse_structure(page(*rows), YEARS)

    assert StructureProblem.DUPLICATE_PERIOD_COLUMN in structure.problems
    assert not structure.valid


def test_overlapping_regions_of_different_periods_are_a_problem():
    rows = [TITLE, [("2025", 360), ("2024", 380)], FIGURES]

    structure = analyse_structure(page(*rows), YEARS)

    assert structure.problems == (StructureProblem.OVERLAPPING_REGIONS,)


def test_regions_that_only_touch_do_not_overlap():
    # 2025 spans 360-380 (region 357-383); 2024 starts at 383+3 = 386 - so region 383-409 touches.
    rows = [TITLE, [("2025", 360), ("2024", 386)], FIGURES]

    assert analyse_structure(page(*rows), YEARS).valid


def test_an_anchor_without_a_validated_period_is_a_problem_but_the_others_still_form_columns():
    resolve = resolver({"2025": Y25})

    structure = analyse_structure(STATEMENT, resolve)

    assert structure.problems == (StructureProblem.UNVALIDATED_ANCHOR,)
    assert [c.period_end for c in structure.columns] == [Y25]
    assert [a.period_end for a in structure.anchors] == [Y25, None]


def test_no_usable_anchor_means_no_columns_and_no_label_limit():
    structure = analyse_structure(page(TITLE, [("Note", 300)], FIGURES), YEARS)

    assert structure.problems == (StructureProblem.NO_USABLE_ANCHOR,)
    assert structure.columns == () and structure.label_limit is None
    assert structure.note_span is None


def test_anchors_that_are_all_unvalidated_give_both_problems():
    structure = analyse_structure(STATEMENT, resolver({}))

    assert structure.problems == (
        StructureProblem.NO_USABLE_ANCHOR,
        StructureProblem.UNVALIDATED_ANCHOR,
    )
    assert structure.label_limit is None


def test_page_selected_by_range_with_no_header_has_no_usable_anchor():
    structure = analyse_structure(page(FIGURES, [("Total", 72), ("equity", 110), ("2,000.00", 350)]), YEARS)

    assert structure.problems == (StructureProblem.NO_USABLE_ANCHOR,)


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_page_is_not_analysed(rotation):
    structure = analyse_structure(page(TITLE, HEADER, FIGURES, rotation=rotation), YEARS)

    assert structure.problems == (StructureProblem.ROTATED,)
    assert structure.lines == () and structure.columns == () and structure.label_limit is None


def test_resolver_is_not_called_for_a_rotated_page():
    def resolve(anchor):
        raise AssertionError("resolver called")

    analyse_structure(page(TITLE, HEADER, FIGURES, rotation=90), resolve)


def test_third_period_column_is_valid_and_kept():
    header = [("2025", 300), ("2024", 380), ("2023", 460)]

    structure = analyse_structure(page(TITLE, header, FIGURES), YEARS)

    assert structure.valid and [c.period_end for c in structure.columns] == [Y25, Y24, Y23]


def test_a_headerless_continuation_page_fails_safe_whatever_its_columns():
    # Same layout, shifted columns, different size: none establishes alignment (3.9).
    for shift, width in ((0, 595.0), (80, 595.0), (0, 612.0)):
        words = tuple(
            Word(w.text, w.x0 + shift, w.x1 + shift, w.top, w.bottom)
            for w in page(FIGURES).words
        )
        continuation = PageWords(2, width, 842.0, 0, words)

        structure = analyse_structure(continuation, YEARS)

        assert structure.problems == (StructureProblem.NO_USABLE_ANCHOR,)


def test_a_continuation_page_with_its_own_header_is_evaluated_normally():
    assert analyse_structure(page(HEADER, FIGURES, number=2), YEARS).valid


def test_analysis_is_deterministic_and_independent_of_word_order():
    expected = analyse_structure(STATEMENT, YEARS)
    rng = random.Random(3)
    for _ in range(10):
        words = list(STATEMENT.words)
        rng.shuffle(words)
        shuffled = PageWords(1, 595.0, 842.0, 0, tuple(words))
        assert analyse_structure(shuffled, YEARS) == expected


def test_shifting_every_x_by_a_constant_shifts_the_result_by_it():
    base = analyse_structure(STATEMENT, YEARS)
    moved_words = tuple(Word(w.text, w.x0 + 25, w.x1 + 25, w.top, w.bottom) for w in STATEMENT.words)
    moved = analyse_structure(PageWords(1, 595.0, 842.0, 0, moved_words), YEARS)

    assert [(c.period_end, c.x0 - 25, c.x1 - 25) for c in moved.columns] == [
        (c.period_end, c.x0, c.x1) for c in base.columns
    ]
    assert moved.label_limit - 25 == base.label_limit
    assert moved.problems == base.problems


def test_structure_records_the_header_block_bounds():
    structure = analyse_structure(STATEMENT, YEARS)

    assert (structure.header_first, structure.header_last) == (1, 2)
    assert structure.page_number == 1
    assert isinstance(structure.anchors[0], PeriodAnchor)


# --- AC-OD1-25: word-line text equals the extract_text line (synthetic PDFs only) ------------------


def pdf_with_rows(tmp_path, rows):
    """rows: lists of (x, y_from_bottom, text)."""
    path = tmp_path / "rows.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.setFont("Helvetica", 10)
    for x, y, text in rows:
        pdf.drawString(x, y, text)
    pdf.showPage()
    pdf.save()
    return path


LAYOUTS = {
    "aligned rows": [
        (72, 700, "Total assets"), (300, 700, "1,740.00"), (400, 700, "1,600.00"),
        (72, 686, "Total equity"), (300, 686, "600.00"), (400, 686, "(500.00)"),
    ],
    "2 pt offset": [(72, 700, "Borrowings"), (300, 698, "300.00"), (400, 700, "250.00")],
    "5 pt offset": [(72, 700, "Borrowings"), (300, 695, "300.00"), (400, 700, "250.00")],
    "blank cell": [(72, 700, "Finance costs"), (400, 700, "250.00"), (72, 686, "Tax"), (300, 686, "5.00")],
    "wrapped label tail": [(72, 700, "Common stock and paid-in capital"), (72, 686, "outstanding 7,434 and 7,434"), (300, 686, "109,095"), (400, 686, "100,923")],
}


@pytest.mark.parametrize("name", list(LAYOUTS))
def test_word_lines_equal_the_extract_text_lines(tmp_path, name):
    path = pdf_with_rows(tmp_path, LAYOUTS[name])
    text_lines = PdfplumberExtractor().extract_pages(path)[0].text.split("\n")
    (words,) = PdfplumberExtractor().extract_words(path, [1])

    lines = group_lines(words.words)

    assert [line.text for line in lines] == text_lines
