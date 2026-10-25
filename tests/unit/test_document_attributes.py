"""Document-level attributes (PRD H.1.2, FR-005.9, H.1.1, H.4.6; step 7d; B-215).

Appendix B.6 rows 3 to 6, 9 and 22. Synthetic page text only.
"""

import random
from datetime import date

import pytest

from credit_intel.extraction.attributes import blocking_reason, verify_attributes
from credit_intel.extraction.periods import Method
from credit_intel.models import (
    DocumentAttributeName as Name,
    PeriodRole,
    ProposedAttribute,
    Status,
    StatusReason as Reason,
)

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE

PAGE = (
    "Acme Industries Limited\n"
    "Consolidated Balance Sheet\n"
    "As at 31 March 2025 31 March 2024\n"
    "(₹ in crore)\n"
    "Total current assets 14 1,482.30 1,356.75"
)
PAGES = {112: PAGE}


def attr(name, raw, norm, quote=None, role=None, page=112):
    return ProposedAttribute(
        attribute=name,
        period_role=role,
        raw_text=raw,
        normalised_value=norm,
        page_number=page,
        evidence_quote=quote or raw,
    )


ENTITY = attr(Name.ENTITY_NAME, "Acme Industries Limited", "Acme Industries Limited")
CURRENT = attr(Name.PERIOD_END, "31 March 2025", "2025-03-31", "As at 31 March 2025 31 March 2024", CUR)
COMPARATIVE = attr(Name.PERIOD_END, "31 March 2024", "2024-03-31", "As at 31 March 2025 31 March 2024", COMP)
BASIS = attr(Name.STATEMENT_BASIS, "Consolidated", "consolidated", "Consolidated Balance Sheet")
CURRENCY = attr(Name.REPORTING_CURRENCY, "₹", "INR", "(₹ in crore)")
SCALE = attr(Name.SCALE, "in crore", "crore", "(₹ in crore)")
ALL = [ENTITY, CURRENT, COMPARATIVE, BASIS, CURRENCY, SCALE]


def verify(proposed=ALL, pages=PAGES):
    return verify_attributes(proposed, pages)


def replaced(old, **changes):
    return old.model_copy(update=changes)


def without(*removed):
    return [a for a in ALL if a not in removed]


# --- a clean document -------------------------------------------------------------------------


def test_a_clean_document_has_every_attribute_extracted():
    result = verify()

    assert all(a.status is Status.EXTRACTED and a.status_reason is None for a in result.all)
    assert result.period_end(CUR) == date(2025, 3, 31) and result.period_end(COMP) == date(2024, 3, 31)
    assert len(result.all) == 6


def test_extracted_records_keep_the_evidence_as_proposed():
    result = verify()

    assert result.reporting_currency.raw_text == "₹"
    assert result.reporting_currency.normalised_value == "INR"
    assert result.reporting_currency.page_number == 112
    assert result.reporting_currency.evidence_quote == "(₹ in crore)"


def test_period_evidence_records_how_each_period_was_validated():
    result = verify()

    assert result.period_evidence[CUR].method is Method.FULL_DATE
    assert result.period_evidence[COMP].raw_text == "31 March 2024"


# --- nothing proposed ------------------------------------------------------------------------------


def test_attributes_that_are_not_proposed_are_not_found():
    result = verify([])

    assert all(a.status is Status.NOT_FOUND and a.status_reason is None for a in result.all)
    assert result.current_period_end.period_role is CUR and result.comparative_period_end.period_role is COMP
    assert result.period_end(CUR) is None and result.period_end(COMP) is None


def test_a_missing_comparative_is_not_found_and_the_current_stands():
    result = verify(without(COMPARATIVE))

    assert result.comparative_period_end.status is Status.NOT_FOUND
    assert result.current_period_end.status is Status.EXTRACTED


# --- evidence (FR-005.1, FR-005.2) ------------------------------------------------------------------------


