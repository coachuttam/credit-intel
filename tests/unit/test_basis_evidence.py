"""How a field, the statement_basis attribute and a derived value carry the basis evidence (PRD H.1, H.1.2, H.4.6 v0.4.24; OD-10 option 3; step A2; B-279)."""

import pytest
from pydantic import ValidationError

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.borrowings import derive_total_borrowings
from credit_intel.calculations.derived import derive_ebit
from credit_intel.extraction.assertion import BasisAssertion
from credit_intel.extraction.attributes import blocking_reasons, verify_attributes
from credit_intel.models import (
    BasisEvidence as E,
    DocumentAttribute,
    DocumentAttributeName as N,
    FieldName as F,
    PeriodRole,
    ProposedAttribute,
    StatementBasis as B,
    Status,
)

COMP = PeriodRole.COMPARATIVE
ASSERTION = E.ANALYST_ASSERTION


def asserted(record):
    return record.model_copy(update={"basis_evidence": ASSERTION})


# --- the models --------------------------------------------------------------------------------------------------------------------------------


def test_a_field_has_the_title_as_its_basis_evidence_unless_said_otherwise():
    assert rec(F.REVENUE).basis_evidence is E.TITLE and asserted(rec(F.REVENUE)).basis_evidence is E.ANALYST_ASSERTION


def test_an_asserted_statement_basis_has_a_value_and_no_raw_text_page_or_quote():
    attribute = DocumentAttribute(attribute=N.STATEMENT_BASIS, normalised_value="consolidated", status=Status.EXTRACTED, basis_evidence=ASSERTION)

    assert attribute.page_number is None and attribute.evidence_quote is None and attribute.raw_text is None


@pytest.mark.parametrize(
    "changes",
    [
        {"page_number": 3},
        {"evidence_quote": "x"},
        {"raw_text": "x"},
        {"normalised_value": None},
        {"attribute": N.SCALE},
        {"status": Status.REQUIRES_REVIEW, "status_reason": "basis_unknown"},
        {"status": Status.NOT_FOUND},
    ],
)
def test_an_asserted_basis_that_carries_evidence_or_is_not_the_extracted_statement_basis_is_refused(changes):
    base = {"attribute": N.STATEMENT_BASIS, "normalised_value": "consolidated", "status": Status.EXTRACTED, "basis_evidence": ASSERTION}

    with pytest.raises(ValidationError):
        DocumentAttribute(**{**base, **changes})


def test_a_title_verified_basis_still_needs_its_evidence_and_only_statement_basis_has_a_basis_evidence():
    with pytest.raises(ValidationError):
        DocumentAttribute(attribute=N.STATEMENT_BASIS, normalised_value="consolidated", status=Status.EXTRACTED, basis_evidence=E.TITLE)
    with pytest.raises(ValidationError):
        DocumentAttribute(attribute=N.SCALE, raw_text="crore", normalised_value="crore", page_number=1, evidence_quote="in crore", status=Status.EXTRACTED, basis_evidence=E.TITLE)


# --- the statement_basis attribute under an assertion ---------------------------------------------------------------------------------------------


PAGES = {1: "Consolidated Balance Sheet as at 31 March 2025\nTotal current assets 1,482.30 1,356.75", 2: "Balance Sheet as at 31 March 2025\nTotal equity 600.00 500.00"}


def proposal(page, raw, value, quote):
    return ProposedAttribute(attribute=N.STATEMENT_BASIS, period_role=None, raw_text=raw, normalised_value=value, page_number=page, evidence_quote=quote)


def attribute(proposals, assertion, configured=B.CONSOLIDATED, pages=PAGES):
    return verify_attributes(proposals, pages, assertion=assertion, configured_basis=configured).statement_basis


APPLIED = BasisAssertion(B.CONSOLIDATED, (1, 2), (2,))
NOT_APPLIED = BasisAssertion(B.CONSOLIDATED, (1,), ())
TITLE_PROPOSAL = proposal(1, "Consolidated", "consolidated", "Consolidated Balance Sheet as at 31 March 2025")
BOGUS_PROPOSAL = proposal(2, "Consolidated", "consolidated", "Consolidated Balance Sheet as at 31 March 2025")  # not on page 2


