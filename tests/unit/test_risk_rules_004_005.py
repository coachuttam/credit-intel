"""RI-004 increasing leverage and RI-005 weak interest coverage (PRD J.3, FR-008, v0.4.23; Phase 4 step 4d; B-250).

Each condition is tested at, below and above its threshold, and for what it lacks. Synthetic field sets only.
"""

from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.borrowings import CAVEAT_NOT_PRESENTED
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status
from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.results import ConditionOutcome as C, RuleOutcome as R
from credit_intel.risk.rules import RULE_FUNCTIONS, increasing_leverage, weak_interest_coverage
from credit_intel.risk.spec import Severity

COMP = PeriodRole.COMPARATIVE
CONFIG = load_risk_rules()


def build(current, comparative, extra=()):
    records = [rec(n, v, role=CUR, end=D25) for n, v in current.items() if v is not None]
    records += [rec(n, v, role=COMP, end=D24) for n, v in comparative.items() if v is not None]
    records += list(extra)
    field_set = FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())
    return field_set, calculate_metrics(field_set)


def leverage(current, comparative, extra=()):
    field_set, metrics = build(current, comparative, extra)
    return increasing_leverage(CONFIG.rule("RI-004"), field_set, metrics)


def borrowings_equity(borrowings, equity):
    return {F.TOTAL_BORROWINGS: borrowings, F.TOTAL_EQUITY: equity}


# --- RI-004 C1: debt-to-equity rose by at least 20 percent (watch) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current_borrowings", "c1"),
    [("119", C.NOT_FIRED), ("119.99", C.NOT_FIRED), ("120", C.FIRED), ("120.01", C.FIRED), ("100", C.NOT_FIRED), ("80", C.NOT_FIRED)],
)  # the comparative ratio is 1.00 (100 over 100): a rise of exactly 20 percent is 1.20
def test_ri004_c1_at_below_and_above_a_rise_of_twenty_percent(current_borrowings, c1):
    result = leverage(borrowings_equity(current_borrowings, "100"), borrowings_equity("100", "100"))

    assert result.conditions[0].outcome is c1 and result.conditions[0].threshold == Decimal("20")


def test_ri004_c1_records_the_ratios_and_the_change():
    result = leverage(borrowings_equity("150", "100"), borrowings_equity("100", "100"))

    c1 = result.conditions[0]
    assert c1.values_used == (("debt_to_equity_current", Decimal("1.5")), ("debt_to_equity_comparative", Decimal("1")), ("relative_change_percent", Decimal("50")))
    assert c1.metric_ids == ("MET-04.2025-03-31", "MET-04.2024-03-31")
    assert "total_borrowings.2025-03-31.consolidated" in c1.field_ids and "total_equity.2024-03-31.consolidated" in c1.field_ids


# --- C2: the current ratio is above 2.00 (elevated) -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("borrowings", "c2"), [("199", C.NOT_FIRED), ("200", C.NOT_FIRED), ("200.01", C.FIRED), ("201", C.FIRED), ("0", C.NOT_FIRED)])
def test_ri004_c2_at_below_and_above_two(borrowings, c2):
    result = leverage(borrowings_equity(borrowings, "100"), borrowings_equity("1000", "100"))  # a falling ratio, so C1 is quiet

    assert result.conditions[1].outcome is c2 and result.conditions[1].threshold == Decimal("2.00")


def test_ri004_c2_records_the_ratio_and_the_references():
    result = leverage(borrowings_equity("250", "100"), borrowings_equity("250", "100"))

    c2 = result.conditions[1]
    assert c2.values_used == (("debt_to_equity_current", Decimal("2.5")),) and c2.metric_ids == ("MET-04.2025-03-31",)
    assert c2.field_ids == ("total_borrowings.2025-03-31.consolidated", "total_equity.2025-03-31.consolidated")


# --- C3: equity at or below zero in either period (elevated) ------------------------------------------------------------------------------


@pytest.mark.parametrize(("equity", "c3"), [("1", C.NOT_FIRED), ("0.01", C.NOT_FIRED), ("0", C.FIRED), ("-0.01", C.FIRED), ("-500", C.FIRED)])
def test_ri004_c3_at_below_and_above_zero_in_the_current_period(equity, c3):
    result = leverage(borrowings_equity("10", equity), borrowings_equity("10", "100"))

    assert result.conditions[2].outcome is c3 and result.conditions[2].threshold == Decimal("0")


