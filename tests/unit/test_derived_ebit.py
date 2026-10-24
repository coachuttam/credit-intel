"""Derived values: EBIT (PRD H.5 rules 1 to 3 and 7; Phase 3 step 3a; B-239). Synthetic records."""

import random
from datetime import date
from decimal import Decimal

import pytest

from credit_intel.calculations.derived import EBIT_OP, EBIT_PBT, derive_ebit, derive_ebit_for
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import (
    Candidate,
    ExtractedField,
    FieldName as F,
    Origin,
    PeriodRole,
    Scale,
    SourceDocument,
    StatementBasis as Basis,
    Status,
    StatusReason as R,
    make_field_id,
)

from calc_records import CUR, D24, D25, DOC, cand, conflicting, rec


OP, PBT, INT = F.OPERATING_PROFIT, F.PROFIT_BEFORE_TAX, F.INTEREST_EXPENSE


# --- the all-extracted case, both methods --------------------------------------------------------------------


def test_ebit_op_is_the_operating_profit_and_records_its_derivation():
    result = derive_ebit(rec(OP, "250"), rec(PBT, "300"), rec(INT, "50"))

    assert result.status is Status.EXTRACTED and result.value == Decimal("250") and result.currency == "INR"
    assert result.origin is Origin.DERIVED and result.field_name is F.EBIT
    assert result.field_id == "ebit.2025-03-31.consolidated"
    assert result.derivation.method_id == EBIT_OP and result.derivation.formula == "ebit = operating_profit"
    assert result.derivation.input_field_ids == ("operating_profit.2025-03-31.consolidated",)


def test_ebit_pbt_adds_interest_to_profit_before_tax_when_operating_profit_is_not_found():
    result = derive_ebit(rec(OP, status=Status.NOT_FOUND), rec(PBT, "300"), rec(INT, "50"))

    assert result.status is Status.EXTRACTED and result.value == Decimal("350")
    assert result.derivation.method_id == EBIT_PBT and result.derivation.formula == "ebit = profit_before_tax + interest_expense"
    assert result.derivation.input_field_ids == ("profit_before_tax.2025-03-31.consolidated", "interest_expense.2025-03-31.consolidated")


def test_a_derived_value_has_no_evidence_of_its_own():
    result = derive_ebit(rec(OP, status=Status.NOT_FOUND), rec(PBT, "300"), rec(INT, "50"))

    for name in ("raw_value", "scale", "source_document", "page_number", "evidence_quote", "line_item_label", "validation"):
        assert getattr(result, name) is None


def test_the_sum_is_exact_decimal_arithmetic():
    result = derive_ebit(None, rec(PBT, "0.1"), rec(INT, "0.2"))

    assert result.value == Decimal("0.3") and isinstance(result.value, Decimal)


def test_a_loss_gives_a_negative_ebit():
    assert derive_ebit(None, rec(PBT, "-400"), rec(INT, "50")).value == Decimal("-350")


# --- method choice is fixed (rule 3) --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [Status.REQUIRES_REVIEW, Status.CONFLICTING])
def test_ebit_op_is_used_whenever_operating_profit_is_reported_even_if_it_is_not_extracted(status):
    operating = rec(OP, status=Status.REQUIRES_REVIEW) if status is Status.REQUIRES_REVIEW else conflicting(OP, ["10", "20"])

    result = derive_ebit(operating, rec(PBT, "300"), rec(INT, "50"))

    assert result.derivation.method_id == EBIT_OP and result.status is status  # no fallback to profit before tax
    assert result.value is None


def test_a_requires_review_operating_profit_passes_its_reason_on():
    result = derive_ebit(rec(OP, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED), rec(PBT), rec(INT))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.LABEL_NOT_RECOGNISED


def test_a_conflicting_operating_profit_gives_a_conflicting_ebit_with_the_same_candidates():
    result = derive_ebit(conflicting(OP, ["10", "20"]), None, None)

    assert result.status is Status.CONFLICTING and sorted(c.value for c in result.candidates) == [Decimal("10"), Decimal("20")]


# --- each non-extracted input (rule 2) ------------------------------------------------------------------------


def test_a_missing_input_gives_not_found_with_missing_input():
    for pbt, interest in ((None, rec(INT)), (rec(PBT), None), (rec(PBT, status=Status.NOT_FOUND), rec(INT))):
        result = derive_ebit(rec(OP, status=Status.NOT_FOUND), pbt, interest)

        assert result.status is Status.NOT_FOUND and result.status_reason is R.MISSING_INPUT and result.value is None


def test_not_found_outranks_conflicting_and_requires_review():
    result = derive_ebit(None, conflicting(PBT, ["1", "2"]), rec(INT, status=Status.NOT_FOUND))
    assert result.status is Status.NOT_FOUND

    result = derive_ebit(None, rec(PBT, status=Status.REQUIRES_REVIEW), rec(INT, status=Status.NOT_FOUND))
    assert result.status is Status.NOT_FOUND


