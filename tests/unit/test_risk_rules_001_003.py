"""RI-001 declining revenue, RI-002 negative net profit, RI-003 deteriorating liquidity (PRD J.3, FR-008; Phase 4 step 4c; B-249).

Each condition is tested at, below and above its threshold, and for what it lacks. Synthetic field sets only.
"""

from decimal import Decimal
from fractions import Fraction

import pytest

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status
from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.results import ConditionOutcome as C, RuleOutcome as R
from credit_intel.risk.rules import RULE_FUNCTIONS, declining_revenue, deteriorating_liquidity, negative_net_profit
from credit_intel.risk.spec import Severity

COMP = PeriodRole.COMPARATIVE
CONFIG = load_risk_rules()
BASE = {F.REVENUE: "100000", F.NET_PROFIT: "5000", F.CURRENT_ASSETS: "150", F.CURRENT_LIABILITIES: "100"}


def scenario(current=None, comparative=None, extra=()):
    cur = {**BASE, **(current or {})}
    com = {**BASE, **(comparative if comparative is not None else {})} if comparative != {} or comparative is None else {}
    records = [rec(n, v, role=CUR, end=D25) for n, v in cur.items() if v is not None]
    records += [rec(n, v, role=COMP, end=D24) for n, v in com.items() if v is not None]
    records += list(extra)
    field_set = FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())
    return field_set, calculate_metrics(field_set)


def evaluate(function, rule_id, field_set, metrics, config=CONFIG):
    return function(config.rule(rule_id), field_set, metrics)


def ri001(current_revenue, comparative_revenue="100000", config=CONFIG):
    field_set, metrics = scenario({F.REVENUE: current_revenue}, {F.REVENUE: comparative_revenue})
    return evaluate(declining_revenue, "RI-001", field_set, metrics, config)


# --- RI-001: growth below 0 (watch); at or below -10 (elevated) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "growth", "c1", "c2"),
    [
        ("110000", "10", C.NOT_FIRED, C.NOT_FIRED),
        ("100000", "0", C.NOT_FIRED, C.NOT_FIRED),  # at the C1 threshold: not below it
        ("99999", "-0.001", C.FIRED, C.NOT_FIRED),  # just below 0
        ("95000", "-5", C.FIRED, C.NOT_FIRED),
        ("90001", "-9.999", C.FIRED, C.NOT_FIRED),  # just above -10
        ("90000", "-10", C.FIRED, C.FIRED),  # at the C2 threshold: at or below fires
        ("89999", "-10.001", C.FIRED, C.FIRED),  # just below -10
    ],
)
def test_ri001_at_below_and_above_each_threshold(current, growth, c1, c2):
    result = ri001(current)

    assert [c.outcome for c in result.conditions] == [c1, c2]
    assert result.conditions[0].values_used == (("revenue_growth_percent", Decimal(growth)),)


def test_ri001_severity_is_the_highest_condition_that_fired():
    assert ri001("95000").severity is Severity.WATCH
    assert ri001("85000").severity is Severity.ELEVATED
    assert ri001("110000").severity is None and ri001("110000").outcome is R.NOT_TRIGGERED


def test_ri001_records_its_threshold_references_and_evidence():
    result = ri001("85000")

    first = result.conditions[0]
    assert first.threshold == Decimal("0") and result.conditions[1].threshold == Decimal("-10")
    assert first.metric_ids == ("MET-01.2025-03-31",)
    assert first.field_ids == ("revenue.2025-03-31.consolidated", "revenue.2024-03-31.consolidated")


def test_ri001_without_a_comparative_period_cannot_be_evaluated():
    field_set, metrics = scenario(comparative={})

    result = evaluate(declining_revenue, "RI-001", field_set, metrics)

    assert result.outcome is R.NOT_EVALUABLE and result.severity is None
    assert result.missing_inputs == ("MET-01.2025-03-31 (missing_input)",)
    assert all(c.outcome is C.NOT_EVALUABLE for c in result.conditions)


def test_ri001_with_a_zero_comparative_revenue_cannot_be_evaluated():
    result = ri001("100", comparative_revenue="0")

    assert result.outcome is R.NOT_EVALUABLE and "zero_denominator" in result.missing_inputs[0]


