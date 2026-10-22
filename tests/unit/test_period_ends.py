"""Period-end validation (PRD FR-005.9, H.1.1; Phase 2 step 7a; B-210).

Appendix B.6 rows 3-6 and 22, and the H.1.1 boundary cases. Pure functions on
synthetic strings; the page-level tests reuse the 6b column structure.
"""

import random
from datetime import date

import pytest

from credit_intel.extraction.columns import StructureProblem, analyse_structure, find_anchors, group_lines
from credit_intel.extraction.periods import (
    Form,
    Method,
    Reason,
    classify,
    find_full_dates,
    find_header_dates,
    header_year_tokens,
    header_lines,
    page_period_resolver,
    parse_full_date,
    parse_year_token,
    periods_are_consecutive,
    resolve_anchor_texts,
)
from credit_intel.ingestion.models import PageWords, Word

D = date


# --- full dates ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("31 March 2025", D(2025, 3, 31)),
        ("March 31, 2025", D(2025, 3, 31)),
        ("March 31 2025", D(2025, 3, 31)),
        ("31st March 2025", D(2025, 3, 31)),
        ("1st April 2024", D(2024, 4, 1)),
        ("Mar 31, 2025", D(2025, 3, 31)),
        ("Mar. 31, 2025", D(2025, 3, 31)),
        ("Sept 30, 2025", D(2025, 9, 30)),
        ("30 JUNE 2025", D(2025, 6, 30)),
        ("  31   March 2025 ", D(2025, 3, 31)),
        ("３１ March 2025", D(2025, 3, 31)),
        ("29 February 2024", D(2024, 2, 29)),
        ("2025-03-31", D(2025, 3, 31)),
        ("31.03.2025", D(2025, 3, 31)),
        ("31/03/2025", D(2025, 3, 31)),
        ("31-03-2025", D(2025, 3, 31)),
        ("03/31/2025", D(2025, 3, 31)),
        ("11/11/2025", D(2025, 11, 11)),
        ("01.01.2025", D(2025, 1, 1)),
        ("as at 31 March 2025", D(2025, 3, 31)),
        ("As of March 31, 2025", D(2025, 3, 31)),
        ("Year ended 31 March 2025", D(2025, 3, 31)),
        ("For the year ended 31 March 2025", D(2025, 3, 31)),
    ],
)
def test_accepted_full_dates(text, expected):
    assert parse_full_date(text) == expected
    assert classify(text) is Form.FULL_DATE


@pytest.mark.parametrize(
    ("text", "form"),
    [
        ("03/04/2025", Form.AMBIGUOUS_NUMERIC_DATE),
        ("03.04.2025", Form.AMBIGUOUS_NUMERIC_DATE),
        ("12-12-2025", Form.FULL_DATE),
        ("31/13/2025", Form.INVALID_DATE),
        ("13/13/2025", Form.INVALID_DATE),
        ("00/05/2025", Form.INVALID_DATE),
        ("31 February 2025", Form.INVALID_DATE),
        ("29 February 2023", Form.INVALID_DATE),
        ("March 32, 2025", Form.INVALID_DATE),
        ("2025-13-01", Form.INVALID_DATE),
        ("2025-02-30", Form.INVALID_DATE),
        ("2025-3-31", Form.UNRECOGNISED),
        ("31 March 25", Form.UNRECOGNISED),
        ("31 Marchh 2025", Form.UNRECOGNISED),
        ("31.03/2025", Form.UNRECOGNISED),
        ("31 March 2025 and more", Form.UNRECOGNISED),
        ("31 March", Form.UNRECOGNISED),
        ("", Form.UNRECOGNISED),
        ("Note", Form.UNRECOGNISED),
    ],
)
def test_other_texts_are_not_guessed(text, form):
    assert classify(text) is form
    if form is not Form.FULL_DATE:
        assert parse_full_date(text) is None


def test_the_ambiguity_rule_reads_the_one_possible_way():
    assert parse_full_date("13/04/2025") == D(2025, 4, 13)
    assert parse_full_date("04/13/2025") == D(2025, 4, 13)
    assert parse_full_date("12/12/2025") == D(2025, 12, 12)
    assert parse_full_date("12/11/2025") is None
    assert parse_full_date("11/12/2025") is None