@pytest.mark.parametrize("original", ALL)
def test_a_quote_that_is_not_on_the_page_is_not_verified(original):
    bad = replaced(original, evidence_quote="Text that is nowhere on the page", raw_text="Text that is nowhere")
    result = verify([bad if a is original else a for a in ALL])

    record = {Name.ENTITY_NAME: result.entity_name, Name.STATEMENT_BASIS: result.statement_basis,
              Name.REPORTING_CURRENCY: result.reporting_currency, Name.SCALE: result.scale}.get(original.attribute)
    if record is None:
        record = result.current_period_end if original.period_role is CUR else result.comparative_period_end
    assert record.status is Status.REQUIRES_REVIEW and record.status_reason is Reason.EVIDENCE_NOT_VERIFIED


@pytest.mark.parametrize("original", [ENTITY, BASIS, CURRENCY, SCALE])
def test_raw_text_outside_the_quote_is_not_in_evidence(original):
    bad = replaced(original, raw_text="somewhere else")
    result = verify([bad if a is original else a for a in ALL])

    records = [result.entity_name, result.statement_basis, result.reporting_currency, result.scale]
    assert any(r.status_reason is Reason.VALUE_NOT_IN_EVIDENCE for r in records)


def test_a_quote_from_a_page_that_is_not_a_candidate_is_not_verified():
    result = verify([replaced(ENTITY, page_number=7)] + ALL[1:])

    assert result.entity_name.status_reason is Reason.EVIDENCE_NOT_VERIFIED


# --- period-ends (Appendix B.6 rows 3 to 6 and 22) ----------------------------------------------------------


def test_b6_row_3_two_full_dates_are_both_validated():
    assert verify().current_period_end.normalised_value == "2025-03-31"
    assert verify().comparative_period_end.normalised_value == "2024-03-31"


def test_b6_row_4_ambiguous_numeric_dates_are_not_guessed():
    page = "Balance Sheet\nAs at 03/04/2025 03/04/2024\nTotal assets 1,740.00"
    cur = attr(Name.PERIOD_END, "03/04/2025", "2025-04-03", "As at 03/04/2025 03/04/2024", CUR)
    comp = attr(Name.PERIOD_END, "03/04/2024", "2024-04-03", "As at 03/04/2025 03/04/2024", COMP)

    result = verify([cur, comp], {112: page})

    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.comparative_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert blocking_reason(result, CUR) is Reason.PERIOD_MISMATCH
    assert blocking_reason(result, COMP) is Reason.PERIOD_MISMATCH


def test_b6_row_5_a_financial_year_header_is_validated_by_the_title_date():
    page = "Balance Sheet for the year ended 31 March 2025\nParticulars 2024-25\nTotal assets 1,740.00"
    cur = attr(Name.PERIOD_END, "2024-25", "2025-03-31", "Particulars 2024-25", CUR)

    result = verify([cur], {112: page})

    assert result.current_period_end.status is Status.EXTRACTED
    assert result.current_period_end.raw_text == "2024-25"
    assert result.period_evidence[CUR].method is Method.YEAR_WITH_PAGE_DATE


def test_b6_row_6_a_comparative_two_years_back_fails_the_consecutive_rule():
    page = "Balance Sheet\nAs at 31 March 2025 31 March 2023\nTotal assets 1,740.00"
    quote = "As at 31 March 2025 31 March 2023"
    cur = attr(Name.PERIOD_END, "31 March 2025", "2025-03-31", quote, CUR)
    comp = attr(Name.PERIOD_END, "31 March 2023", "2023-03-31", quote, COMP)

    result = verify([cur, comp], {112: page})

    assert result.current_period_end.status is Status.EXTRACTED
    assert result.comparative_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.period_end(COMP) is None
    assert blocking_reason(result, CUR) is not Reason.PERIOD_MISMATCH


def test_b6_row_22_the_comparative_year_is_derived_from_the_current():
    page = "Balance Sheet\nAs at March 31,\n2025 2024\nTotal assets 1,740.00 1,600.00\nDated 31 March 2025"
    cur = attr(Name.PERIOD_END, "2025", "2025-03-31", "2025 2024", CUR)
    comp = attr(Name.PERIOD_END, "2024", "2024-03-31", "2025 2024", COMP)

    result = verify([cur, comp], {112: page})

    assert result.period_end(CUR) == date(2025, 3, 31)
    assert result.period_end(COMP) == date(2024, 3, 31)
    assert result.period_evidence[COMP].method is Method.DERIVED_COMPARATIVE
    assert result.period_evidence[COMP].derived_from == date(2025, 3, 31)


