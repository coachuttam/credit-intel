"""The memo's wording of each rule condition says what the rule does (PRD J.3, J.4; Phase 5 step 5g; B-263).

The operator of a condition lives in ``risk/rules.py`` and the memo's phrase in ``memo/rule_text.py``. Every
condition with a threshold is driven one step below, at and one step above its configured threshold, and the
outcome must agree with the relation the memo prints.
"""

from decimal import Decimal

import pytest

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.memo.rule_text import CHANGE, FIXED_TEXT, LEVEL, THRESHOLD_TEXT, condition_text
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis
from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.rules import RULE_FUNCTIONS
from credit_intel.risk.spec import RULE_SPECS

COMP = PeriodRole.COMPARATIVE
CONFIG = load_risk_rules()


def threshold(rule_id, condition_id):
    return CONFIG.rule(rule_id).condition(condition_id).threshold


def fires(rule_id, condition_id, current, comparative=None):
    records = [rec(n, str(v), role=CUR, end=D25) for n, v in current.items()]
    records += [rec(n, str(v), role=COMP, end=D24) for n, v in (comparative or {}).items()]
    field_set = FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ())
    rule = CONFIG.rule(rule_id)
    result = RULE_FUNCTIONS[rule_id](rule, field_set, calculate_metrics(field_set))
    outcome = next(c.outcome.value for c in result.conditions if c.condition_id == condition_id)
    assert outcome in ("fired", "not_fired"), f"{rule_id} {condition_id} was {outcome}"
    return outcome == "fired"


def at(rule_id, condition_id, step):
    """Drive the condition so its measured quantity is the threshold plus ``step`` (in its own unit), and report whether it fired."""
    t = threshold(rule_id, condition_id)
    x = t + Decimal(step)
    key = (rule_id, condition_id)
    if rule_id == "RI-001":  # growth in percent: revenue 1000 -> 1000 + 10 x
        return fires(rule_id, condition_id, {F.REVENUE: 1000 + 10 * x}, {F.REVENUE: 1000})
    if key == ("RI-002", "C1"):
        return fires(*key, {F.NET_PROFIT: x})
    if key == ("RI-003", "C1"):  # ratio x with current liabilities 100
        return fires(*key, {F.CURRENT_ASSETS: 100 * x, F.CURRENT_LIABILITIES: 100})
    if key == ("RI-003", "C2"):  # a fall of x percent from a ratio of 2
        return fires(*key, {F.CURRENT_ASSETS: 200 * (1 - x / 100), F.CURRENT_LIABILITIES: 100}, {F.CURRENT_ASSETS: 200, F.CURRENT_LIABILITIES: 100})
    if key == ("RI-004", "C1"):  # a rise of x percent from a ratio of 1
        return fires(*key, {F.TOTAL_BORROWINGS: 100 + x, F.TOTAL_EQUITY: 100}, {F.TOTAL_BORROWINGS: 100, F.TOTAL_EQUITY: 100})
    if key == ("RI-004", "C2"):  # ratio x with equity 100
        return fires(*key, {F.TOTAL_BORROWINGS: 100 * x, F.TOTAL_EQUITY: 100}, {F.TOTAL_BORROWINGS: 100, F.TOTAL_EQUITY: 100})
    if key == ("RI-004", "C3"):
        return fires(*key, {F.TOTAL_EQUITY: x}, {F.TOTAL_EQUITY: 100})
    if rule_id == "RI-005":  # coverage x with interest 100: EBIT = profit before tax + interest = 100 x
        return fires(rule_id, condition_id, {F.PROFIT_BEFORE_TAX: 100 * x - 100, F.INTEREST_EXPENSE: 100})
    raise AssertionError(key)


def expected(relation, step):
    return {"<": step < 0, "<=": step <= 0, ">": step > 0, ">=": step >= 0, "fell": step >= 0, "rose": step >= 0}[relation]


STEPS = ("-1", "-0.01", "0", "0.01", "1")


def test_every_condition_with_a_threshold_has_wording_and_every_other_has_a_fixed_sentence():
    with_threshold = {(r.id, c.id) for r in RULE_SPECS.values() for c in r.conditions if c.takes_threshold}
    without = {(r.id, c.id) for r in RULE_SPECS.values() for c in r.conditions if not c.takes_threshold}

    assert set(THRESHOLD_TEXT) == with_threshold and set(FIXED_TEXT) == without


def test_every_relation_used_is_a_known_one():
    assert {relation for _, relation, _ in THRESHOLD_TEXT.values()} <= {*LEVEL, *CHANGE}


@pytest.mark.parametrize(("key", "entry"), sorted(THRESHOLD_TEXT.items()))
@pytest.mark.parametrize("step", STEPS)
def test_the_printed_relation_agrees_with_what_the_rule_does_at_below_and_above_the_threshold(key, entry, step):
    rule_id, condition_id = key
    _, relation, _ = entry

    assert at(rule_id, condition_id, step) is expected(relation, Decimal(step)), (key, relation, step)


@pytest.mark.parametrize(
    ("rule_id", "condition_id", "value", "text"),
    [
        ("RI-001", "C1", "0", "revenue growth < 0%"),
        ("RI-001", "C2", "-10", "revenue growth <= -10%"),
        ("RI-003", "C1", "1.00", "current ratio of the current period < 1.00"),
        ("RI-003", "C2", "10", "current ratio fell by at least 10% relative to the comparative period"),
        ("RI-004", "C1", "20", "debt-to-equity ratio rose by at least 20% relative to the comparative period"),
        ("RI-004", "C2", "2.00", "debt-to-equity ratio of the current period > 2.00"),
        ("RI-004", "C3", "0", "total equity in either period <= 0"),
        ("RI-005", "C1", "1.50", "interest coverage ratio of the current period < 1.50"),
    ],
)
def test_the_wording_puts_the_threshold_into_the_sentence(rule_id, condition_id, value, text):
    assert condition_text(rule_id, condition_id, value) == text


def test_conditions_without_a_threshold_use_their_fixed_sentence_and_an_unknown_one_is_named():
    assert condition_text("RI-007", "C1", None) == FIXED_TEXT[("RI-007", "C1")]
    assert condition_text("RI-009", "C1", "1") == "condition C1"


@pytest.mark.parametrize(("key", "entry"), sorted((k, v) for k, v in THRESHOLD_TEXT.items() if v[1] in CHANGE))
def test_a_change_in_the_opposite_direction_does_not_fire_the_condition_the_memo_calls_a_fall_or_a_rise(key, entry):
    rule_id, condition_id = key
    t = threshold(rule_id, condition_id)
    if entry[1] == "fell":  # the ratio rises by t percent instead
        opposite = fires(*key, {F.CURRENT_ASSETS: 200 * (1 + t / 100), F.CURRENT_LIABILITIES: 100}, {F.CURRENT_ASSETS: 200, F.CURRENT_LIABILITIES: 100})
    else:  # the ratio falls by t percent instead
        opposite = fires(*key, {F.TOTAL_BORROWINGS: 100 - t, F.TOTAL_EQUITY: 100}, {F.TOTAL_BORROWINGS: 100, F.TOTAL_EQUITY: 100})

    assert opposite is False
