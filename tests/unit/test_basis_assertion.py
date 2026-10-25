"""The analyst's assertion of the statement basis: where it applies and what stops the run (PRD H.4.6 v0.4.24, FR-013 rule 7; OD-10 option 3; step A1; B-277).

Synthetic page text only. The assertion fills pages whose basis is unknown and never overrides a page's own title.
"""

import pytest

from credit_intel.extraction.assertion import ASSERTABLE, BasisAssertion, apply_assertion
from credit_intel.extraction.bases import page_basis
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.locator import check_statement_basis
from credit_intel.ingestion.models import CandidatePage, LocatorResult, PageText
from credit_intel.models import StatementBasis as B

BODY = "\nParticulars Note 31 March 2025 31 March 2024\nTotal current assets 14 1,482.30 1,356.75\n"
TEXTS = {
    "consolidated": "Consolidated Balance Sheet as at 31 March 2025" + BODY,
    "standalone": "Standalone Balance Sheet as at 31 March 2025" + BODY,
    "untitled": "Balance Sheet as at 31 March 2025" + BODY,
    "both": "Consolidated and Standalone Balance Sheet as at 31 March 2025" + BODY,
    "none": "The directors present their report." + BODY,
    "empty": "",
}


def document(*kinds):
    pages = {n: PageText(n, TEXTS[kind]) for n, kind in enumerate(kinds, 1)}
    located = LocatorResult("page_range", tuple(CandidatePage(n, (), None, ()) for n in pages))
    return pages, located


def test_the_fixtures_have_the_bases_the_tests_assume():
    expected = {"consolidated": B.CONSOLIDATED, "standalone": B.STANDALONE, "untitled": B.UNKNOWN, "both": B.UNKNOWN, "none": None, "empty": None}

    assert {kind: page_basis(text) for kind, text in TEXTS.items()} == expected


@pytest.mark.parametrize("kind", ["untitled", "both", "none", "empty"])
def test_the_assertion_applies_to_a_page_whose_basis_is_unknown_or_has_no_title(kind):
    pages, located = document(kind)

    result = apply_assertion(pages, located, B.CONSOLIDATED)

    assert result == BasisAssertion(B.CONSOLIDATED, (1,), (1,))


@pytest.mark.parametrize(("asserted", "kind"), [(B.CONSOLIDATED, "consolidated"), (B.STANDALONE, "standalone")])
def test_a_page_whose_own_title_names_the_asserted_basis_keeps_it_and_the_assertion_is_not_applied(asserted, kind):
    pages, located = document(kind, kind)

    assert apply_assertion(pages, located, asserted) == BasisAssertion(asserted, (1, 2), ())


@pytest.mark.parametrize(("asserted", "kind", "other_page"), [(B.CONSOLIDATED, "standalone", 2), (B.STANDALONE, "consolidated", 1)])
def test_a_page_whose_title_names_the_other_basis_stops_the_run_naming_the_page(asserted, kind, other_page):
    pages, located = document("consolidated", "standalone")

    with pytest.raises(IngestionError) as caught:
        apply_assertion(pages, located, asserted)

    assert caught.value.code is ErrorCode.BASIS_UNAVAILABLE and str(other_page) in caught.value.detail
    assert f"asserted basis: {asserted.value}" in caught.value.detail


def test_every_conflicting_page_is_named_in_ascending_order_and_nothing_else_is(tmp_path):
    pages, located = document("standalone", "untitled", "consolidated", "standalone", "none")

    with pytest.raises(IngestionError) as caught:
        apply_assertion(pages, located, B.CONSOLIDATED)

    assert caught.value.detail.endswith("pages whose title names the other basis: 1, 4")
    assert "Balance Sheet" not in str(caught.value) and "1,482.30" not in str(caught.value)


def test_a_conflict_is_never_resolved_by_skipping_the_page_even_when_most_pages_agree():
    pages, located = document(*["untitled"] * 9, "standalone")

    with pytest.raises(IngestionError):
        apply_assertion(pages, located, B.CONSOLIDATED)


def test_a_page_with_no_title_line_is_not_given_the_basis_of_an_earlier_page_because_a_range_has_no_runs():
    pages, located = document("consolidated", "none", "untitled")

    result = apply_assertion(pages, located, B.CONSOLIDATED)

    assert result.applied_pages == (2, 3) and result.pages == (1, 2, 3)


def test_applied_pages_and_pages_are_ascending_whatever_the_order_of_the_candidates():
    pages, located = document("untitled", "consolidated", "none")
    located = LocatorResult("page_range", tuple(reversed(located.candidates)))

    assert apply_assertion(pages, located, B.CONSOLIDATED) == BasisAssertion(B.CONSOLIDATED, (1, 2, 3), (1, 3))


def test_only_consolidated_and_standalone_can_be_asserted_and_only_for_a_page_range():
    pages, located = document("untitled")
    keywords = LocatorResult("keywords", located.candidates)

    assert ASSERTABLE == (B.CONSOLIDATED, B.STANDALONE)
    with pytest.raises(ValueError):
        apply_assertion(pages, located, B.UNKNOWN)
    with pytest.raises(ValueError):
        apply_assertion(pages, keywords, B.CONSOLIDATED)


def test_the_assertion_does_not_change_its_inputs_and_gives_the_same_answer_twice():
    pages, located = document("untitled", "consolidated")
    before = dict(pages)

    assert apply_assertion(pages, located, B.CONSOLIDATED) == apply_assertion(pages, located, B.CONSOLIDATED) and pages == before


# --- the basis gate counts asserted pages -------------------------------------------------------------------------------------------------------


def gate(kinds, configured="consolidated", asserted=None):
    pages, located = document(*kinds)
    return check_statement_basis(list(pages.values()), located, configured, asserted_basis=asserted)


def test_without_an_assertion_untitled_pages_stop_the_gate_as_before():
    with pytest.raises(IngestionError) as caught:
        gate(["untitled"])

    assert caught.value.code is ErrorCode.BASIS_UNAVAILABLE and "bases found: unknown" in caught.value.detail


def test_an_asserted_basis_equal_to_the_configured_one_passes_the_gate():
    assert gate(["untitled", "none"], asserted="consolidated") == ("consolidated", "unknown")


def test_an_asserted_basis_other_than_the_configured_one_stops_the_gate_and_is_marked():
    with pytest.raises(IngestionError) as caught:
        gate(["untitled"], configured="consolidated", asserted="standalone")

    assert "bases found: standalone (asserted), unknown" in caught.value.detail and "configured basis: consolidated" in caught.value.detail


def test_an_asserted_basis_that_a_title_also_names_is_not_marked():
    with pytest.raises(IngestionError) as caught:
        gate(["standalone"], configured="consolidated", asserted="standalone")

    assert "bases found: standalone" in caught.value.detail and "(asserted)" not in caught.value.detail


def test_no_assertion_leaves_the_gate_result_unchanged():
    assert gate(["consolidated", "standalone"]) == ("consolidated", "standalone")