def test_a_requires_review_input_gives_requires_review_with_its_reason():
    result = derive_ebit(None, rec(PBT, status=Status.REQUIRES_REVIEW, reason=R.PERIOD_NOT_VERIFIED), rec(INT, "5"))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.PERIOD_NOT_VERIFIED and result.value is None


def test_a_conflicting_input_gives_the_combined_candidate_results_with_both_inputs_evidence():
    result = derive_ebit(None, conflicting(PBT, ["300", "310"]), rec(INT, "50"))

    assert result.status is Status.CONFLICTING and result.status_reason is None
    assert sorted(c.value for c in result.candidates) == [Decimal("350"), Decimal("360")]
    first = next(c for c in result.candidates if c.value == Decimal("350"))
    assert "profit_before_tax 300" in first.evidence_quote and "interest_expense 50" in first.evidence_quote
    assert first.line_item_label == "profit_before_tax + interest_expense" and first.raw_value == "300 + 50"


def test_two_conflicting_inputs_give_every_combination():
    result = derive_ebit(None, conflicting(PBT, ["300", "310"]), conflicting(INT, ["50", "60"]))

    assert sorted(c.value for c in result.candidates) == [Decimal("350"), Decimal("360"), Decimal("360"), Decimal("370")]


def test_a_conflicting_input_beside_a_requires_review_input_cannot_list_candidates_so_it_needs_review():
    result = derive_ebit(None, conflicting(PBT, ["300", "310"]), rec(INT, status=Status.REQUIRES_REVIEW, reason=R.SCALE_AMBIGUOUS))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.SCALE_AMBIGUOUS


# --- currency and period (rule 1) ------------------------------------------------------------------------------


def test_inputs_in_two_currencies_need_review_with_currency_mismatch():
    result = derive_ebit(None, rec(PBT, "300", currency="INR"), rec(INT, "50", currency="USD"))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.CURRENCY_MISMATCH and result.value is None


def test_inputs_with_different_period_ends_need_review_with_period_mismatch():
    result = derive_ebit(None, rec(PBT, "300"), rec(INT, "50", end=date(2025, 4, 1)))

    assert result.status is Status.REQUIRES_REVIEW and result.status_reason is R.PERIOD_MISMATCH


def test_inputs_of_different_bases_or_roles_are_a_caller_error():
    with pytest.raises(ValueError):
        derive_ebit(None, rec(PBT), rec(INT, basis=Basis.STANDALONE))
    with pytest.raises(ValueError):
        derive_ebit(None, rec(PBT), rec(INT, role=PeriodRole.COMPARATIVE, end=D24))


def test_without_any_record_there_is_nothing_to_derive():
    assert derive_ebit(None, None, None) is None


def test_a_not_found_operating_profit_alone_still_gives_a_not_found_ebit_for_its_period():
    result = derive_ebit(rec(OP, status=Status.NOT_FOUND), None, None)

    assert result.status is Status.NOT_FOUND and result.status_reason is R.MISSING_INPUT and result.period_end == D25


# --- the comparative period, and a run's field set -------------------------------------------------------------


def test_the_comparative_period_has_its_own_ebit():
    result = derive_ebit(None, rec(PBT, "280", end=D24, role=PeriodRole.COMPARATIVE), rec(INT, "40", end=D24, role=PeriodRole.COMPARATIVE))

    assert result.period_role is PeriodRole.COMPARATIVE and result.field_id == "ebit.2024-03-31.consolidated" and result.value == Decimal("320")


def test_ebit_for_a_field_set_uses_the_configured_basis_records():
    records = (rec(OP, status=Status.NOT_FOUND), rec(PBT, "300"), rec(INT, "50"))
    field_set = FieldSet(Basis.CONSOLIDATED, records, (), (), ("consolidated",))

    assert derive_ebit_for(field_set, CUR).value == Decimal("350")
    assert derive_ebit_for(field_set, PeriodRole.COMPARATIVE) is None  # no records for that period


# --- properties ------------------------------------------------------------------------------------------------


def test_property_the_sum_is_exact_and_the_method_follows_operating_profit():
    rng = random.Random(3)
    for _ in range(300):
        pbt, interest, op = (Decimal(rng.randint(-10**6, 10**6)) / 100 for _ in range(3))
        status = rng.choice([Status.EXTRACTED, Status.NOT_FOUND])
        operating = rec(OP, str(op)) if status is Status.EXTRACTED else rec(OP, status=Status.NOT_FOUND)
        interest_rec = rec(INT, str(abs(interest)))

        result = derive_ebit(operating, rec(PBT, str(pbt)), interest_rec)

        assert result.status is Status.EXTRACTED
        if status is Status.EXTRACTED:
            assert result.derivation.method_id == EBIT_OP and result.value == op
        else:
            assert result.derivation.method_id == EBIT_PBT and result.value == pbt + abs(interest)
