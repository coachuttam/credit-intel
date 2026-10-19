"""Statement runs (PRD FR-013 rule 6; step 7c; B-213)."""

from credit_intel.ingestion.models import CandidatePage, LocatorResult
from credit_intel.extraction.runs import statement_run_start

BS, IS = "balance_sheet", "income_statement"


def result(*pages, method="keywords"):
    return LocatorResult(
        method=method,
        candidates=tuple(CandidatePage(n, tuple(sorted(types)), 5 if types else None, ()) for n, types in pages),
    )


def test_consecutive_pages_of_one_type_form_a_run_starting_at_its_first_page():
    located = result((112, {BS}), (113, {BS}), (114, {BS}))

    assert [statement_run_start(located, p, BS) for p in (112, 113, 114)] == [112, 112, 112]


def test_a_gap_in_the_page_numbers_starts_a_new_run():
    located = result((112, {BS}), (113, {BS}), (115, {BS}), (116, {BS}))

    assert [statement_run_start(located, p, BS) for p in (113, 115, 116)] == [112, 115, 115]


def test_a_neighbouring_page_of_another_type_does_not_extend_the_run():
    located = result((112, {BS}), (113, {IS}), (114, {IS}))

    assert statement_run_start(located, 112, BS) == 112
    assert statement_run_start(located, 114, IS) == 113


def test_a_page_with_two_types_belongs_to_a_run_of_each():
    located = result((110, {BS}), (111, {BS, IS}), (112, {IS}))

    assert statement_run_start(located, 111, BS) == 110
    assert statement_run_start(located, 111, IS) == 111
    assert statement_run_start(located, 112, IS) == 111


def test_a_page_that_was_not_selected_for_the_type_has_no_run():
    located = result((112, {BS}))

    assert statement_run_start(located, 112, IS) is None
    assert statement_run_start(located, 113, BS) is None
    assert statement_run_start(located, 111, BS) is None


def test_a_page_range_records_no_types_so_there_is_no_run():
    located = result((5, set()), (6, set()), method="page_range")

    assert statement_run_start(located, 5, BS) is None
    assert statement_run_start(located, 6, BS) is None


def test_an_unselected_page_between_two_selected_ones_splits_them():
    located = result((112, {BS}), (114, {BS}))

    assert statement_run_start(located, 114, BS) == 114


def test_a_long_run_is_followed_to_its_start():
    located = result(*[(n, {BS}) for n in range(20, 60)])

    assert statement_run_start(located, 59, BS) == 20


def test_appendix_b_example_5_pages_112_and_113_are_one_run():
    located = result((112, {BS}), (113, {BS}), (114, {IS}))

    assert statement_run_start(located, 113, BS) == 112
    assert statement_run_start(located, 114, IS) == 114