@pytest.mark.parametrize(
    ("text", "year"),
    [
        ("2025", 2025),
        ("FY2025", 2025),
        ("fy2025", 2025),
        ("FY 2025", 2025),
        ("2024-25", 2025),
        ("FY2024-25", 2025),
        ("FY 2024-25", 2025),
        ("1999-00", 2000),
        ("2099-00", 2100),
    ],
)
def test_year_and_financial_year_tokens_reduce_to_the_later_year(text, year):
    assert parse_year_token(text) == year
    assert classify(text) is Form.YEAR_TOKEN


@pytest.mark.parametrize("text", ["2024-26", "2024-24", "2024-24", "2025-3"])
def test_a_financial_year_must_end_in_the_next_year(text):
    assert parse_year_token(text) is None


@pytest.mark.parametrize("text", ["25", "123", "20255", "FY25", "(2025)", "2025,", "year 2025", ""])
def test_other_year_texts_are_not_years(text):
    assert parse_year_token(text) is None


def test_bad_financial_years_are_reported_as_such():
    assert classify("2024-26") is Form.BAD_FINANCIAL_YEAR


# --- dates elsewhere on the page ----------------------------------------------------------------


def test_full_dates_are_found_anywhere_in_the_page_text():
    text = "Balance Sheet as at 31 March 2025\nNote 5 dated March 31, 2024\n2025-03-31\nTotal 1,234"

    assert find_full_dates(text) == {D(2025, 3, 31), D(2024, 3, 31)}


def test_ambiguous_impossible_and_glued_dates_are_not_found():
    text = "Dated 03/04/2025 and 31 February 2025 and 1231.03.2025 and 31.03.20255"

    assert find_full_dates(text) == frozenset()


def test_a_page_with_no_date_has_no_full_dates():
    assert find_full_dates("Total assets 1,740.00 1,600.00") == frozenset()
    assert find_full_dates("") == frozenset()


# --- resolving anchors: Appendix B.6 -----------------------------------------------------------------


def resolve(texts, page_text=""):
    return resolve_anchor_texts(texts, page_text)


def test_b6_row_3_two_full_dates_are_both_validated():
    result = resolve(["31 March 2025", "31 March 2024"])

    assert result["31 March 2025"].evidence.period_end == D(2025, 3, 31)
    assert result["31 March 2024"].evidence.period_end == D(2024, 3, 31)
    assert result["31 March 2025"].evidence.method is Method.FULL_DATE
    assert result["31 March 2025"].evidence.raw_text == "31 March 2025"


def test_b6_row_4_ambiguous_numeric_dates_are_not_guessed():
    result = resolve(["03/04/2025", "03/04/2024"])

    for found in result.values():
        assert found.evidence is None and found.reason is Reason.AMBIGUOUS_NUMERIC_DATE


def test_b6_row_5_a_financial_year_is_validated_by_the_titles_full_date():
    result = resolve(["2024-25"], "Balance Sheet for the year ended 31 March 2025")

    evidence = result["2024-25"].evidence
    assert evidence.period_end == D(2025, 3, 31) and evidence.raw_text == "2024-25"
    assert evidence.method is Method.YEAR_WITH_PAGE_DATE


def test_b6_row_22_the_comparative_year_is_derived_from_the_validated_current():
    page = "Balance Sheet\nAs at 31 March 2025"

    result = resolve(["2025", "2024"], page)

    assert result["2025"].evidence.period_end == D(2025, 3, 31)
    assert result["2025"].evidence.method is Method.YEAR_WITH_PAGE_DATE
    derived = result["2024"].evidence
    assert derived.period_end == D(2024, 3, 31) and derived.raw_text == "2024"
    assert derived.method is Method.DERIVED_COMPARATIVE and derived.derived_from == D(2025, 3, 31)


def test_b6_row_22_a_current_ending_in_february_leaves_the_comparative_unvalidated():
    for ending in ("28 February 2025", "29 February 2024"):
        year = int(ending[-4:])
        result = resolve([str(year), str(year - 1)], f"As at {ending}")

        assert result[str(year)].evidence is not None
        assert result[str(year - 1)].evidence is None
        assert result[str(year - 1)].reason is Reason.CURRENT_ENDS_IN_FEBRUARY


def test_the_day_before_the_end_of_february_can_still_be_derived():
    result = resolve(["2025", "2024"], "As at 27 February 2025")

    assert result["2024"].evidence.period_end == D(2024, 2, 27)


