"""MET-01 revenue growth and MET-02 net profit margin (PRD I.1, I.2, FR-007; Phase 3 step 3c; B-240)."""

import random
from datetime import date
from decimal import Decimal, getcontext, localcontext

import pytest

from calc_records import CUR, D24, D25, conflicting, rec
from credit_intel.calculations.metrics import MetricReason as M, MetricResult, Unit, net_profit_margin, revenue_growth
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status

COMP = PeriodRole.COMPARATIVE


def rev(value, role=CUR, **kw):
    end = D25 if role is CUR else D24
    return rec(F.REVENUE, value, role=role, end=end, **kw)


def growth(current, comparative, **kw):
    return revenue_growth(rev(current, CUR, **kw) if current is not None else None, rev(comparative, COMP, **kw) if comparative is not None else None)


def margin(net, revenue, **kw):
    return net_profit_margin(rec(F.NET_PROFIT, net, **kw) if net is not None else None, rec(F.REVENUE, revenue, **kw) if revenue is not None else None)


# --- MET-01: the PRD's acceptance tests ---------------------------------------------------------------------------------------


def test_met01_100_to_110_is_ten_percent():
    result = growth("110", "100")

    assert result.value == Decimal("10") and result.undefined_reason is None and result.unit is Unit.PERCENT
    assert result.metric_id == "MET-01" and result.defined


def test_met01_100_to_90_is_minus_ten_percent():
    assert growth("90", "100").value == Decimal("-10")


def test_met01_a_zero_comparative_is_undefined_with_zero_denominator():
    result = growth("50", "0")

    assert result.value is None and result.undefined_reason is M.ZERO_DENOMINATOR and not result.defined


def test_met01_a_missing_comparative_is_undefined_with_missing_input():
    for result in (growth("110", None), revenue_growth(rev("110"), rec(F.REVENUE, status=Status.NOT_FOUND, role=COMP, end=D24))):
        assert result.value is None and result.undefined_reason is M.MISSING_INPUT


def test_met01_a_missing_current_period_is_undefined_with_missing_input():
    assert growth(None, "100").undefined_reason is M.MISSING_INPUT


# --- MET-01: edge cases ------------------------------------------------------------------------------------------------------


def test_met01_a_negative_comparative_is_not_a_positive_base():
    assert growth("10", "-5").undefined_reason is M.NON_POSITIVE_BASE


def test_met01_a_negative_current_is_input_requires_review():
    assert growth("-10", "100").undefined_reason is M.INPUT_REQUIRES_REVIEW


def test_met01_the_result_is_exact_not_rounded():
    assert growth("4", "3").value == Decimal("33.33333333333333333333333333")  # 28 significant digits


def test_met01_zero_current_revenue_is_minus_one_hundred_percent():
    assert growth("0", "100").value == Decimal("-100")


def test_met01_the_periods_must_be_consecutive():
    older = rec(F.REVENUE, "100", role=COMP, end=date(2023, 3, 31))

    assert revenue_growth(rev("110"), older).undefined_reason is M.PERIOD_MISMATCH


def test_met01_leap_day_and_28_february_count_as_one_day():
    current = rec(F.REVENUE, "110", end=date(2025, 2, 28))
    comparative = rec(F.REVENUE, "100", role=COMP, end=date(2024, 2, 29))

    assert revenue_growth(current, comparative).value == Decimal("10")


def test_met01_two_currencies_are_undefined():
    assert revenue_growth(rev("110", currency="INR"), rev("100", COMP, currency="USD")).undefined_reason is M.CURRENCY_MISMATCH


def test_met01_arguments_in_the_wrong_roles_are_a_caller_error():
    with pytest.raises(ValueError):
        revenue_growth(rev("100", COMP), rev("110", CUR))


def test_met01_inputs_of_two_bases_are_a_caller_error():
    with pytest.raises(ValueError):
        revenue_growth(rev("110"), rev("100", COMP, basis=Basis.STANDALONE))


# --- input statuses and their precedence (I.1) ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "reason"),
    [(Status.NOT_FOUND, M.MISSING_INPUT), (Status.REQUIRES_REVIEW, M.INPUT_REQUIRES_REVIEW)],
)
def test_a_non_extracted_input_makes_the_metric_undefined_with_the_matching_reason(status, reason):
    assert revenue_growth(rev("110"), rec(F.REVENUE, status=status, role=COMP, end=D24)).undefined_reason is reason
    assert net_profit_margin(rec(F.NET_PROFIT, "5"), rec(F.REVENUE, status=status)).undefined_reason is reason


def test_a_conflicting_input_makes_the_metric_undefined_with_input_conflicting():
    result = net_profit_margin(rec(F.NET_PROFIT, "5"), conflicting(F.REVENUE, ["100", "110"]))

    assert result.undefined_reason is M.INPUT_CONFLICTING and result.value is None