def test_the_comparative_is_not_derived_when_the_current_is_not_validated():
    page = "Balance Sheet\n2025 2024\nTotal assets 1,740.00"
    cur = attr(Name.PERIOD_END, "2025", "2025-03-31", "2025 2024", CUR)
    comp = attr(Name.PERIOD_END, "2024", "2024-03-31", "2025 2024", COMP)

    result = verify([cur, comp], {112: page})

    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.comparative_period_end.status_reason is Reason.PERIOD_MISMATCH


def test_a_derived_comparative_needs_the_current_on_another_page_too():
    pages = {1: "Balance Sheet\nAs at 31 March 2025\nTotal assets 1,740.00", 2: "Balance Sheet\n2024\nTotal assets 1,600.00"}
    cur = attr(Name.PERIOD_END, "31 March 2025", "2025-03-31", "As at 31 March 2025", CUR, page=1)
    comp = attr(Name.PERIOD_END, "2024", "2024-03-31", "2024", COMP, page=2)

    result = verify([cur, comp], pages)

    assert result.period_end(COMP) == date(2024, 3, 31)


def test_the_normalised_date_must_equal_the_validated_one():
    for wrong in ("2025-03-30", "31 March 2025", "2025-3-31", ""):
        result = verify([replaced(CURRENT, normalised_value=wrong)] + [a for a in ALL if a is not CURRENT])
        assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH


def test_a_date_found_only_below_the_first_figure_line_is_not_a_header():
    page = "Balance Sheet\nTotal assets 1,740.00\nNote: dated 31 March 2025"
    cur = attr(Name.PERIOD_END, "31 March 2025", "2025-03-31", "Note: dated 31 March 2025", CUR)

    assert verify([cur], {112: page}).current_period_end.status_reason is Reason.PERIOD_MISMATCH


def test_the_later_validated_date_must_be_the_current_period():
    swapped_cur = replaced(COMPARATIVE, period_role=CUR)
    swapped_comp = replaced(CURRENT, period_role=COMP)

    result = verify([swapped_cur, swapped_comp])

    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.comparative_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.period_end(CUR) is None


def test_the_same_date_for_both_roles_is_not_two_periods():
    result = verify([CURRENT, replaced(CURRENT, period_role=COMP)])

    assert result.comparative_period_end.status_reason is Reason.PERIOD_MISMATCH
    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH  # no later date to call current


def test_the_consecutive_rule_treats_the_end_of_february_as_one_day():
    page = "Balance Sheet\nAs at 28 February 2025 29 February 2024\nTotal assets 1,740.00"
    quote = "As at 28 February 2025 29 February 2024"
    cur = attr(Name.PERIOD_END, "28 February 2025", "2025-02-28", quote, CUR)
    comp = attr(Name.PERIOD_END, "29 February 2024", "2024-02-29", quote, COMP)

    result = verify([cur, comp], {112: page})

    assert result.comparative_period_end.status is Status.EXTRACTED


# --- statement basis (H.4.6, B.6 row 9) -------------------------------------------------------------------------


def test_the_basis_is_verified_from_the_title_block():
    assert verify().statement_basis.status is Status.EXTRACTED


def test_a_standalone_title_does_not_support_a_consolidated_basis():
    page = PAGE.replace("Consolidated Balance Sheet", "Standalone Balance Sheet")
    claim = attr(Name.STATEMENT_BASIS, "Standalone", "consolidated", "Standalone Balance Sheet")

    assert verify([claim], {112: page}).statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_a_standalone_title_supports_a_standalone_basis():
    page = PAGE.replace("Consolidated Balance Sheet", "Standalone Balance Sheet")
    standalone = attr(Name.STATEMENT_BASIS, "Standalone", "standalone", "Standalone Balance Sheet")

    assert verify([standalone], {112: page}).statement_basis.status is Status.EXTRACTED