def test_b6_row_22_no_validated_current_period_leaves_both_unvalidated():
    result = resolve(["2025", "2024"], "Balance Sheet, no date here")

    assert all(r.evidence is None for r in result.values())
    assert result["2025"].reason is Reason.NO_VALIDATED_CURRENT


def test_a_year_that_is_not_exactly_one_year_earlier_is_not_derived():
    result = resolve(["2025", "2023"], "As at 31 March 2025")

    assert result["2023"].evidence is None and result["2023"].reason is Reason.NOT_ONE_YEAR_EARLIER


def test_a_later_year_than_the_current_is_not_derived():
    result = resolve(["2025", "2026"], "As at 31 March 2025")

    assert result["2026"].evidence is None and result["2026"].reason is Reason.NOT_ONE_YEAR_EARLIER


def test_a_year_is_validated_directly_when_the_page_has_its_own_full_date():
    result = resolve(["2025", "2024"], "As at 31 March 2025 and 31 March 2024")

    assert result["2024"].evidence.method is Method.YEAR_WITH_PAGE_DATE


def test_two_different_page_dates_in_one_year_are_not_guessed():
    result = resolve(["2025"], "From 30 June 2025 until 31 March 2025")

    assert result["2025"].evidence is None and result["2025"].reason is Reason.AMBIGUOUS_PAGE_DATE


def test_the_same_page_date_written_twice_is_not_ambiguous():
    assert resolve(["2025"], "31 March 2025 / 2025-03-31")["2025"].evidence is not None


def test_a_year_with_only_a_page_date_of_another_year_is_not_validated():
    result = resolve(["2025"], "As at 31 March 2024")

    assert result["2025"].evidence is None


def test_a_full_date_anchor_can_be_the_current_period_for_a_derived_comparative():
    result = resolve(["31 March 2025", "2024"], "")

    assert result["2024"].evidence.period_end == D(2024, 3, 31)


def test_a_comparative_full_date_alone_does_not_make_the_current_year_valid():
    result = resolve(["31 March 2024", "2025"], "")

    assert result["2025"].evidence is None and result["2025"].reason is Reason.NOT_ONE_YEAR_EARLIER


def test_the_current_period_is_the_latest_validated_one():
    result = resolve(["31 March 2025", "31 March 2024", "2023"], "")

    assert result["2023"].evidence is None and result["2023"].reason is Reason.NOT_ONE_YEAR_EARLIER


def test_financial_year_headers_are_derived_by_their_later_year():
    result = resolve(["FY2024-25", "FY2023-24"], "As at 31 March 2025")

    assert result["FY2024-25"].evidence.period_end == D(2025, 3, 31)
    assert result["FY2023-24"].evidence.period_end == D(2024, 3, 31)


def test_unrecognised_and_invalid_texts_are_never_validated():
    result = resolve(["Note", "31 February 2025", "2024-26"], "As at 31 March 2025")

    assert [r.reason for r in result.values()] == [
        Reason.UNRECOGNISED_FORM,
        Reason.INVALID_DATE,
        Reason.BAD_FINANCIAL_YEAR,
    ]


def test_repeated_anchor_texts_are_resolved_once_in_order():
    result = resolve(["2025", "2024", "2025"], "As at 31 March 2025")

    assert list(result) == ["2025", "2024"]


def test_no_anchors_no_results():
    assert resolve([], "As at 31 March 2025") == {}


# --- the consecutive-period rule (H.1.1) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "comparative", "expected"),
    [
        (D(2025, 3, 31), D(2024, 3, 31), True),
        (D(2024, 2, 29), D(2023, 2, 28), True),
        (D(2025, 2, 28), D(2024, 2, 29), True),
        (D(2024, 2, 28), D(2023, 2, 28), True),
        (D(2025, 3, 31), D(2023, 3, 31), False),
        (D(2025, 3, 31), D(2024, 12, 31), False),
        (D(2025, 3, 31), D(2024, 3, 30), False),
        (D(2025, 3, 31), D(2025, 3, 31), False),
        (D(2025, 3, 31), D(2026, 3, 31), False),
        (D(2025, 3, 1), D(2024, 2, 29), False),
        (D(2024, 2, 29), D(2023, 3, 1), False),
        (D(2025, 2, 27), D(2024, 2, 28), False),
    ],
)
def test_consecutive_period_boundary_cases(current, comparative, expected):
    assert periods_are_consecutive(current, comparative) is expected