def test_ri004_c3_fires_on_a_comparative_period_with_non_positive_equity():
    result = leverage(borrowings_equity("10", "100"), borrowings_equity("10", "-1"))

    assert result.conditions[2].outcome is C.FIRED and result.conditions[2].note == "negative or zero equity"
    assert result.outcome is R.TRIGGERED and result.severity is Severity.ELEVATED


def test_ri004_c3_is_not_triggered_only_if_both_periods_have_extracted_positive_equity():
    result = leverage(borrowings_equity("10", "100"), borrowings_equity("10", "100"))
    assert result.conditions[2].outcome is C.NOT_FIRED

    one_missing = leverage(borrowings_equity("10", "100"), {F.TOTAL_BORROWINGS: "10"})
    assert one_missing.conditions[2].outcome is C.NOT_EVALUABLE
    assert one_missing.conditions[2].missing_inputs == ("total_equity.comparative (not_found)",)


def test_ri004_c3_fires_even_if_the_other_periods_equity_is_unusable():
    review = rec(F.TOTAL_EQUITY, status=Status.REQUIRES_REVIEW, role=COMP, end=D24)

    result = leverage(borrowings_equity("10", "-5"), {F.TOTAL_BORROWINGS: "10"}, extra=[review])

    assert result.conditions[2].outcome is C.FIRED


def test_ri004_c3_with_a_review_equity_in_the_only_other_period_is_not_evaluable():
    review = rec(F.TOTAL_EQUITY, status=Status.REQUIRES_REVIEW, role=COMP, end=D24)

    result = leverage(borrowings_equity("10", "100"), {F.TOTAL_BORROWINGS: "10"}, extra=[review])

    assert result.conditions[2].outcome is C.NOT_EVALUABLE
    assert result.conditions[2].missing_inputs == ("total_equity.2024-03-31 (requires_review)",)


# --- the rule: severity and the J.3 example ---------------------------------------------------------------------------------------------------


def test_ri004_severity_is_the_highest_condition_that_fired():
    assert leverage(borrowings_equity("120", "100"), borrowings_equity("100", "100")).severity is Severity.WATCH  # C1 only
    assert leverage(borrowings_equity("250", "100"), borrowings_equity("250", "100")).severity is Severity.ELEVATED  # C2 only
    assert leverage(borrowings_equity("50", "100"), borrowings_equity("50", "100")).outcome is R.NOT_TRIGGERED


def test_j3_ri004_with_negative_equity_and_missing_borrowings_is_triggered_and_lists_the_missing_inputs():
    result = leverage({F.TOTAL_EQUITY: "-100"}, {F.TOTAL_EQUITY: "100"})

    assert result.outcome is R.TRIGGERED and result.severity is Severity.ELEVATED
    assert [c.outcome for c in result.conditions] == [C.NOT_EVALUABLE, C.NOT_EVALUABLE, C.FIRED]
    assert "MET-04.2025-03-31 (missing_input)" in result.missing_inputs


def test_ri004_without_a_comparative_period_still_evaluates_c2_and_c3():
    result = leverage(borrowings_equity("250", "100"), {})

    assert [c.outcome for c in result.conditions] == [C.NOT_EVALUABLE, C.FIRED, C.NOT_EVALUABLE]
    assert result.outcome is R.TRIGGERED


# --- the borrowings caveat travels (PRD v0.4.23) -------------------------------------------------------------------------------------------------


def components(non_current, current, equity):
    return {F.BORROWINGS_NON_CURRENT: non_current, F.BORROWINGS_CURRENT: current, F.TOTAL_EQUITY: equity}


def test_a_derived_total_of_borrowings_puts_the_caveat_on_the_conditions_and_the_rule():
    result = leverage(components("200", "100", "100"), components("100", "50", "100"))

    assert result.caveats == (CAVEAT_NOT_PRESENTED,)
    assert result.conditions[0].caveats == (CAVEAT_NOT_PRESENTED,) and result.conditions[1].caveats == (CAVEAT_NOT_PRESENTED,)
    assert result.conditions[2].caveats == ()  # equity alone has no assumption behind it


def test_a_reported_total_of_borrowings_carries_no_caveat():
    assert leverage(borrowings_equity("250", "100"), borrowings_equity("100", "100")).caveats == ()