def test_a_basis_word_that_is_not_in_a_title_block_establishes_nothing():
    page = "Consolidated Industries Limited\nBalance Sheet\nAs at 31 March 2025\nTotal assets 1,740.00"
    proposed = attr(Name.STATEMENT_BASIS, "Consolidated", "consolidated", "Consolidated Industries Limited")

    assert verify([proposed], {112: page}).statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_a_basis_line_directly_above_the_title_is_part_of_the_block():
    page = "(Consolidated)\nBalance Sheet\nAs at 31 March 2025\nTotal assets 1,740.00"
    proposed = attr(Name.STATEMENT_BASIS, "Consolidated", "consolidated", "(Consolidated)")

    assert verify([proposed], {112: page}).statement_basis.status is Status.EXTRACTED


def test_both_bases_in_one_block_or_none_is_unknown():
    both = "Consolidated and Standalone Balance Sheet\nTotal assets 1,740.00"
    none = "Balance Sheet\nTotal assets 1,740.00"
    for page, raw in ((both, "Consolidated"), (none, "Balance Sheet")):
        proposed = attr(Name.STATEMENT_BASIS, raw, "consolidated", page.split("\n")[0])
        assert verify([proposed], {112: page}).statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_a_proposed_basis_of_unknown_is_requires_review():
    proposed = attr(Name.STATEMENT_BASIS, "Consolidated", "unknown", "Consolidated Balance Sheet")

    assert verify([proposed]).statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_unknown_is_not_a_basis_even_when_the_title_block_really_names_none():
    page = "Balance Sheet\nAs at 31 March 2025\nTotal assets 1,740.00"
    proposed = attr(Name.STATEMENT_BASIS, "Balance Sheet", "unknown", "Balance Sheet")

    result = verify([proposed], {112: page})

    assert result.statement_basis.status is Status.REQUIRES_REVIEW
    assert result.statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_the_raw_text_must_be_in_the_title_block_not_only_in_the_quote():
    quote = "Acme Industries Limited\nConsolidated Balance Sheet"
    proposed = attr(Name.STATEMENT_BASIS, "Acme", "consolidated", quote)

    assert verify([proposed]).statement_basis.status_reason is Reason.BASIS_UNKNOWN


def test_whitespace_around_proposed_values_is_ignored():
    padded = [
        replaced(BASIS, normalised_value=" consolidated "),
        replaced(CURRENCY, normalised_value=" INR "),
        replaced(SCALE, normalised_value=" crore "),
        replaced(CURRENT, normalised_value=" 2025-03-31 "),
    ]

    result = verify(padded)

    assert result.statement_basis.status is Status.EXTRACTED
    assert result.reporting_currency.status is Status.EXTRACTED
    assert result.scale.status is Status.EXTRACTED
    assert result.current_period_end.status is Status.EXTRACTED
    assert result.current_period_end.normalised_value == "2025-03-31"  # stored stripped
    assert result.current_period_end.raw_text == "31 March 2025"  # the evidence is as proposed
    assert result.period_end(CUR) == date(2025, 3, 31)


def test_the_raw_text_is_kept_exactly_as_proposed():
    padded = replaced(CURRENT, raw_text=" 31 March  2025 ")

    result = verify([padded] + [a for a in ALL if a is not CURRENT])

    assert result.current_period_end.status is Status.EXTRACTED
    assert result.current_period_end.raw_text == " 31 March  2025 "


def test_a_made_up_basis_value_is_not_accepted():
    proposed = attr(Name.STATEMENT_BASIS, "Consolidated", "group", "Consolidated Balance Sheet")

    assert verify([proposed]).statement_basis.status_reason is Reason.BASIS_UNKNOWN


# --- currency and scale (FR-005.8) ---------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["inr", "RS", "RUPEES", "IN", "", "INRR", "XYZ"])
def test_a_currency_the_quote_does_not_support_is_not_verified(value):
    proposed = replaced(CURRENCY, normalised_value=value)

    assert verify([proposed]).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_a_currency_symbol_for_another_code_is_not_verified():
    proposed = replaced(CURRENCY, normalised_value="USD")

    assert verify([proposed]).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


# The document-level currency is supported in the quote or on the cited page (PRD v0.4.30, FR-005.8; Appendix B.6 rows 68 to 71).

USD_PAGE = "Acme Inc\nConsolidated Balance Sheet\nAs at 31 March 2025 31 March 2024\n(In millions)\nCash and cash equivalents $ 1,482.30 $ 1,356.75"
UNIT_LINE = attr(Name.REPORTING_CURRENCY, "In millions", "USD", "(In millions)")  # a quote that states only the unit


