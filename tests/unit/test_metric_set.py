"""All five metrics for both periods from a field set, and the period comparison (PRD I.1, I.3; Phase 3 step 3e; B-242)."""

import random
from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.calculations.calculate import Comparison, MetricSet, calculate_metrics, compare
from credit_intel.calculations.derived import EBIT_OP, EBIT_PBT
from credit_intel.calculations.metrics import MetricReason as M, MetricResult, Unit
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status

COMP = PeriodRole.COMPARATIVE
CURRENT_VALUES = {F.REVENUE: "1100", F.NET_PROFIT: "110", F.PROFIT_BEFORE_TAX: "160", F.INTEREST_EXPENSE: "40",
                  F.CURRENT_ASSETS: "300", F.CURRENT_LIABILITIES: "200", F.TOTAL_BORROWINGS: "400", F.TOTAL_EQUITY: "500"}  # fmt: skip
COMPARATIVE_VALUES = {F.REVENUE: "1000", F.NET_PROFIT: "80", F.PROFIT_BEFORE_TAX: "120", F.INTEREST_EXPENSE: "40",
                      F.CURRENT_ASSETS: "240", F.CURRENT_LIABILITIES: "200", F.TOTAL_BORROWINGS: "300", F.TOTAL_EQUITY: "500"}  # fmt: skip


def records(values, role):
    end = D25 if role is CUR else D24
    return [rec(name, value, role=role, end=end) for name, value in values.items()]


def field_set(current=CURRENT_VALUES, comparative=COMPARATIVE_VALUES, extra=(), ignored=()):
    fields = (*records(current, CUR), *records(comparative, COMP), *extra)
    return FieldSet(Basis.CONSOLIDATED, tuple(fields), tuple(ignored), (), ("consolidated",))


# --- a complete run ----------------------------------------------------------------------------------------------------------


def test_every_metric_is_computed_for_both_periods():
    metrics = calculate_metrics(field_set())

    assert isinstance(metrics, MetricSet) and metrics.configured_basis is Basis.CONSOLIDATED
    assert metrics.get("MET-01").value == Decimal("10")
    assert metrics.get("MET-02", CUR).value == Decimal("10") and metrics.get("MET-02", COMP).value == Decimal("8")
    assert metrics.get("MET-03", CUR).value == Decimal("1.5") and metrics.get("MET-03", COMP).value == Decimal("1.2")
    assert metrics.get("MET-04", CUR).value == Decimal("0.8") and metrics.get("MET-04", COMP).value == Decimal("0.6")
    assert metrics.get("MET-05", CUR).value == Decimal("5") and metrics.get("MET-05", COMP).value == Decimal("4")


def test_ebit_is_derived_for_each_period_from_profit_before_tax_and_interest():
    metrics = calculate_metrics(field_set())

    current, comparative = metrics.derived
    assert (current.period_role, comparative.period_role) == (CUR, COMP)
    assert current.value == Decimal("200") and comparative.value == Decimal("160")
    assert current.derivation.method_id == EBIT_PBT


def test_a_reported_operating_profit_is_used_for_ebit():
    extra = [rec(F.OPERATING_PROFIT, "210", role=CUR, end=D25), rec(F.OPERATING_PROFIT, "150", role=COMP, end=D24)]

    metrics = calculate_metrics(field_set(extra=extra))

    assert metrics.derived[0].derivation.method_id == EBIT_OP and metrics.get("MET-05", CUR).value == Decimal("5.25")


def test_every_result_is_labelled_with_its_metric_unit_and_inputs():
    metrics = calculate_metrics(field_set())

    assert metrics.get("MET-01").unit is Unit.PERCENT and metrics.get("MET-03", CUR).unit is Unit.RATIO
    assert metrics.get("MET-05", CUR).input_field_ids == ("ebit.2025-03-31.consolidated", "interest_expense.2025-03-31.consolidated")
    assert metrics.get("MET-01").period_ends == (D25, D24)


# --- what is not used ----------------------------------------------------------------------------------------------------------


def test_fields_of_another_basis_set_aside_by_the_run_are_never_used():
    other = rec(F.REVENUE, "999999", role=CUR, end=D25, basis=Basis.STANDALONE)

    metrics = calculate_metrics(field_set(ignored=[other]))

    assert metrics.get("MET-01").value == Decimal("10")


def test_the_field_set_is_not_changed_and_a_second_call_gives_the_same_answer():
    fs = field_set()
    before = fs.fields

    first, second = calculate_metrics(fs), calculate_metrics(fs)

    assert fs.fields is before and first.results == second.results and first.comparisons == second.comparisons


def test_the_result_mappings_cannot_be_changed():
    metrics = calculate_metrics(field_set())

    with pytest.raises(TypeError):
        metrics.results[("MET-01", None)] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        metrics.comparisons["MET-02"] = None  # type: ignore[index]


# --- gaps ----------------------------------------------------------------------------------------------------------------------


def test_a_run_with_no_comparative_period_has_current_metrics_and_undefined_growth_and_comparisons():
    metrics = calculate_metrics(field_set(comparative={}))

    assert metrics.get("MET-02", CUR).value == Decimal("10")
    assert metrics.get("MET-01").undefined_reason is M.MISSING_INPUT
    assert metrics.get("MET-02", COMP).undefined_reason is M.MISSING_INPUT
    for metric in ("MET-02", "MET-03", "MET-04", "MET-05"):
        comparison = metrics.comparison(metric)
        assert comparison.relative_change is None and comparison.undefined_reason is M.MISSING_INPUT


