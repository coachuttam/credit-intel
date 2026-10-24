"""MET-03 current ratio, MET-04 debt-to-equity, MET-05 interest coverage (PRD I.1, I.2, FR-007; Phase 3 step 3d; B-241)."""

import random
from datetime import date
from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.calculations.derived import derive_ebit
from credit_intel.calculations.metrics import MetricReason as M, Unit, current_ratio, debt_to_equity, interest_coverage
from credit_intel.models import FieldName as F, Origin, PeriodRole, StatementBasis as Basis, Status

COMP = PeriodRole.COMPARATIVE


def cr(assets, liabilities, **kw):
    return current_ratio(rec(F.CURRENT_ASSETS, assets, **kw), rec(F.CURRENT_LIABILITIES, liabilities, **kw))


def de(borrowings, equity, **kw):
    return debt_to_equity(rec(F.TOTAL_BORROWINGS, borrowings, **kw), rec(F.TOTAL_EQUITY, equity, **kw))


def ic(ebit, interest, **kw):
    return interest_coverage(rec(F.EBIT, ebit, **kw), rec(F.INTEREST_EXPENSE, interest, **kw))


# --- MET-03: the PRD's acceptance tests ----------------------------------------------------------------------------------


def test_met03_150_over_100_is_one_point_five():
    result = cr("150", "100")

    assert result.value == Decimal("1.5") and result.unit is Unit.RATIO and result.metric_id == "MET-03"


def test_met03_80_over_100_is_zero_point_eight():
    assert cr("80", "100").value == Decimal("0.8")


def test_met03_zero_current_liabilities_is_undefined_with_zero_denominator():
    result = cr("100", "0")

    assert result.value is None and result.undefined_reason is M.ZERO_DENOMINATOR


def test_met03_a_negative_input_is_input_requires_review():
    assert cr("-100", "100").undefined_reason is M.INPUT_REQUIRES_REVIEW
    assert cr("100", "-100").undefined_reason is M.INPUT_REQUIRES_REVIEW


def test_met03_zero_assets_is_a_valid_zero_ratio():
    assert cr("0", "100").value == Decimal("0")


def test_met03_the_two_balance_sheet_dates_must_match():
    result = current_ratio(rec(F.CURRENT_ASSETS, "150"), rec(F.CURRENT_LIABILITIES, "100", end=date(2025, 4, 1)))

    assert result.undefined_reason is M.PERIOD_MISMATCH


# --- MET-04 ---------------------------------------------------------------------------------------------------------------------


def test_met04_200_over_100_is_two():
    result = de("200", "100")

    assert result.value == Decimal("2") and result.unit is Unit.RATIO and result.metric_id == "MET-04"


def test_met04_zero_borrowings_is_a_valid_zero():
    assert de("0", "100").value == Decimal("0")


def test_met04_negative_equity_is_not_meaningful():
    result = de("50", "-10")

    assert result.value is None and result.undefined_reason is M.NOT_MEANINGFUL_NEGATIVE_EQUITY


def test_met04_zero_equity_is_a_zero_denominator():
    assert de("50", "0").undefined_reason is M.ZERO_DENOMINATOR


def test_met04_missing_borrowings_are_undefined_and_nothing_is_substituted():
    for borrowings in (None, rec(F.TOTAL_BORROWINGS, status=Status.NOT_FOUND)):
        result = debt_to_equity(borrowings, rec(F.TOTAL_EQUITY, "100"))
        assert result.value is None and result.undefined_reason is M.MISSING_INPUT


def test_met04_negative_borrowings_are_input_requires_review():
    assert de("-5", "100").undefined_reason is M.INPUT_REQUIRES_REVIEW


def test_met04_borrowings_and_equity_in_two_currencies_are_undefined():
    assert debt_to_equity(rec(F.TOTAL_BORROWINGS, "5", currency="USD"), rec(F.TOTAL_EQUITY, "100")).undefined_reason is M.CURRENCY_MISMATCH


def test_met04_a_derived_total_of_borrowings_is_an_input_like_any_other():
    from credit_intel.models import Derivation, ExtractedField, make_field_id

    derived = ExtractedField(
        field_id=make_field_id(F.TOTAL_BORROWINGS, D25, Basis.CONSOLIDATED), field_name=F.TOTAL_BORROWINGS, origin=Origin.DERIVED,
        period_end=D25, period_length_months=12, period_role=CUR, statement_basis=Basis.CONSOLIDATED, status=Status.EXTRACTED,
        value=Decimal("300"), currency="INR", derivation=Derivation(method_id="BORR-SUM", formula="f", input_field_ids=("a", "b")),
    )  # fmt: skip

    result = debt_to_equity(derived, rec(F.TOTAL_EQUITY, "100"))

    assert result.value == Decimal("3") and result.input_field_ids[0] == "total_borrowings.2025-03-31.consolidated"


# --- MET-05 ---------------------------------------------------------------------------------------------------------------------


def test_met05_300_over_100_is_three():
    result = ic("300", "100")

    assert result.value == Decimal("3") and result.unit is Unit.RATIO and result.metric_id == "MET-05"