def test_ri001_thresholds_come_from_the_file_not_the_code(tmp_path):
    text = open("config/risk_rules.toml", encoding="utf-8").read().replace("threshold = -10", "threshold = -3", 1)
    path = tmp_path / "rules.toml"
    path.write_text(text, encoding="utf-8")
    custom = load_risk_rules(path)

    assert ri001("96000", config=custom).severity is Severity.ELEVATED  # -4 is at or below the new -3
    assert ri001("96000").severity is Severity.WATCH  # but only below 0 with the shipped -10


# --- RI-002: current net profit below 0 (elevated) ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("profit", "outcome"), [("-0.01", C.FIRED), ("-5000", C.FIRED), ("0", C.NOT_FIRED), ("0.01", C.NOT_FIRED), ("5000", C.NOT_FIRED)])
def test_ri002_at_below_and_above_the_threshold(profit, outcome):
    field_set, metrics = scenario({F.NET_PROFIT: profit})

    result = evaluate(negative_net_profit, "RI-002", field_set, metrics)

    assert result.conditions[0].outcome is outcome
    assert result.outcome is (R.TRIGGERED if outcome is C.FIRED else R.NOT_TRIGGERED)
    assert result.severity is (Severity.ELEVATED if outcome is C.FIRED else None)


def test_ri002_only_looks_at_the_current_period():
    field_set, metrics = scenario(comparative={F.NET_PROFIT: "-9999"})

    assert evaluate(negative_net_profit, "RI-002", field_set, metrics).outcome is R.NOT_TRIGGERED


def test_ri002_records_the_value_and_the_field():
    field_set, metrics = scenario({F.NET_PROFIT: "-5"})

    condition = evaluate(negative_net_profit, "RI-002", field_set, metrics).conditions[0]

    assert condition.values_used == (("net_profit", Decimal("-5")),) and condition.field_ids == ("net_profit.2025-03-31.consolidated",)


@pytest.mark.parametrize(("record", "expected"), [
    (rec(F.NET_PROFIT, status=Status.NOT_FOUND, role=CUR, end=D25), "net_profit.2025-03-31 (not_found)"),
    (rec(F.NET_PROFIT, status=Status.REQUIRES_REVIEW, role=CUR, end=D25), "net_profit.2025-03-31 (requires_review)"),
])  # fmt: skip
def test_ri002_with_an_unusable_net_profit_cannot_be_evaluated(record, expected):
    field_set, metrics = scenario({F.NET_PROFIT: None}, extra=[record])

    result = evaluate(negative_net_profit, "RI-002", field_set, metrics)

    assert result.outcome is R.NOT_EVALUABLE and result.missing_inputs == (expected,)


def test_ri002_with_no_net_profit_record_at_all_cannot_be_evaluated():
    field_set, metrics = scenario({F.NET_PROFIT: None})

    assert evaluate(negative_net_profit, "RI-002", field_set, metrics).missing_inputs == ("net_profit.current (not_found)",)


# --- RI-003: ratio below 1.00 (elevated); a fall of 10 or more (watch) ----------------------------------------------------------------------


def ri003(current_assets, comparative_assets="150", **kw):
    field_set, metrics = scenario({F.CURRENT_ASSETS: current_assets}, {F.CURRENT_ASSETS: comparative_assets}, **kw)
    return evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)


@pytest.mark.parametrize(
    ("assets", "c1"),
    [("101", C.NOT_FIRED), ("100", C.NOT_FIRED), ("99", C.FIRED), ("84", C.FIRED)],  # liabilities 100: ratios 1.01, 1.00, 0.99
)
def test_ri003_c1_at_below_and_above_one(assets, c1):
    assert ri003(assets).conditions[0].outcome is c1


@pytest.mark.parametrize(
    ("assets", "c2"),
    [
        ("135", C.FIRED),  # 1.50 to 1.35: a fall of exactly 10 percent
        ("135.01", C.NOT_FIRED),  # just inside
        ("134.99", C.FIRED),  # just beyond
        ("150", C.NOT_FIRED),
        ("200", C.NOT_FIRED),  # a rise never fires
    ],
)
def test_ri003_c2_at_below_and_above_a_fall_of_ten_percent(assets, c2):
    result = ri003(assets)

    name, change = result.conditions[1].values_used[2]
    exact = (Fraction(assets) / 100 - Fraction(3, 2)) / Fraction(3, 2) * 100  # liabilities are 100, the comparative ratio is 1.5
    assert result.conditions[1].outcome is c2 and name == "relative_change_percent"
    assert abs(Fraction(change) - exact) < Fraction(1, 10**20)