def test_a_derived_comparative_is_always_consecutive_with_its_current():
    rng = random.Random(5)
    for _ in range(200):
        current = D(rng.randint(2001, 2099), rng.randint(1, 12), 1)
        current = current.replace(day=rng.randint(1, 28))
        result = resolve([str(current.year), str(current.year - 1)], f"As at {current:%d %B %Y}")
        comparative = result[str(current.year - 1)]
        if current.month == 2 and current.day in (28, 29):
            assert comparative.evidence is None
        else:
            assert periods_are_consecutive(current, comparative.evidence.period_end)


# --- totality ---------------------------------------------------------------------------------------------


def test_parsers_never_raise_on_arbitrary_text():
    rng = random.Random(9)
    alphabet = "0123456789 -/.,:()FYfyMarchJunSeptember−–１\n st"
    for _ in range(2000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
        parse_full_date(text)
        parse_year_token(text)
        classify(text)
        find_full_dates(text)
        resolve_anchor_texts([text, "2025"], text)


# --- agreement with the 6b anchor forms ----------------------------------------------------------------------


def w(text, x0, row=0, char=5.0):
    top = 100 + 14 * row
    return Word(text, x0, x0 + char * len(text), top, top + 10)


ANCHOR_FORMS = [
    "2025", "1999", "FY2025", "fy2025", "2024-25", "FY2024-25", "2025-03-31", "31.03.2025",
    "31/03/2025", "31-03-2025", "03/04/2025", "31/13/2025", "2025-13-01",
]
WRITTEN = [
    ("31", "March", "2025"), ("March", "31,", "2025"), ("March", "31", "2025"),
    ("31st", "March", "2025"), ("Mar", "31,", "2025"), ("Sept", "30,", "2025"),
    ("30", "JUNE", "2025"), ("31", "February", "2025"), ("Mar.", "31,", "2025"), ("31,", "March", "2025"),
]


def anchors_for(words):
    return find_anchors(group_lines(words))


@pytest.mark.parametrize("text", ANCHOR_FORMS)
def test_every_single_word_form_6b_recognises_is_classified_here(text):
    (anchor,) = anchors_for([w(text, 100)])

    assert classify(anchor.text) is not Form.UNRECOGNISED


@pytest.mark.parametrize("parts", WRITTEN)
def test_every_written_date_6b_recognises_is_classified_here(parts):
    x, words = 100.0, []
    for part in parts:
        words.append(w(part, x))
        x += 5.0 * len(part) + 2
    (anchor,) = anchors_for(words)

    assert classify(anchor.text) in (Form.FULL_DATE, Form.INVALID_DATE)


def test_the_fy_word_pair_6b_recognises_is_classified_here():
    (anchor,) = anchors_for([w("FY", 100), w("2024-25", 115)])

    assert anchor.text == "FY 2024-25" and classify(anchor.text) is Form.YEAR_TOKEN
    assert parse_year_token(anchor.text) == 2025


# --- the page-level resolver for the column check (6b) -------------------------------------------------------


def page_of(*rows, rotation=0):
    words = [w(t, x, i) for i, row in enumerate(rows) for t, x in row]
    return PageWords(1, 595.0, 842.0, rotation, tuple(words))


TITLE = [("Consolidated", 72), ("Balance", 150), ("Sheet", 200)]
HEADER = [("Note", 300), ("2025", 360), ("2024", 440)]
FIGURES = [("Total", 72), ("assets", 110), ("14", 305), ("1,740.00", 358), ("1,600.00", 438)]
PAGE_TEXT = "Consolidated Balance Sheet as at 31 March 2025\nNote 2025 2024\nTotal assets 14 1,740.00 1,600.00"


def test_the_resolver_gives_the_column_check_its_two_periods():
    page = page_of(TITLE, HEADER, FIGURES)

    structure = analyse_structure(page, page_period_resolver(page, PAGE_TEXT))

    assert structure.valid
    assert [c.period_end for c in structure.columns] == [D(2025, 3, 31), D(2024, 3, 31)]


def test_ambiguous_headers_leave_no_usable_anchor():
    header = [("Note", 300), ("03/04/2025", 350), ("03/04/2024", 440)]
    page = page_of(TITLE, header, FIGURES)

    structure = analyse_structure(page, page_period_resolver(page, "Balance Sheet"))

    assert StructureProblem.NO_USABLE_ANCHOR in structure.problems
    assert StructureProblem.UNVALIDATED_ANCHOR in structure.problems


def test_a_year_header_without_any_page_date_is_unvalidated():
    page = page_of(TITLE, HEADER, FIGURES)

    structure = analyse_structure(page, page_period_resolver(page, "Balance Sheet"))

    assert structure.problems[0] is StructureProblem.NO_USABLE_ANCHOR


def test_the_resolver_for_a_rotated_page_resolves_nothing():
    page = page_of(TITLE, HEADER, FIGURES, rotation=90)

    resolver = page_period_resolver(page, PAGE_TEXT)

    assert resolver(find_anchors(group_lines(page.words))[0]) is None


def test_a_date_below_the_header_block_does_not_validate_a_header():
    # The only full date is in a row below the first figure line, so it is not an anchor
    # and, with no date in the page text, the year headers stay unvalidated.
    page = page_of(TITLE, HEADER, FIGURES, [("31", 72), ("March", 84), ("2025", 111)])

    structure = analyse_structure(page, page_period_resolver(page, "Balance Sheet"))

    assert StructureProblem.NO_USABLE_ANCHOR in structure.problems


def test_the_resolver_only_considers_the_header_block():
    # "2023" sits below the first figure line: it is not an anchor and must not decide the current period.
    page = page_of(TITLE, HEADER, FIGURES, [("2023", 300)])

    structure = analyse_structure(page, page_period_resolver(page, PAGE_TEXT))

    assert structure.valid and len(structure.anchors) == 2


def test_a_known_current_period_lets_a_comparative_only_page_derive_its_column():
    page = page_of(TITLE, [("Note", 300), ("2024", 440)], FIGURES[:3] + [("1,600.00", 438)])
    text = "Balance Sheet\nNote 2024\nTotal assets 14 1,600.00"

    without = analyse_structure(page, page_period_resolver(page, text))
    derived = analyse_structure(page, page_period_resolver(page, text, known_current=D(2025, 3, 31)))

    assert StructureProblem.NO_USABLE_ANCHOR in without.problems
    assert derived.valid and [c.period_end for c in derived.columns] == [D(2024, 3, 31)]


# --- v0.4.20: dates in the title or column-header block only, and wrapped dates -----------------------

HDR_TITLE = "Acme Limited\nBalance Sheet"
HDR_FIGURES = "Total current assets 14 1,482.30 1,356.75"


def text_of(*lines):
    return "\n".join(lines)


def test_header_lines_stop_at_the_first_figure_line():
    text = text_of(HDR_TITLE, "As at March 31,", "2025 2024", HDR_FIGURES, "Signed on April 17, 2025")

    assert header_lines(text) == ("Acme Limited", "Balance Sheet", "As at March 31,", "2025 2024")


def test_a_page_with_no_figure_line_is_all_header():
    assert header_lines("A\nB") == ("A", "B")


def test_b6_row_22_the_date_is_in_the_header_block():
    text = text_of(HDR_TITLE, "As at March 31, 2025", "2025 2024", HDR_FIGURES)

    result = resolve(["2025", "2024"], text)

    assert result["2025"].evidence.period_end == D(2025, 3, 31)
    assert result["2024"].evidence.method is Method.DERIVED_COMPARATIVE


def test_b6_row_23_a_date_wrapped_over_two_lines_is_one_date():
    text = text_of(HDR_TITLE, "As at March 31,", "2025", "2025 2024", HDR_FIGURES)

    assert find_header_dates(text) == {D(2025, 3, 31)}
    result = resolve(["2025", "2024"], text)
    assert result["2025"].evidence.period_end == D(2025, 3, 31)
    assert result["2024"].evidence.period_end == D(2024, 3, 31)


def test_b6_row_24_a_date_below_the_figures_validates_nothing():
    text = text_of(HDR_TITLE, "2025 2024", HDR_FIGURES, "Signed on behalf of the Board on April 17, 2025")

    assert find_header_dates(text) == frozenset()
    assert find_full_dates(text) == {D(2025, 4, 17)}  # the page scan still sees it; the rule does not use it
    for token in ("2025", "2024"):
        found = resolve([token], text)[token]
        assert found.evidence is None and found.reason is Reason.NO_VALIDATED_CURRENT


def test_b6_row_24_the_signing_date_cannot_validate_the_year_even_with_a_real_date_elsewhere():
    text = text_of(HDR_TITLE, "As at March 31, 2025", "2025 2024", HDR_FIGURES, "Signed April 17, 2025")

    assert resolve(["2025"], text)["2025"].evidence.period_end == D(2025, 3, 31)


def test_b6_row_25_two_different_dates_of_the_year_in_the_header_are_not_guessed():
    text = text_of(HDR_TITLE, "As at March 31, 2025", "Approved April 17, 2025", "2025 2024", HDR_FIGURES)

    found = resolve(["2025"], text)["2025"]

    assert found.evidence is None and found.reason is Reason.AMBIGUOUS_PAGE_DATE


def test_the_same_date_written_twice_in_the_header_is_one_date():
    text = text_of(HDR_TITLE, "As at March 31, 2025", "31 March 2025", "2025 2024", HDR_FIGURES)

    assert resolve(["2025"], text)["2025"].evidence.period_end == D(2025, 3, 31)


def test_b6_row_26_a_date_split_by_a_figure_line_is_not_joined():
    text = text_of(HDR_TITLE, "As at March 31,", HDR_FIGURES, "2025")

    assert find_header_dates(text) == frozenset()


def test_a_date_is_not_joined_across_a_line_that_is_not_adjacent():
    text = text_of(HDR_TITLE, "As at March 31,", "Note", "2025")

    assert find_header_dates(text) == frozenset()


def test_a_wrapped_date_that_is_impossible_or_ambiguous_is_not_a_date():
    assert find_header_dates(text_of("Dated 31 February", "2025")) == frozenset()
    assert find_header_dates(text_of("Dated 03/04/", "2025")) == frozenset()


def test_the_wrapped_date_of_one_year_does_not_validate_another_years_header():
    text = text_of(HDR_TITLE, "As at March 31,", "2025", "2023 2022", HDR_FIGURES)

    found = resolve(["2023"], text)["2023"]

    assert found.evidence is None and found.reason is Reason.NO_VALIDATED_CURRENT


def test_no_page_without_a_header_date_can_validate_a_year_header():
    rng = random.Random(20)
    for _ in range(200):
        year = rng.randint(1990, 2090)
        below = f"Signed {rng.randint(1, 28)} March {year}"
        text = text_of(HDR_TITLE, f"{year} {year - 1}", HDR_FIGURES, below)

        found = resolve([str(year)], text)[str(year)]

        assert found.evidence is None


# --- v0.4.22: year headings in the header block (the code derives the comparative from them) --------------------------------


def test_year_headings_are_found_with_their_header_line():
    text = text_of(HDR_TITLE, "Particulars Note 2025 2024", HDR_FIGURES)

    assert header_year_tokens(text) == (("2025", "Particulars Note 2025 2024"), ("2024", "Particulars Note 2025 2024"))


def test_a_financial_year_heading_and_fy_prefix_are_tokens():
    text = text_of("Particulars FY 2024-25 FY2023-24", HDR_FIGURES)

    assert [t for t, _ in header_year_tokens(text)] == ["FY 2024-25", "FY2023-24"]


def test_a_year_inside_a_full_date_is_not_a_heading():
    text = text_of(HDR_TITLE, "As at 31 March 2025", "Approved on 17 April 2024", HDR_FIGURES)

    assert header_year_tokens(text) == ()


def test_a_year_in_a_wrapped_date_is_not_a_heading():
    text = text_of(HDR_TITLE, "As at March 31,", "2024", HDR_FIGURES)

    assert header_year_tokens(text) == ()


def test_a_year_below_the_first_figure_line_is_not_a_heading():
    text = text_of(HDR_TITLE, "Particulars 2025", HDR_FIGURES, "Annual Report 2024")

    assert [t for t, _ in header_year_tokens(text)] == ["2025"]


def test_the_year_heading_next_to_a_date_is_still_found():
    text = text_of("As at 31 March 2025 and 2024", HDR_FIGURES)

    assert [t for t, _ in header_year_tokens(text)] == ["2024"]
