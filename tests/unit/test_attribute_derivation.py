"""The code reads the currency and scale from the pages when the model gave none that is usable (PRD v0.4.37, H.1.2; Appendix B.6 rows 102 to 108; B-310). Synthetic pages."""

import pytest

from credit_intel.extraction.attributes import AttributeDerivation, blocking_reasons, verify_attributes
from credit_intel.models import DocumentAttributeName as Name, PeriodRole, ProposedAttribute, Status, StatusReason as Reason

P1 = "Acme Inc\nINCOME STATEMENTS\n(In millions, except per share amounts)\nRevenue $ 100.00 90.00"
P2 = "Acme Inc\nBALANCE SHEETS\n(In millions)\nCash $ 50.00 40.00"
PAGES = {1: P1, 2: P2}


def attr(name, raw, norm, quote, page=1, role=None):
    return ProposedAttribute(attribute=name, period_role=role, raw_text=raw, normalised_value=norm, page_number=page, evidence_quote=quote)


def verified(proposed, pages=PAGES):
    return verify_attributes(proposed, pages)


# --- derived ---------------------------------------------------------------------------------------------------------------------


def test_b6_row_102_no_scale_proposal_and_one_scale_on_the_pages_is_read_by_the_code():
    result = verified([])

    assert result.scale.status is Status.EXTRACTED and result.scale.normalised_value == "millions"
    assert result.scale.page_number == 1 and result.scale.evidence_quote == "(In millions, except per share amounts)" and result.scale.raw_text == result.scale.evidence_quote
    assert AttributeDerivation("scale", 1, "no_proposal") in result.derivations


def test_b6_row_103_a_currency_proposal_without_its_raw_text_in_the_quote_is_replaced_by_the_one_the_pages_declare():
    result = verified([attr(Name.REPORTING_CURRENCY, "somewhere else", "USD", "(In millions)", 2)])

    assert result.reporting_currency.status is Status.EXTRACTED and result.reporting_currency.normalised_value == "USD"
    assert result.reporting_currency.page_number == 1 and result.reporting_currency.evidence_quote == "Revenue $ 100.00 90.00"  # the first line that holds the sign
    assert AttributeDerivation("reporting_currency", 1, "value_not_in_evidence") in result.derivations


def test_a_proposal_whose_quote_is_on_no_page_is_replaced_and_the_reason_is_recorded():
    result = verified([attr(Name.SCALE, "In billions", "billions", "(In billions)", 1)])

    assert result.scale.normalised_value == "millions" and AttributeDerivation("scale", 1, "evidence_not_verified") in result.derivations


def test_the_lowest_numbered_page_that_declares_it_is_used():
    pages = {1: "Acme Inc\nINCOME STATEMENTS", 2: P2, 3: "NOTE\n(In millions)\nOther $ 5"}

    result = verified([], pages)

    assert result.scale.page_number == 2 and result.reporting_currency.page_number == 2


def test_the_derived_attributes_unblock_the_fields_that_depended_on_them():
    pages = PAGES
    proposals = [
        attr(Name.STATEMENT_BASIS, "Consolidated", "consolidated", "Consolidated Balance Sheets", 1),
        attr(Name.PERIOD_END, "June 30, 2025", "2025-06-30", "June 30, 2025 2024", 1, PeriodRole.CURRENT),
    ]
    both = {1: P1 + "\nConsolidated Balance Sheets\nJune 30, 2025 2024", 2: P2}

    result = verified(proposals, both)

    assert Reason.CURRENCY_NOT_VERIFIED not in blocking_reasons(result, PeriodRole.CURRENT) and Reason.SCALE_NOT_VERIFIED not in blocking_reasons(result, PeriodRole.CURRENT)
    assert pages is PAGES


# --- never derived ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("proposal", "reason"),
    [
        (attr(Name.SCALE, "In millions", "crore", "(In millions)", 2), Reason.SCALE_NOT_VERIFIED),  # b6 row 104: the model's claim contradicts the page
        (attr(Name.REPORTING_CURRENCY, "In millions", "INR", "(In millions)", 2), Reason.CURRENCY_NOT_VERIFIED),
    ],
)
def test_b6_row_104_a_claim_the_pages_contradict_is_not_replaced(proposal, reason):
    result = verified([proposal])

    record = result.scale if proposal.attribute is Name.SCALE else result.reporting_currency
    assert record.status is Status.REQUIRES_REVIEW and record.status_reason is reason
    assert not [d for d in result.derivations if d.attribute == proposal.attribute.value]  # the other attribute, which has no proposal, may still be read


def test_b6_row_105_two_scales_on_the_candidate_pages_derive_nothing():
    result = verified([], {1: P1, 2: "Notes\n(In thousands)\nOther $ 5"})

    assert result.scale.status is Status.NOT_FOUND and not [d for d in result.derivations if d.attribute == "scale"]


def test_b6_row_106_two_currencies_on_the_candidate_pages_derive_nothing():
    result = verified([], {1: P1, 2: "Notes\n(In millions)\nOther ₹ 5"})

    assert result.reporting_currency.status is Status.NOT_FOUND and not [d for d in result.derivations if d.attribute == "reporting_currency"]
    assert result.scale.status is Status.EXTRACTED  # the other attribute does not conflict


def test_b6_row_107_a_verified_proposal_is_kept_and_nothing_is_recorded():
    result = verified([attr(Name.SCALE, "In millions", "millions", "(In millions)", 2), attr(Name.REPORTING_CURRENCY, "In millions", "USD", "(In millions)", 2)])

    assert result.scale.page_number == 2 and result.reporting_currency.page_number == 2 and result.derivations == ()


def test_b6_row_108_pages_that_declare_nothing_leave_the_attributes_not_found():
    result = verified([], {1: "Acme Inc\nINCOME STATEMENTS\nRevenue 100.00"})

    assert result.scale.status is Status.NOT_FOUND and result.reporting_currency.status is Status.NOT_FOUND and result.derivations == ()


def test_a_declaration_that_is_not_on_one_line_is_not_quoted_so_not_derived():
    result = verified([], {1: "Acme Inc\nAmounts in\nmillions of dollars\nRevenue 100.00"})

    assert result.scale.status is Status.NOT_FOUND and not [d for d in result.derivations if d.attribute == "scale"]


def test_only_the_currency_and_the_scale_are_ever_derived():
    result = verified([])

    assert result.statement_basis.status is Status.NOT_FOUND and result.entity_name.status is Status.NOT_FOUND
    assert result.current_period_end.status is Status.NOT_FOUND and result.comparative_period_end.status is Status.NOT_FOUND
    assert {d.attribute for d in result.derivations} == {"reporting_currency", "scale"}


def test_a_declaration_the_page_repair_can_verify_is_repaired_not_derived():
    result = verified([attr(Name.SCALE, "In millions", "millions", "(In millions)", 1)])  # cited page 1, quote on page 2

    assert result.scale.page_number == 2 and result.page_repairs and not [d for d in result.derivations if d.attribute == "scale"]


def test_a_conflict_that_stopped_the_page_repair_does_not_let_the_derivation_in_either():
    pages = {1: P1, 2: P2, 3: "Notes\n(In thousands)\nOther $ 5"}

    result = verified([attr(Name.SCALE, "In millions", "millions", "(In millions)", 1)], pages)

    assert result.scale.status_reason is Reason.SCALE_AMBIGUOUS and not [d for d in result.derivations if d.attribute == "scale"] and result.page_repairs == ()