def test_missing_outranks_conflicting_outranks_requires_review():
    review = rec(F.NET_PROFIT, status=Status.REQUIRES_REVIEW)
    assert net_profit_margin(review, conflicting(F.REVENUE, ["1", "2"])).undefined_reason is M.INPUT_CONFLICTING
    assert net_profit_margin(review, rec(F.REVENUE, status=Status.NOT_FOUND)).undefined_reason is M.MISSING_INPUT
    assert net_profit_margin(conflicting(F.NET_PROFIT, ["1", "2"]), None).undefined_reason is M.MISSING_INPUT


# --- MET-02: the PRD's acceptance tests -------------------------------------------------------------------------------------


def test_met02_10_over_200_is_five_percent():
    result = margin("10", "200")

    assert result.value == Decimal("5") and result.unit is Unit.PERCENT and result.metric_id == "MET-02"


def test_met02_a_loss_gives_a_valid_negative_margin():
    assert margin("-10", "200").value == Decimal("-5")


def test_met02_zero_revenue_is_undefined_with_zero_denominator():
    assert margin("10", "0").undefined_reason is M.ZERO_DENOMINATOR


def test_met02_negative_revenue_is_not_a_positive_base():
    assert margin("10", "-200").undefined_reason is M.NON_POSITIVE_BASE


def test_met02_zero_profit_is_a_zero_margin():
    assert margin("0", "200").value == Decimal("0")


def test_met02_two_currencies_or_two_period_ends_are_undefined():
    assert net_profit_margin(rec(F.NET_PROFIT, "5", currency="USD"), rec(F.REVENUE, "100")).undefined_reason is M.CURRENCY_MISMATCH
    assert net_profit_margin(rec(F.NET_PROFIT, "5", end=date(2025, 4, 1)), rec(F.REVENUE, "100")).undefined_reason is M.PERIOD_MISMATCH


def test_met02_inputs_of_two_period_roles_are_a_caller_error():
    with pytest.raises(ValueError):
        net_profit_margin(rec(F.NET_PROFIT, "5"), rec(F.REVENUE, "100", role=COMP, end=D24))


# --- what every result records (FR-007.2) --------------------------------------------------------------------------------------


def test_a_result_records_formula_input_ids_input_values_and_periods():
    result = growth("110", "100")

    assert result.formula == "(revenue_current - revenue_comparative) / revenue_comparative x 100"
    assert result.input_field_ids == ("revenue.2025-03-31.consolidated", "revenue.2024-03-31.consolidated")
    assert result.input_values == (Decimal("110"), Decimal("100")) and result.period_ends == (D25, D24)


def test_an_undefined_result_still_names_its_inputs_and_what_is_missing():
    result = growth("110", None)

    assert result.input_field_ids == ("revenue.2025-03-31.consolidated", "revenue") and result.input_values == (Decimal("110"), None)
    assert result.period_ends == (D25,)


def test_the_margin_records_one_period():
    result = margin("10", "200")

    assert result.period_ends == (D25,) and result.input_field_ids == ("net_profit.2025-03-31.consolidated", "revenue.2025-03-31.consolidated")


def test_a_result_has_a_value_or_a_reason_never_both_or_neither():
    base = dict(metric_id="X", name="x", unit=Unit.RATIO, formula="f", input_field_ids=(), input_values=(), period_ends=())
    with pytest.raises(ValueError):
        MetricResult(value=None, undefined_reason=None, **base)
    with pytest.raises(ValueError):
        MetricResult(value=Decimal(1), undefined_reason=M.MISSING_INPUT, **base)
    with pytest.raises(TypeError):
        MetricResult(value=1.5, undefined_reason=None, **base)  # a float is never a value


# --- determinism ------------------------------------------------------------------------------------------------------------


def test_the_callers_decimal_context_does_not_change_a_result():
    expected = growth("4", "3").value
    with localcontext() as context:
        context.prec = 3
        assert growth("4", "3").value == expected
    assert getcontext().prec == 28


def test_property_scaling_both_inputs_leaves_a_ratio_unchanged():
    rng = random.Random(40)
    for _ in range(300):
        a, b = Decimal(rng.randint(1, 10**6)) / 100, Decimal(rng.randint(1, 10**6)) / 100
        k = Decimal(rng.randint(1, 1000))
        assert margin(str(a), str(b)).value == margin(str(a * k), str(b * k)).value
        assert growth(str(a), str(b)).value == growth(str(a * k), str(b * k)).value


def test_property_growth_inverts_the_comparative_for_any_positive_pair():
    rng = random.Random(41)
    for _ in range(300):
        current, comparative = (Decimal(rng.randint(1, 10**5)) for _ in range(2))
        g = growth(str(current), str(comparative)).value
        assert abs(comparative * (1 + g / 100) - current) < Decimal("1e-20")
