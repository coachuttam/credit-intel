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


def test_the_currency_must_be_supported_by_the_quote_itself():
    page = PAGE + "\nAll amounts in USD"
    proposed = replaced(CURRENCY, normalised_value="USD")  # USD is on the page, not in the quote

    assert verify([proposed], {112: page}).reporting_currency.status_reason is Reason.CURRENCY_NOT_VERIFIED


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