def test_met05_negative_ebit_gives_a_valid_negative_ratio():
    assert ic("-50", "100").value == Decimal("-0.5")


def test_met05_zero_interest_is_not_applicable():
    result = ic("300", "0")

    assert result.value is None and result.undefined_reason is M.NOT_APPLICABLE_NO_INTEREST


def test_met05_negative_interest_is_input_requires_review():
    assert ic("300", "-100").undefined_reason is M.INPUT_REQUIRES_REVIEW


def test_met05_takes_the_derived_ebit_and_names_it_in_its_inputs():
    ebit = derive_ebit(rec(F.OPERATING_PROFIT, status=Status.NOT_FOUND), rec(F.PROFIT_BEFORE_TAX, "280"), rec(F.INTEREST_EXPENSE, "20"))

    result = interest_coverage(ebit, rec(F.INTEREST_EXPENSE, "20"))

    assert result.value == Decimal("15") and result.input_field_ids == ("ebit.2025-03-31.consolidated", "interest_expense.2025-03-31.consolidated")


def test_met05_a_reported_but_unverified_operating_profit_leaves_the_coverage_undefined():
    # H.5 rule 3: EBIT-OP is used whenever operating profit is reported, so there is no fallback to profit before tax.
    ebit = derive_ebit(rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW), rec(F.PROFIT_BEFORE_TAX, "280"), rec(F.INTEREST_EXPENSE, "20"))

    result = interest_coverage(ebit, rec(F.INTEREST_EXPENSE, "20"))

    assert result.value is None and result.undefined_reason is M.INPUT_REQUIRES_REVIEW


def test_met05_a_conflicting_ebit_is_input_conflicting():
    ebit = derive_ebit(conflicting(F.OPERATING_PROFIT, ["10", "20"]), None, None)

    assert interest_coverage(ebit, rec(F.INTEREST_EXPENSE, "5")).undefined_reason is M.INPUT_CONFLICTING


def test_met05_missing_ebit_is_missing_input_and_the_result_names_what_was_missing():
    result = interest_coverage(None, rec(F.INTEREST_EXPENSE, "5"))

    assert result.undefined_reason is M.MISSING_INPUT
    assert result.input_field_ids == ("ebit.2025-03-31", "interest_expense.2025-03-31.consolidated")
    assert result.input_values == (None, Decimal("5"))


# --- all three: the comparative period, statuses and callers' errors ---------------------------------------------------------


def test_each_ratio_works_for_the_comparative_period_with_its_own_date():
    result = cr("90", "60", role=COMP, end=D24)

    assert result.value == Decimal("1.5") and result.period_ends == (D24,)
    assert result.input_field_ids == ("current_assets.2024-03-31.consolidated", "current_liabilities.2024-03-31.consolidated")


@pytest.mark.parametrize("function", [current_ratio, debt_to_equity, interest_coverage])
def test_a_ratio_with_no_inputs_at_all_is_missing_input(function):
    result = function(None, None)

    assert result.undefined_reason is M.MISSING_INPUT and result.input_values == (None, None) and result.period_ends == ()


def test_an_unusable_input_status_gives_the_matching_reason_for_every_ratio():
    assert current_ratio(rec(F.CURRENT_ASSETS, status=Status.REQUIRES_REVIEW), rec(F.CURRENT_LIABILITIES, "1")).undefined_reason is M.INPUT_REQUIRES_REVIEW
    assert debt_to_equity(conflicting(F.TOTAL_BORROWINGS, ["1", "2"]), rec(F.TOTAL_EQUITY, "1")).undefined_reason is M.INPUT_CONFLICTING


def test_inputs_of_two_bases_or_two_period_roles_are_a_caller_error():
    with pytest.raises(ValueError):
        current_ratio(rec(F.CURRENT_ASSETS, "5"), rec(F.CURRENT_LIABILITIES, "1", basis=Basis.STANDALONE))
    with pytest.raises(ValueError):
        debt_to_equity(rec(F.TOTAL_BORROWINGS, "5"), rec(F.TOTAL_EQUITY, "1", role=COMP, end=D24))


def test_the_ratio_is_exact_decimal_not_rounded():
    assert cr("1", "3").value == Decimal("0.3333333333333333333333333333")  # 28 significant digits


def test_property_scaling_both_inputs_leaves_every_ratio_unchanged_and_the_result_is_a_decimal():
    rng = random.Random(50)
    for _ in range(300):
        a, b = Decimal(rng.randint(1, 10**6)) / 100, Decimal(rng.randint(1, 10**6)) / 100
        k = Decimal(rng.randint(2, 1000))
        for func, left, right in ((cr, F.CURRENT_ASSETS, F.CURRENT_LIABILITIES), (de, F.TOTAL_BORROWINGS, F.TOTAL_EQUITY), (ic, F.EBIT, F.INTEREST_EXPENSE)):
            assert func(str(a), str(b)).value == func(str(a * k), str(b * k)).value
            assert isinstance(func(str(a), str(b)).value, Decimal)
