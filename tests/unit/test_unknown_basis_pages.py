"""Pages of unknown basis are not sent (PRD H.4.6 and FR-013 as amended in v0.4.21; B-235).

Appendix B.6 examples 27 to 33. Synthetic page text and a hand-built locator result: no PDF,
no model.
"""

import random

import pytest

from credit_intel.extraction.bases import BASIS_UNKNOWN_REASON, drop_unknown_basis_pages
from credit_intel.ingestion.models import CandidatePage, ExcludedCandidate, LocatorResult, PageText

BS, IS = "balance_sheet", "income_statement"
FIGURES = "Total assets 1,740.00 1,600.00"


def text(title: str | None) -> str:
    head = f"Acme Limited\n{title}\n" if title else "Acme Limited\n"
    return head + "(Rs. in crore)\n" + FIGURES


def candidate(number, *types, score=5):
    return CandidatePage(number, tuple(sorted(types)), score, ())


def drop(titles: dict[int, str | None], types: dict[int, tuple[str, ...]], method="keywords", excluded=()):
    pages = {n: PageText(n, text(t)) for n, t in titles.items()}
    located = LocatorResult(method, tuple(candidate(n, *types[n]) for n in sorted(types)), excluded_candidates=tuple(excluded))
    return drop_unknown_basis_pages(pages, located), located


def numbers(result):
    return [c.page_number for c in result.candidates]


def reasons(result):
    return [(e.page_number, e.statement_type, e.reason, e.chain_start_page) for e in result.excluded_candidates]


def test_b6_row_27_untitled_pages_go_and_the_titled_ones_stay():
    result, _ = drop(
        {10: "Balance Sheet", 11: None, 20: "Consolidated Balance Sheet", 21: None},
        {10: (BS,), 11: (BS,), 20: (BS,), 21: (BS,)},
    )

    assert numbers(result) == [20, 21]  # 21 is a continuation of the consolidated page 20
    assert reasons(result) == [(10, BS, BASIS_UNKNOWN_REASON, 10), (11, BS, BASIS_UNKNOWN_REASON, 10)]


def test_b6_row_29_a_continuation_of_a_titled_page_inherits_its_basis():
    result, _ = drop({20: "Consolidated Balance Sheet", 21: None}, {20: (BS,), 21: (BS,)})

    assert numbers(result) == [20, 21] and result.excluded_candidates == ()


def test_b6_row_30_a_continuation_of_an_untitled_page_is_removed_with_its_run():
    result, _ = drop({10: "Balance Sheet", 11: None, 20: "Consolidated Balance Sheet"}, {10: (BS,), 11: (BS,), 20: (BS,)})

    assert numbers(result) == [20]
    assert [(e.page_number, e.chain_start_page) for e in result.excluded_candidates] == [(10, 10), (11, 10)]


def test_b6_row_32_a_page_of_the_other_known_basis_stays():
    result, _ = drop(
        {10: "Standalone Balance Sheet", 20: "Consolidated Balance Sheet"}, {10: (BS,), 20: (BS,)}
    )

    assert numbers(result) == [10, 20] and result.excluded_candidates == ()


def test_a_title_that_names_both_bases_is_unknown_and_removed():
    result, _ = drop({10: "Consolidated and Standalone Balance Sheet", 20: "Consolidated Balance Sheet"}, {10: (BS,), 20: (BS,)})

    assert numbers(result) == [20] and reasons(result) == [(10, BS, BASIS_UNKNOWN_REASON, 10)]


def test_b6_row_33_a_page_of_two_types_is_removed_only_if_unknown_for_every_type():
    # Page 11 is untitled; it continues the consolidated balance sheet on 10 but starts its own
    # income-statement run, so it is known for one type chain and stays.
    result, _ = drop(
        {10: "Consolidated Balance Sheet", 11: None},
        {10: (BS,), 11: (BS, IS)},
    )

    assert numbers(result) == [10, 11] and result.excluded_candidates == ()


def test_a_page_of_two_types_unknown_for_both_is_removed_with_one_entry_per_type():
    result, _ = drop(
        {10: "Balance Sheet", 11: "Consolidated Balance Sheet"},
        {10: (BS, IS), 11: (BS,)},
    )

    assert numbers(result) == [11]
    assert reasons(result) == [(10, BS, BASIS_UNKNOWN_REASON, 10), (10, IS, BASIS_UNKNOWN_REASON, 10)]


def test_b6_row_31_a_page_range_is_returned_as_it_is():
    result, original = drop({10: "Balance Sheet"}, {10: ()}, method="page_range")

    assert result is original


def test_earlier_exclusions_are_kept_and_the_record_stays_in_page_then_type_order():
    earlier = ExcludedCandidate(15, BS, "cap", 3, 15)
    result, _ = drop({10: "Balance Sheet", 20: "Consolidated Balance Sheet"}, {10: (BS,), 20: (BS,)}, excluded=[earlier])

    assert [(e.page_number, e.reason) for e in result.excluded_candidates] == [(10, BASIS_UNKNOWN_REASON), (15, "cap")]


def test_nothing_to_remove_returns_the_same_result():
    result, original = drop({10: "Consolidated Balance Sheet"}, {10: (BS,)})

    assert result is original


def test_kept_candidates_are_unchanged_and_in_page_order():
    result, original = drop(
        {10: "Balance Sheet", 20: "Consolidated Balance Sheet", 30: "Standalone Balance Sheet"},
        {10: (BS,), 20: (BS,), 30: (BS,)},
    )

    assert list(result.candidates) == [c for c in original.candidates if c.page_number != 10]


@pytest.mark.parametrize("seed", range(20))
def test_property_no_unknown_page_survives_and_removed_plus_kept_is_the_input(seed):
    rng = random.Random(seed)
    titles = {n: rng.choice([None, "Balance Sheet", "Consolidated Balance Sheet", "Standalone Balance Sheet"]) for n in range(1, 13)}
    types = {n: (BS,) for n in titles}

    result, original = drop(titles, types)

    removed = {e.page_number for e in result.excluded_candidates}
    assert removed.isdisjoint(numbers(result))
    assert sorted(removed | set(numbers(result))) == numbers(original)
    # a surviving page is titled with a known basis or continues such a page
    for n in numbers(result):
        start = n
        while start - 1 in titles and start - 1 in numbers(original):
            start -= 1
        own = titles[n]
        assert (own and ("onsolidated" in own or "tandalone" in own)) or (own is None and titles[start] and ("onsolidated" in titles[start] or "tandalone" in titles[start]))