def test_b6_row_68_a_currency_on_the_cited_page_supports_the_attribute_when_the_quote_has_no_sign():
    result = verify([UNIT_LINE], {112: USD_PAGE}).reporting_currency

    assert result.status is Status.EXTRACTED and result.normalised_value == "USD" and result.evidence_quote == "(In millions)"


def test_the_currency_may_also_be_stated_as_a_code_or_a_name_on_the_cited_page():
    for declaration in ("All amounts in USD", "All amounts in US dollars", "Amounts in dollars"):
        page = USD_PAGE.replace("Cash and cash equivalents $ 1,482.30 $ 1,356.75", f"{declaration}\nCash 1,482.30 1,356.75")

        assert verify([UNIT_LINE], {112: page}).reporting_currency.status is Status.EXTRACTED, declaration


def test_b6_row_69_a_page_with_no_sign_code_or_name_leaves_the_attribute_unverified():
    page = USD_PAGE.replace("$ ", "")

    assert verify([UNIT_LINE], {112: page}).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_b6_row_70_a_sign_for_another_code_on_the_page_does_not_support_the_code():
    proposed = replaced(UNIT_LINE, normalised_value="INR")

    assert verify([proposed], {112: USD_PAGE}).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_b6_row_71_a_quote_that_carries_the_sign_is_supported_as_before():
    assert verify([CURRENCY]).reporting_currency.status is Status.EXTRACTED


def test_only_the_cited_page_counts_not_another_candidate_page():
    pages = {112: USD_PAGE.replace("$ ", ""), 113: USD_PAGE}

    assert verify([UNIT_LINE], pages).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED
    assert verify([replaced(UNIT_LINE, page_number=113)], pages).reporting_currency.status is Status.EXTRACTED


def test_the_other_conditions_still_apply_when_the_page_supports_the_currency():
    lower = replaced(UNIT_LINE, normalised_value="usd")
    not_in_quote = replaced(UNIT_LINE, raw_text="$")  # the raw text is not in the quote
    off_page = replaced(UNIT_LINE, evidence_quote="(In billions)", raw_text="In billions")  # the quote is not on the page

    assert verify([lower], {112: USD_PAGE}).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED
    assert verify([not_in_quote], {112: USD_PAGE}).reporting_currency.status_reason is Reason.VALUE_NOT_IN_EVIDENCE
    assert verify([off_page], {112: USD_PAGE}).reporting_currency.status_reason is Reason.EVIDENCE_NOT_VERIFIED


def test_a_page_that_names_two_currencies_still_does_not_let_two_proposals_disagree():
    page = USD_PAGE + "\nAlso shown in ₹"
    usd = replaced(UNIT_LINE, normalised_value="USD")
    inr = replaced(UNIT_LINE, normalised_value="INR")

    assert verify([usd, inr], {112: page}).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_a_scale_other_than_the_declared_one_is_not_verified():
    for wrong in ("lakh", "millions", "units", "tens", ""):
        assert verify([replaced(SCALE, normalised_value=wrong)]).scale.status_reason is Reason.SCALE_NOT_VERIFIED


def test_two_scales_in_the_scale_quote_are_ambiguous():
    quote = "(₹ in crore) (₹ in lakh)"
    page = PAGE + "\n" + quote
    proposed = attr(Name.SCALE, "in crore", "crore", quote)

    assert verify([proposed], {112: page}).scale.status_reason is Reason.SCALE_AMBIGUOUS


# --- duplicates -------------------------------------------------------------------------------------------------------


def test_the_same_attribute_proposed_twice_with_the_same_value_is_one_attribute():
    again = replaced(CURRENCY, evidence_quote="(₹ in crore)")

    assert verify([CURRENCY, again]).reporting_currency.status is Status.EXTRACTED


def test_verified_proposals_that_disagree_are_not_guessed_between():
    pages = {112: PAGE + "\nAll amounts in INR and in USD"}
    inr = attr(Name.REPORTING_CURRENCY, "INR", "INR", "All amounts in INR and in USD")
    usd = attr(Name.REPORTING_CURRENCY, "USD", "USD", "All amounts in INR and in USD")

    assert verify([inr, usd], pages).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