def test_ri003_severity_c1_elevated_c2_watch():
    assert ri003("99", "99").severity is Severity.ELEVATED  # ratio 0.99, no fall
    assert ri003("135").severity is Severity.WATCH  # ratio 1.35 but fell 10 percent
    assert ri003("84").severity is Severity.ELEVATED  # both fire
    assert ri003("150").outcome is R.NOT_TRIGGERED


def test_j3_ri003_with_a_ratio_of_0_84_and_no_comparative_period_is_triggered():
    field_set, metrics = scenario({F.CURRENT_ASSETS: "84"}, comparative={})

    result = evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)

    assert result.outcome is R.TRIGGERED and result.severity is Severity.ELEVATED
    assert [c.outcome for c in result.conditions] == [C.FIRED, C.NOT_EVALUABLE]
    assert result.missing_inputs == ("MET-03.comparative (missing_input)",)


def test_j3_ri003_with_a_ratio_of_1_20_and_no_comparative_period_is_not_evaluable():
    field_set, metrics = scenario({F.CURRENT_ASSETS: "120"}, comparative={})

    result = evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)

    assert result.outcome is R.NOT_EVALUABLE and result.severity is None
    assert [c.outcome for c in result.conditions] == [C.NOT_FIRED, C.NOT_EVALUABLE]


def test_ri003_with_no_current_ratio_cannot_evaluate_either_condition():
    field_set, metrics = scenario({F.CURRENT_ASSETS: None})

    result = evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)

    assert result.outcome is R.NOT_EVALUABLE
    assert all(c.outcome is C.NOT_EVALUABLE for c in result.conditions)
    assert "MET-03.2025-03-31 (missing_input)" in result.missing_inputs


def test_ri003_with_a_zero_comparative_ratio_has_c1_but_no_comparison():
    field_set, metrics = scenario({F.CURRENT_ASSETS: "84"}, {F.CURRENT_ASSETS: "0"})

    result = evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)

    assert [c.outcome for c in result.conditions] == [C.FIRED, C.NOT_EVALUABLE]
    assert result.missing_inputs == ("MET-03 comparison (zero_denominator)",)


def test_ri003_records_the_references_values_and_threshold():
    result = ri003("135")

    c2 = result.conditions[1]
    assert c2.threshold == Decimal("10") and c2.metric_ids == ("MET-03.2025-03-31", "MET-03.2024-03-31")
    assert c2.values_used[:2] == (("current_ratio_current", Decimal("1.35")), ("current_ratio_comparative", Decimal("1.5")))
    assert "current_assets.2025-03-31.consolidated" in c2.field_ids and "current_liabilities.2024-03-31.consolidated" in c2.field_ids


def test_ri003_a_review_input_makes_the_ratio_unusable_and_says_why():
    review = rec(F.CURRENT_ASSETS, status=Status.REQUIRES_REVIEW, role=CUR, end=D25)
    field_set, metrics = scenario({F.CURRENT_ASSETS: None}, extra=[review])

    result = evaluate(deteriorating_liquidity, "RI-003", field_set, metrics)

    assert "MET-03.2025-03-31 (input_requires_review)" in result.missing_inputs


# --- all three -----------------------------------------------------------------------------------------------------------------------------------


def test_the_rule_functions_are_registered_by_rule_id():
    assert set(RULE_FUNCTIONS) >= {"RI-001", "RI-002", "RI-003"}


def test_the_evaluation_does_not_change_its_inputs_and_is_repeatable():
    field_set, metrics = scenario({F.REVENUE: "85000", F.NET_PROFIT: "-1", F.CURRENT_ASSETS: "84"})
    before = [r.model_dump() for r in field_set.fields]

    ids = ("RI-001", "RI-002", "RI-003")
    first = [RULE_FUNCTIONS[i](CONFIG.rule(i), field_set, metrics) for i in ids]
    second = [RULE_FUNCTIONS[i](CONFIG.rule(i), field_set, metrics) for i in ids]

    assert first == second and [r.model_dump() for r in field_set.fields] == before
    assert [r.outcome for r in first] == [R.TRIGGERED, R.TRIGGERED, R.TRIGGERED]
