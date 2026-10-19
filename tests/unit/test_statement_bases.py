"""Statement basis of a field and the configured-basis filter (PRD H.4.6, D-06; step 8a; B-217)."""

from credit_intel.extraction.bases import (
    CITED_PAGE,
    RUN_START,
    field_basis,
    filter_by_basis,
    page_basis,
)
from credit_intel.config import CONSOLIDATED, LocatorSettings
from credit_intel.ingestion.models import CandidatePage, LocatorResult, PageText
from credit_intel.models import StatementBasis as B

BODY = "\nTotal equity 600.00 500.00"


def page(title, number=1):
    return PageText(page_number=number, text=(title + BODY) if title is not None else "Total equity 600.00 500.00")


def located(*numbers, types=("balance_sheet",)):
    return LocatorResult("keywords", tuple(CandidatePage(n, types, 5, ()) for n in numbers))


# --- the basis a page's own title gives -----------------------------------------------------------------


def test_a_title_naming_one_basis_gives_it():
    assert page_basis("Consolidated Balance Sheet" + BODY) is B.CONSOLIDATED
    assert page_basis("Standalone Balance Sheet" + BODY) is B.STANDALONE
    assert page_basis("Separate Balance Sheet" + BODY) is B.STANDALONE


def test_a_title_naming_both_or_neither_is_unknown():
    assert page_basis("Consolidated and Standalone Balance Sheet" + BODY) is B.UNKNOWN
    assert page_basis("Balance Sheet" + BODY) is B.UNKNOWN


def test_a_basis_line_directly_above_the_title_counts():
    assert page_basis("(Consolidated)\nBalance Sheet" + BODY) is B.CONSOLIDATED


def test_basis_words_outside_a_title_block_do_not_count():
    assert page_basis("Consolidated Industries Limited\nBalance Sheet" + BODY) is B.UNKNOWN


def test_a_page_with_no_title_line_has_no_basis_of_its_own():
    assert page_basis("Total equity 600.00 500.00") is None
    assert page_basis("") is None


def test_two_title_blocks_of_one_basis_agree_and_of_two_bases_do_not():
    # Title lines count only above the page's first figure line (G.0).
    same = "Consolidated Balance Sheet\nConsolidated Balance Sheet\nTotal assets 1,740.00"
    mixed = "Consolidated Balance Sheet\nStandalone Balance Sheet\nTotal assets 1,740.00"

    assert page_basis(same) is B.CONSOLIDATED
    assert page_basis(mixed) is B.UNKNOWN


# --- the basis of a field -----------------------------------------------------------------------------------


def test_a_field_takes_the_basis_of_its_cited_page():
    pages = {1: page("Consolidated Balance Sheet", 1), 2: page("Standalone Balance Sheet", 2)}

    assert field_basis("total_equity", 1, pages, located(1, 2)) == (B.CONSOLIDATED, CITED_PAGE)
    assert field_basis("total_equity", 2, pages, located(1, 2)) == (B.STANDALONE, CITED_PAGE)


def test_a_page_without_a_title_inherits_from_the_first_page_of_its_run():
    pages = {1: page("Standalone Balance Sheet", 1), 2: page(None, 2), 3: page(None, 3)}

    assert field_basis("total_equity", 2, pages, located(1, 2, 3)) == (B.STANDALONE, RUN_START)
    assert field_basis("total_equity", 3, pages, located(1, 2, 3)) == (B.STANDALONE, RUN_START)


def test_a_run_that_starts_after_a_gap_does_not_inherit_across_it():
    pages = {1: page("Standalone Balance Sheet", 1), 3: page(None, 3)}

    assert field_basis("total_equity", 3, pages, located(1, 3)) == (B.UNKNOWN, None)


def test_the_run_is_that_of_the_fields_own_statement_type():
    pages = {1: page("Consolidated Statement of Profit and Loss", 1), 2: page(None, 2)}
    result = LocatorResult("keywords", (CandidatePage(1, ("income_statement",), 9, ()), CandidatePage(2, ("income_statement",), 5, ())))

    assert field_basis("revenue", 2, pages, result) == (B.CONSOLIDATED, RUN_START)
    assert field_basis("total_equity", 2, pages, result) == (B.UNKNOWN, None)  # a balance-sheet field has no run here