def test_a_failed_duplicate_does_not_spoil_a_verified_one():
    bad = replaced(CURRENCY, normalised_value="USD")

    assert verify([bad, CURRENCY]).reporting_currency.status is Status.EXTRACTED
    assert verify([bad, CURRENCY]).reporting_currency.normalised_value == "INR"


def test_if_none_is_verified_the_first_failure_is_reported():
    first = replaced(CURRENCY, evidence_quote="not on the page", raw_text="not on")
    second = replaced(CURRENCY, normalised_value="USD")

    assert verify([first, second]).reporting_currency.status_reason is Reason.EVIDENCE_NOT_VERIFIED


# --- the dependency rule (H.1.2) --------------------------------------------------------------------------------------------


def test_with_every_attribute_extracted_no_field_is_blocked():
    result = verify()

    assert blocking_reason(result, CUR) is None and blocking_reason(result, COMP) is None


def test_a_field_is_blocked_by_its_own_periods_attribute_only():
    result = verify([replaced(COMPARATIVE, normalised_value="2024-03-30")] + [a for a in ALL if a is not COMPARATIVE])

    assert blocking_reason(result, CUR) is None
    assert blocking_reason(result, COMP) is Reason.PERIOD_MISMATCH


def test_a_missing_period_blocks_with_period_mismatch():
    assert blocking_reason(verify(without(CURRENT)), CUR) is Reason.PERIOD_MISMATCH


@pytest.mark.parametrize(
    ("missing", "reason"),
    [(BASIS, Reason.BASIS_UNKNOWN), (CURRENCY, Reason.CURRENCY_NOT_VERIFIED), (SCALE, Reason.SCALE_NOT_VERIFIED)],
)
def test_a_missing_or_failed_attribute_blocks_every_field_with_its_reason(missing, reason):
    result = verify(without(missing))

    assert blocking_reason(result, CUR) is reason and blocking_reason(result, COMP) is reason


def test_an_ambiguous_scale_blocks_as_ambiguous():
    quote = "(₹ in crore) (₹ in lakh)"
    result = verify([attr(Name.SCALE, "in crore", "crore", quote)] + without(SCALE), {112: PAGE + "\n" + quote})

    assert blocking_reason(result, CUR) is Reason.SCALE_AMBIGUOUS


def test_the_entity_name_blocks_nothing():
    assert blocking_reason(verify(without(ENTITY)), CUR) is None


def test_blocking_reasons_follow_the_prd_order_period_then_basis_then_currency_then_scale():
    result = verify([])
    assert blocking_reason(result, CUR) is Reason.PERIOD_MISMATCH
    result = verify([CURRENT, COMPARATIVE])
    assert blocking_reason(result, CUR) is Reason.BASIS_UNKNOWN
    result = verify([CURRENT, COMPARATIVE, BASIS])
    assert blocking_reason(result, CUR) is Reason.CURRENCY_NOT_VERIFIED
    result = verify([CURRENT, COMPARATIVE, BASIS, CURRENCY])
    assert blocking_reason(result, CUR) is Reason.SCALE_NOT_VERIFIED


# --- determinism ---------------------------------------------------------------------------------------------------------------


def test_the_order_of_the_proposals_does_not_matter():
    expected = verify()
    rng = random.Random(4)
    for _ in range(20):
        shuffled = ALL[:]
        rng.shuffle(shuffled)
        assert verify(shuffled) == expected


def test_verification_is_repeatable():
    assert verify() == verify()


# --- a role on an attribute that has none (seen on the first live run) ---------------------------------------------


@pytest.mark.parametrize("original", [ENTITY, BASIS, CURRENCY, SCALE])
@pytest.mark.parametrize("role", [CUR, COMP])
def test_an_attribute_that_is_not_a_period_end_is_used_even_if_the_model_gives_it_a_role(original, role):
    with_role = replaced(original, period_role=role)

    result = verify([with_role if a is original else a for a in ALL])

    record = {Name.ENTITY_NAME: result.entity_name, Name.STATEMENT_BASIS: result.statement_basis,
              Name.REPORTING_CURRENCY: result.reporting_currency, Name.SCALE: result.scale}[original.attribute]  # fmt: skip
    assert record.status is Status.EXTRACTED and record.period_role is None
    assert record.raw_text == original.raw_text
    assert blocking_reason(result, CUR) is None and blocking_reason(result, COMP) is None


