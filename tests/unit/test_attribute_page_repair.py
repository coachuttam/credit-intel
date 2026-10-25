"""A currency or scale declaration is verified on the page that holds it (PRD v0.4.36, H.1.2; Appendix B.6 rows 96 to 101; B-307). Synthetic pages."""

from credit_intel.extraction.attributes import PageRepair, verify_attributes
from credit_intel.models import DocumentAttributeName as Name, PeriodRole, ProposedAttribute, Status, StatusReason as Reason

P1 = "Acme Inc\nINCOME STATEMENTS\n(In millions, except per share amounts)\nRevenue $ 100.00 90.00"
P2 = "Acme Inc\nBALANCE SHEETS\n(In millions)\nCash $ 50.00 40.00"
P3 = "Acme Inc\nNOTE 3\n(In millions)\nOther $ 5.00 4.00"
PAGES = {1: P1, 2: P2, 3: P3}
QUOTE = "(In millions)"  # on pages 2 and 3, not on page 1


def attr(name, raw, norm, quote, page, role=None):
    return ProposedAttribute(attribute=name, period_role=role, raw_text=raw, normalised_value=norm, page_number=page, evidence_quote=quote)


def declarations(page):
    return [attr(Name.REPORTING_CURRENCY, "In millions", "USD", QUOTE, page), attr(Name.SCALE, "In millions", "millions", QUOTE, page)]


def verified(proposed, pages=PAGES):
    return verify_attributes(proposed, pages)


# --- the repair ------------------------------------------------------------------------------------------------------------------


def test_b6_row_96_a_declaration_cited_on_the_wrong_page_is_verified_on_the_page_that_holds_it():
    result = verified(declarations(1))

    assert result.reporting_currency.status is Status.EXTRACTED and result.reporting_currency.page_number == 2
    assert result.scale.status is Status.EXTRACTED and result.scale.page_number == 2 and result.scale.normalised_value == "millions"
    assert result.page_repairs == (PageRepair("reporting_currency", 1, 2), PageRepair("scale", 1, 2))


def test_the_lowest_numbered_page_that_holds_the_quote_is_used():
    assert verified(declarations(1)).scale.page_number == 2  # the quote is on pages 2 and 3
    assert verified(declarations(3)).scale.page_number == 3 and verified(declarations(3)).page_repairs == ()  # cited right: nothing to repair


def test_b6_row_97_a_declaration_cited_on_the_right_page_is_unchanged():
    result = verified(declarations(2))

    assert result.scale.page_number == 2 and result.reporting_currency.status is Status.EXTRACTED and result.page_repairs == ()


def test_a_cited_page_that_is_not_a_candidate_is_repaired_too():
    result = verified(declarations(9))  # the model cited a page that is not in the run

    assert result.scale.page_number == 2 and result.page_repairs[0].cited_page == 9


def test_b6_row_98_a_quote_that_is_on_no_candidate_page_is_still_not_verified():
    result = verified([attr(Name.SCALE, "In billions", "billions", "(In billions)", 1), attr(Name.REPORTING_CURRENCY, "In billions", "USD", "(In billions)", 1)])

    assert result.scale.status is Status.REQUIRES_REVIEW and result.scale.status_reason is Reason.EVIDENCE_NOT_VERIFIED
    assert result.reporting_currency.status_reason is Reason.EVIDENCE_NOT_VERIFIED and result.page_repairs == ()


def test_the_declaration_tests_still_apply_to_the_repaired_text():
    wrong_scale = [attr(Name.SCALE, "In millions", "thousands", QUOTE, 1)]
    wrong_currency = [attr(Name.REPORTING_CURRENCY, "In millions", "EUR", QUOTE, 1)]

    assert verified(wrong_scale).scale.status_reason is Reason.SCALE_NOT_VERIFIED
    assert verified(wrong_currency).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_the_raw_text_must_still_be_in_the_quote():
    result = verified([attr(Name.SCALE, "In thousands", "millions", QUOTE, 1)])

    assert result.scale.status_reason is Reason.VALUE_NOT_IN_EVIDENCE


# --- what is never repaired ----------------------------------------------------------------------------------------------------


def test_b6_row_99_the_statement_basis_the_period_end_and_the_entity_name_keep_the_strict_rule():
    pages = {1: "Acme Inc\nINCOME STATEMENTS", 2: "Acme Inc\nConsolidated Balance Sheets\nJune 30, 2025 2024"}
    proposals = [
        attr(Name.STATEMENT_BASIS, "Consolidated", "consolidated", "Consolidated Balance Sheets", 1),  # cited page 1, on page 2
        attr(Name.PERIOD_END, "June 30, 2025", "2025-06-30", "June 30, 2025 2024", 1, role=PeriodRole.CURRENT),  # cited page 1, on page 2
        attr(Name.ENTITY_NAME, "Acme Inc", "Acme Inc", "Acme Inc", 3),
    ]

    result = verified(proposals, pages)

    assert result.statement_basis.status is Status.REQUIRES_REVIEW and result.current_period_end.status is Status.REQUIRES_REVIEW
    assert result.page_repairs == () and result.statement_basis.page_number == 1 and result.current_period_end.page_number == 1


# --- conflicting declarations: no repair ---------------------------------------------------------------------------------------


def test_b6_row_100_candidate_pages_that_declare_two_scales_are_not_repaired():
    pages = {1: P1, 2: P2, 3: "Acme Inc\nNOTE 4\n(In thousands)\nOther $ 5"}

    result = verified(declarations(1), pages)

    assert result.scale.status is Status.REQUIRES_REVIEW and result.scale.status_reason is Reason.SCALE_AMBIGUOUS
    assert result.scale.page_number == 1  # the scale was not moved to page 2
    assert result.page_repairs == (PageRepair("reporting_currency", 1, 2),)  # the currency, which does not conflict, was


def test_b6_row_101_candidate_pages_that_declare_two_currencies_are_not_repaired():
    pages = {1: P1, 2: P2, 3: "Acme Inc\nNOTE 4\n(In millions)\nOther ₹ 5"}

    result = verified(declarations(1), pages)

    assert result.reporting_currency.status is Status.REQUIRES_REVIEW and result.reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED
    assert result.reporting_currency.page_number == 1 and result.page_repairs == (PageRepair("scale", 1, 2),)  # the scale, which does not conflict, was repaired


def test_a_scale_conflict_blocks_only_the_scale_and_a_currency_conflict_only_the_currency():
    scale_conflict = {1: P1, 2: P2, 3: "Acme Inc\n(In thousands)\nOther $ 5"}
    currency_conflict = {1: P1, 2: P2, 3: "Acme Inc\n(In millions)\nOther ₹ 5"}

    one = verified(declarations(1), scale_conflict)
    two = verified(declarations(1), currency_conflict)

    assert one.reporting_currency.status is Status.EXTRACTED and one.scale.status is Status.REQUIRES_REVIEW
    assert two.scale.status is Status.EXTRACTED and two.reporting_currency.status is Status.REQUIRES_REVIEW


def test_a_conflict_does_not_matter_when_the_quote_is_already_on_the_cited_page():
    pages = {1: P1, 2: P2, 3: "Acme Inc\n(In thousands)\nOther ₹ 5"}

    result = verified(declarations(2), pages)

    assert result.scale.status is Status.EXTRACTED and result.page_repairs == ()  # the strict path is unchanged: nothing to repair, so nothing to refuse