def test_the_caveat_stays_on_a_condition_that_could_not_be_evaluated_because_equity_was_negative():
    result = leverage(components("200", "100", "-10"), components("100", "50", "100"))

    assert [c.outcome for c in result.conditions][:2] == [C.NOT_EVALUABLE, C.NOT_EVALUABLE]
    assert result.conditions[1].caveats == (CAVEAT_NOT_PRESENTED,)  # the metric is undefined but still carries it
    assert "not_meaningful_negative_equity" in result.conditions[1].missing_inputs[0]


def test_the_caveat_is_still_reported_when_only_the_equity_condition_fired():
    result = leverage(components("200", "100", "-10"), components("100", "50", "100"))

    assert result.outcome is R.TRIGGERED and result.caveats == (CAVEAT_NOT_PRESENTED,)


# --- RI-005 weak interest coverage ---------------------------------------------------------------------------------------------------------------


def coverage(ebit, interest, extra=(), comparative=None):
    current = {F.OPERATING_PROFIT: ebit, F.INTEREST_EXPENSE: interest}
    field_set, metrics = build(current, comparative or {}, extra)
    return weak_interest_coverage(CONFIG.rule("RI-005"), field_set, metrics)


@pytest.mark.parametrize(
    ("ebit", "c1", "c2"),
    [
        ("200", C.NOT_FIRED, C.NOT_FIRED),  # 2.00
        ("150", C.NOT_FIRED, C.NOT_FIRED),  # exactly 1.50: not below it
        ("149", C.FIRED, C.NOT_FIRED),  # 1.49
        ("101", C.FIRED, C.NOT_FIRED),  # 1.01
        ("100", C.FIRED, C.NOT_FIRED),  # exactly 1.00: C2 is not below it
        ("99", C.FIRED, C.FIRED),  # 0.99
        ("0", C.FIRED, C.FIRED),
        ("-50", C.FIRED, C.FIRED),  # negative coverage is included
    ],
)
def test_ri005_at_below_and_above_each_threshold(ebit, c1, c2):
    result = coverage(ebit, "100")

    assert [c.outcome for c in result.conditions] == [c1, c2]
    assert result.conditions[0].threshold == Decimal("1.50") and result.conditions[1].threshold == Decimal("1.00")


def test_ri005_severity():
    assert coverage("149", "100").severity is Severity.WATCH
    assert coverage("99", "100").severity is Severity.ELEVATED
    assert coverage("200", "100").outcome is R.NOT_TRIGGERED


def test_ri005_records_the_value_and_the_evidence():
    result = coverage("99", "100")

    first = result.conditions[0]
    assert first.values_used == (("interest_coverage_current", Decimal("0.99")),) and first.metric_ids == ("MET-05.2025-03-31",)
    assert "interest_expense.2025-03-31.consolidated" in first.field_ids


def test_ri005_with_no_interest_expense_neither_condition_fires_and_a_note_says_why():
    result = coverage("300", "0")

    assert result.outcome is R.NOT_TRIGGERED and result.severity is None
    assert [c.outcome for c in result.conditions] == [C.NOT_FIRED, C.NOT_FIRED]
    assert all("not applicable" in c.note for c in result.conditions) and "not applicable" in result.notes[0]


def test_ri005_with_no_coverage_for_another_reason_cannot_be_evaluated():
    result = coverage("300", None)

    assert result.outcome is R.NOT_EVALUABLE and result.severity is None
    assert result.missing_inputs == ("MET-05.2025-03-31 (missing_input)",)


def test_ri005_an_unverified_operating_profit_blocks_the_coverage_and_says_so():
    review = rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)

    result = coverage(None, "100", extra=[review])

    assert result.outcome is R.NOT_EVALUABLE
    assert "MET-05.2025-03-31 (input_requires_review)" in result.missing_inputs


def test_ri005_derives_ebit_from_profit_before_tax_when_operating_profit_is_not_found():
    field_set, metrics = build({F.PROFIT_BEFORE_TAX: "60", F.INTEREST_EXPENSE: "40"}, {})

    result = weak_interest_coverage(CONFIG.rule("RI-005"), field_set, metrics)

    assert result.conditions[0].values_used == (("interest_coverage_current", Decimal("2.5")),) and result.outcome is R.NOT_TRIGGERED


# --- both -------------------------------------------------------------------------------------------------------------------------------------------


def test_the_rule_functions_are_registered():
    assert set(RULE_FUNCTIONS) >= {"RI-004", "RI-005"}