def test_a_role_that_is_given_to_a_verified_attribute_does_not_change_its_verification():
    bad = replaced(CURRENCY, period_role=CUR, normalised_value="USD")

    result = verify([bad if a is CURRENCY else a for a in ALL])

    assert result.reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED
    assert result.reporting_currency.period_role is None


def test_a_period_end_with_no_role_is_still_not_used():
    # Which period it is cannot be guessed from nothing, so it stays not_found (a known limit).
    no_role = replaced(CURRENT, period_role=None)

    result = verify([no_role if a is CURRENT else a for a in ALL])

    assert result.current_period_end.status is Status.NOT_FOUND


def test_duplicate_non_period_proposals_with_different_roles_are_still_one_attribute():
    again = replaced(CURRENCY, period_role=COMP)

    result = verify([CURRENCY, again] + [a for a in ALL if a is not CURRENCY])

    assert result.reporting_currency.status is Status.EXTRACTED and result.reporting_currency.period_role is None


# --- v0.4.20: a wrapped date, and a date below the figures ---------------------------------------------

WRAPPED_PAGE = (
    "Acme Industries Limited\n"
    "Consolidated Balance Sheet\n"
    "As at March 31,\n"
    "2025\n"
    "(₹ in crore)\n"
    "Total current assets 14 1,482.30 1,356.75\n"
    "Signed on behalf of the Board on April 17, 2025"
)


def test_a_period_end_wrapped_over_two_header_lines_is_accepted():
    current = attr(Name.PERIOD_END, "March 31, 2025", "2025-03-31", "As at March 31,\n2025", CUR, page=7)

    result = verify_attributes([current], {7: WRAPPED_PAGE})

    assert result.current_period_end.status is Status.EXTRACTED
    assert result.period_end(CUR) == date(2025, 3, 31)


def test_the_signing_date_below_the_figures_is_not_a_period_end():
    current = attr(Name.PERIOD_END, "April 17, 2025", "2025-04-17", "Signed on behalf of the Board on April 17, 2025", CUR, page=7)

    result = verify_attributes([current], {7: WRAPPED_PAGE})

    assert result.current_period_end.status is Status.REQUIRES_REVIEW
    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH


def test_a_year_header_is_not_validated_by_the_signing_date():
    page = "Acme Limited\nBalance Sheet\n2025 2024\nTotal current assets 14 1,482.30 1,356.75\nSigned on April 17, 2025"
    current = attr(Name.PERIOD_END, "2025", "2025-04-17", "2025 2024", CUR, page=7)

    result = verify_attributes([current], {7: page})

    assert result.current_period_end.status is Status.REQUIRES_REVIEW
    assert result.current_period_end.status_reason is Reason.PERIOD_MISMATCH


# --- v0.4.22: the code derives the comparative period end -------------------------------------------------------------------

DERIVE_PAGE = (
    "Acme Industries Limited\n"
    "Consolidated Balance Sheet\n"
    "As at March 31, 2025\n"
    "Particulars Note 2025 2024\n"
    "(₹ in crore)\n"
    "Total current assets 14 1,482.30 1,356.75"
)
CUR_YEAR_HEADED = attr(Name.PERIOD_END, "March 31, 2025", "2025-03-31", "As at March 31, 2025", CUR, page=7)


def comparative_of(proposed, pages=None):
    return verify_attributes(proposed, pages or {7: DERIVE_PAGE}).comparative_period_end


def test_b6_row_34_a_missing_comparative_is_derived_from_the_year_heading():
    result = verify_attributes([CUR_YEAR_HEADED], {7: DERIVE_PAGE})

    comparative = result.comparative_period_end
    assert comparative.status is Status.EXTRACTED and comparative.normalised_value == "2024-03-31"
    assert comparative.raw_text == "2024" and comparative.page_number == 7
    assert comparative.evidence_quote == "Particulars Note 2025 2024"
    evidence = result.period_evidence[COMP]
    assert evidence.method is Method.DERIVED_COMPARATIVE and evidence.derived_from == date(2025, 3, 31)
    assert result.period_end(COMP) == date(2024, 3, 31)