def test_a_missing_total_of_borrowings_leaves_only_debt_to_equity_undefined():
    values = {k: v for k, v in CURRENT_VALUES.items() if k is not F.TOTAL_BORROWINGS}

    metrics = calculate_metrics(field_set(current=values))

    assert metrics.get("MET-04", CUR).undefined_reason is M.MISSING_INPUT and metrics.get("MET-03", CUR).defined
    assert metrics.comparison("MET-04").undefined_reason is M.MISSING_INPUT and metrics.comparison("MET-03").relative_change is not None


def test_a_field_that_needs_review_makes_only_the_metrics_that_read_it_undefined():
    extra = [rec(F.CURRENT_ASSETS, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)]
    values = {k: v for k, v in CURRENT_VALUES.items() if k is not F.CURRENT_ASSETS}

    metrics = calculate_metrics(field_set(current=values, extra=extra))

    assert metrics.get("MET-03", CUR).undefined_reason is M.INPUT_REQUIRES_REVIEW
    assert metrics.get("MET-02", CUR).defined and metrics.get("MET-05", CUR).defined


def test_an_unverified_operating_profit_leaves_interest_coverage_undefined_with_no_fallback():
    values = dict(CURRENT_VALUES)
    extra = [rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)]

    metrics = calculate_metrics(field_set(current=values, extra=extra))

    assert metrics.get("MET-05", CUR).undefined_reason is M.INPUT_REQUIRES_REVIEW
    assert metrics.get("MET-05", COMP).defined  # the other period is untouched


# --- the comparison (I.3) ---------------------------------------------------------------------------------------------------


def test_the_comparison_is_the_relative_change_in_percent():
    metrics = calculate_metrics(field_set())

    assert metrics.comparison("MET-03").relative_change == Decimal("25")  # 1.2 to 1.5
    assert metrics.comparison("MET-04").relative_change == Decimal("33.33333333333333333333333333")  # 0.6 to 0.8
    assert metrics.comparison("MET-02").relative_change == Decimal("25")  # 8 to 10 percent


def test_a_comparison_names_both_results():
    comparison = calculate_metrics(field_set()).comparison("MET-03")

    assert comparison.current.value == Decimal("1.5") and comparison.comparative.value == Decimal("1.2") and comparison.metric_id == "MET-03"


def result(value, reason=None, metric="MET-03"):
    return MetricResult(metric, "m", Unit.RATIO, "f", None if reason else Decimal(value), reason, (), (), ())


def test_a_fall_is_a_negative_change():
    assert compare(result("0.9"), result("1")).relative_change == Decimal("-10")


def test_if_either_result_is_undefined_the_comparison_is_undefined():
    assert compare(result(None, M.ZERO_DENOMINATOR), result("1")).undefined_reason is M.ZERO_DENOMINATOR
    assert compare(result("1"), result(None, M.MISSING_INPUT)).undefined_reason is M.MISSING_INPUT
    assert compare(result(None, M.INPUT_CONFLICTING), result(None, M.MISSING_INPUT)).undefined_reason is M.INPUT_CONFLICTING


def test_a_zero_or_negative_comparative_base_is_undefined():
    assert compare(result("1"), result("0")).undefined_reason is M.ZERO_DENOMINATOR
    assert compare(result("1"), result("-2")).undefined_reason is M.NON_POSITIVE_BASE


def test_a_zero_current_value_against_a_positive_base_is_minus_one_hundred_percent():
    assert compare(result("0"), result("2")).relative_change == Decimal("-100")


def test_a_comparison_of_two_different_metrics_is_a_caller_error():
    with pytest.raises(ValueError):
        compare(result("1", metric="MET-03"), result("1", metric="MET-04"))


def test_a_comparison_has_a_change_or_a_reason_never_both_or_neither():
    one = result("1")
    with pytest.raises(ValueError):
        Comparison("MET-03", one, one, None, None)
    with pytest.raises(ValueError):
        Comparison("MET-03", one, one, Decimal(1), M.MISSING_INPUT)


# --- properties -----------------------------------------------------------------------------------------------------------------


def test_property_the_order_of_the_records_does_not_change_the_answer():
    rng = random.Random(60)
    base = (*records(CURRENT_VALUES, CUR), *records(COMPARATIVE_VALUES, COMP))
    expected = calculate_metrics(FieldSet(Basis.CONSOLIDATED, base, (), (), ())).results
    for _ in range(50):
        shuffled = list(base)
        rng.shuffle(shuffled)
        assert calculate_metrics(FieldSet(Basis.CONSOLIDATED, tuple(shuffled), (), (), ())).results == expected


def test_property_scaling_every_amount_leaves_every_ratio_and_comparison_unchanged():
    rng = random.Random(61)
    for _ in range(100):
        k = Decimal(rng.randint(2, 500))
        scaled = lambda values: {n: str(Decimal(v) * k) for n, v in values.items()}  # noqa: E731
        a, b = calculate_metrics(field_set()), calculate_metrics(field_set(scaled(CURRENT_VALUES), scaled(COMPARATIVE_VALUES)))
        for key, result_a in a.results.items():
            assert result_a.value == b.results[key].value
        for metric, comparison in a.comparisons.items():
            assert comparison.relative_change == b.comparisons[metric].relative_change