def test_a_page_range_has_no_runs_so_an_untitled_page_is_unknown():
    pages = {1: page("Consolidated Balance Sheet", 1), 2: page(None, 2)}
    result = LocatorResult("page_range", (CandidatePage(1, (), None, ()), CandidatePage(2, (), None, ())))

    assert field_basis("total_equity", 2, pages, result) == (B.UNKNOWN, None)
    assert field_basis("total_equity", 1, pages, result) == (B.CONSOLIDATED, CITED_PAGE)


def test_a_page_that_is_not_a_candidate_has_no_basis():
    assert field_basis("total_equity", 9, {1: page("Consolidated Balance Sheet", 1)}, located(1)) == (B.UNKNOWN, None)


def test_a_title_of_unknown_basis_is_not_replaced_by_the_runs_first_page():
    pages = {1: page("Consolidated Balance Sheet", 1), 2: page("Balance Sheet", 2)}

    assert field_basis("total_equity", 2, pages, located(1, 2)) == (B.UNKNOWN, CITED_PAGE)


# --- the configured-basis filter (D-06) --------------------------------------------------------------------


ITEMS = [("a", B.CONSOLIDATED), ("b", B.STANDALONE), ("c", B.UNKNOWN), ("d", None), ("e", B.CONSOLIDATED)]


def basis_of(item):
    return item[1]


def test_the_configured_basis_is_kept_and_other_known_bases_are_ignored():
    result = filter_by_basis(ITEMS, "consolidated", basis_of)

    assert [i[0] for i in result.kept] == ["a", "c", "d", "e"]
    assert [i[0] for i in result.ignored] == ["b"]


def test_with_another_configured_basis_the_other_fields_are_used():
    result = filter_by_basis(ITEMS, "standalone", basis_of)

    assert [i[0] for i in result.kept] == ["b", "c", "d"]
    assert [i[0] for i in result.ignored] == ["a", "e"]


def test_the_bases_present_are_recorded_without_unknown():
    assert filter_by_basis(ITEMS, "consolidated", basis_of).bases_present == ("consolidated", "standalone")
    assert filter_by_basis([("x", B.UNKNOWN)], "consolidated", basis_of).bases_present == ()
    assert filter_by_basis([], "consolidated", basis_of).bases_present == ()


def test_unknown_and_missing_bases_are_kept_so_the_analyst_sees_them():
    result = filter_by_basis([("c", B.UNKNOWN), ("d", None)], "standalone", basis_of)

    assert len(result.kept) == 2 and result.ignored == ()


def test_the_filter_keeps_the_order_and_does_not_mix_bases():
    result = filter_by_basis(ITEMS, "consolidated", basis_of)

    assert not any(i[1] is B.STANDALONE for i in result.kept)
    assert [i[0] for i in result.kept] == sorted(i[0] for i in result.kept)


def test_configured_locator_settings_decide_what_names_a_basis():
    settings = LocatorSettings(
        title_prefix_words=("consolidated", "standalone", "separate", "group"),
        basis_phrases={CONSOLIDATED: ("consolidated", "group"), "standalone": ("standalone", "separate")},
    )
    text = "Group Balance Sheet" + BODY

    assert page_basis(text) is None  # "group" is not a title prefix word by default
    assert page_basis(text, settings) is B.CONSOLIDATED
    assert field_basis("total_equity", 1, {1: PageText(1, text)}, located(1), settings) == (B.CONSOLIDATED, CITED_PAGE)


def test_configured_locator_settings_also_apply_to_the_first_page_of_a_run():
    settings = LocatorSettings(
        title_prefix_words=("consolidated", "standalone", "separate", "group"),
        basis_phrases={CONSOLIDATED: ("consolidated", "group"), "standalone": ("standalone", "separate")},
    )
    pages = {1: PageText(1, "Group Balance Sheet" + BODY), 2: page(None, 2)}

    assert field_basis("total_equity", 2, pages, located(1, 2), settings) == (B.CONSOLIDATED, RUN_START)
    assert field_basis("total_equity", 2, pages, located(1, 2)) == (B.UNKNOWN, None)