def test_the_derived_comparative_quote_is_on_the_page():
    from credit_intel.extraction.presence import check_presence

    comparative = comparative_of([CUR_YEAR_HEADED])

    assert check_presence({7: DERIVE_PAGE}, 7, comparative.evidence_quote, comparative.raw_text).evidence_verified


def test_b6_row_35_a_current_period_ending_in_february_derives_nothing():
    page = DERIVE_PAGE.replace("March 31, 2025", "February 28, 2025")
    current = attr(Name.PERIOD_END, "February 28, 2025", "2025-02-28", "As at February 28, 2025", CUR, page=7)

    comparative = comparative_of([current], {7: page})

    assert comparative.status is Status.NOT_FOUND


def test_b6_row_36_no_heading_of_the_previous_year_derives_nothing():
    page = DERIVE_PAGE.replace("2025 2024", "2025 2022")

    assert comparative_of([CUR_YEAR_HEADED], {7: page}).status is Status.NOT_FOUND


def test_b6_row_37_a_proposed_comparative_that_equals_the_derived_date_is_kept():
    proposed = attr(Name.PERIOD_END, "2024", "2024-03-31", "Particulars Note 2025 2024", COMP, page=7)

    comparative = comparative_of([CUR_YEAR_HEADED, proposed])

    assert comparative.status is Status.EXTRACTED and comparative.normalised_value == "2024-03-31"


def test_b6_row_38_a_proposed_comparative_that_differs_from_the_derived_date_is_for_review():
    page = DERIVE_PAGE.replace("Particulars Note 2025 2024", "Particulars Note 2025 2024 30 March 2024")
    proposed = attr(Name.PERIOD_END, "30 March 2024", "2024-03-30", "Particulars Note 2025 2024 30 March 2024", COMP, page=7)

    comparative = comparative_of([CUR_YEAR_HEADED, proposed], {7: page})

    assert comparative.status is Status.REQUIRES_REVIEW
    assert comparative.status_reason is Reason.PERIOD_MISMATCH


def test_b6_row_39_an_unvalidated_current_period_derives_nothing():
    wrong = replaced(CUR_YEAR_HEADED, normalised_value="2025-04-17")

    result = verify_attributes([wrong], {7: DERIVE_PAGE})

    assert result.current_period_end.status is Status.REQUIRES_REVIEW
    assert result.comparative_period_end.status is Status.NOT_FOUND


def test_a_failed_proposed_comparative_is_replaced_by_the_derived_one_without_an_error():
    broken = attr(Name.PERIOD_END, "2024", "2024-03-31", "A quote that is not on the page", COMP, page=7)

    comparative = comparative_of([CUR_YEAR_HEADED, broken])

    assert comparative.status is Status.EXTRACTED and comparative.evidence_quote == "Particulars Note 2025 2024"


def test_a_signing_date_of_the_previous_year_does_not_become_a_comparative():
    page = DERIVE_PAGE.replace("(₹ in crore)", "Approved on 17 April 2024\n(₹ in crore)")
    page = page.replace("Particulars Note 2025 2024", "Particulars Note 2025")

    assert comparative_of([CUR_YEAR_HEADED], {7: page}).status is Status.NOT_FOUND


def test_property_a_derived_comparative_is_the_same_month_and_day_one_year_earlier():
    rng = random.Random(22)
    for _ in range(200):
        year, month, day = rng.randint(1991, 2090), rng.choice([1, 3, 4, 6, 9, 12]), rng.randint(1, 28)
        page = f"Acme\nBalance Sheet\nAs at {day} {['', 'January', '', 'March', 'April', '', 'June', '', '', 'September', '', '', 'December'][month]} {year}\nParticulars {year} {year - 1}\nTotal assets 1,740.00 1,600.00"
        current = attr(Name.PERIOD_END, page.splitlines()[2][len("As at "):], date(year, month, day).isoformat(), page.splitlines()[2], CUR, page=7)

        comparative = verify_attributes([current], {7: page}).comparative_period_end

        assert comparative.status is Status.EXTRACTED
        assert comparative.normalised_value == date(year - 1, month, day).isoformat()