def test_with_no_proposal_the_assertion_makes_the_attribute_extracted_without_page_or_quote():
    result = attribute([], APPLIED, pages={2: PAGES[2]})

    assert (result.status, result.normalised_value, result.basis_evidence) == (Status.EXTRACTED, "consolidated", ASSERTION)
    assert (result.page_number, result.evidence_quote, result.raw_text) == (None, None, None)


def test_a_proposal_that_cannot_be_verified_is_neither_needed_nor_used():
    result = attribute([BOGUS_PROPOSAL], APPLIED, pages={2: PAGES[2]})

    assert result.status is Status.EXTRACTED and result.basis_evidence is ASSERTION and result.page_number is None


def test_a_proposal_verified_from_a_title_block_is_unchanged_and_the_title_is_its_evidence():
    with_assertion = attribute([TITLE_PROPOSAL], APPLIED)
    without = attribute([TITLE_PROPOSAL], None)

    assert with_assertion == without and with_assertion.basis_evidence is E.TITLE and with_assertion.page_number == 1


def test_an_assertion_of_the_other_basis_than_the_configured_one_leaves_the_attribute_alone():
    result = attribute([], BasisAssertion(B.STANDALONE, (2,), (2,)), configured=B.CONSOLIDATED, pages={2: PAGES[2]})

    assert result.status is Status.NOT_FOUND and result.basis_evidence is None


def test_an_assertion_that_was_applied_to_no_page_leaves_the_attribute_alone():
    result = attribute([BOGUS_PROPOSAL], NOT_APPLIED, pages={2: PAGES[2]})

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason.value == "evidence_not_verified" and result.basis_evidence is None


def test_without_an_assertion_nothing_changes_and_a_missing_attribute_has_no_evidence():
    assert attribute([], None, pages={2: PAGES[2]}).basis_evidence is None
    assert attribute([TITLE_PROPOSAL], None).basis_evidence is E.TITLE


def test_without_a_configured_basis_the_assertion_is_not_used():
    result = verify_attributes([], {2: PAGES[2]}, assertion=APPLIED).statement_basis

    assert result.status is Status.NOT_FOUND


def test_an_asserted_attribute_does_not_block_the_fields_and_an_unverified_one_does():
    pages = {2: PAGES[2]}
    asserted_set = verify_attributes([], pages, assertion=APPLIED, configured_basis=B.CONSOLIDATED)
    plain = verify_attributes([], pages)

    assert [r.value for r in blocking_reasons(asserted_set, CUR) if r.value == "basis_unknown"] == []
    assert any(r.value == "basis_unknown" for r in blocking_reasons(plain, CUR))


# --- a derived value ------------------------------------------------------------------------------------------------------------------------------


def test_a_value_derived_from_an_asserted_input_is_asserted_and_otherwise_title():
    pbt, interest = rec(F.PROFIT_BEFORE_TAX, "150"), rec(F.INTEREST_EXPENSE, "30")

    assert derive_ebit(None, pbt, interest).basis_evidence is E.TITLE
    assert derive_ebit(None, asserted(pbt), interest).basis_evidence is ASSERTION
    assert derive_ebit(None, pbt, asserted(interest)).basis_evidence is ASSERTION


def test_a_derived_value_that_could_not_be_computed_still_records_the_evidence_of_the_inputs_it_had():
    pbt = asserted(rec(F.PROFIT_BEFORE_TAX, "150"))

    result = derive_ebit(None, pbt, None)

    assert result.status is Status.NOT_FOUND and result.basis_evidence is ASSERTION


def test_a_derived_total_of_borrowings_follows_the_same_rule():
    non_current, current = rec(F.BORROWINGS_NON_CURRENT, "700"), rec(F.BORROWINGS_CURRENT, "300")

    assert derive_total_borrowings(non_current, current, None).basis_evidence is E.TITLE
    assert derive_total_borrowings(non_current, asserted(current), None).basis_evidence is ASSERTION
