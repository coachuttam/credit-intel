"""Condition results and the aggregation of a rule (PRD FR-008.2, FR-008.3, D-09, J.1, J.3, J.5; Phase 4 step 4b; B-248)."""

import dataclasses
import itertools
import random
from decimal import Decimal

import pytest

from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.results import (
    ConditionOutcome as C,
    ConditionResult,
    RuleOutcome as R,
    RuleResult,
    aggregate,
    condition_result,
)
from credit_intel.risk.spec import RULE_ORDER, Severity

CONFIG = load_risk_rules()
FIRED, NOT_FIRED, NOT_EVAL = C.FIRED, C.NOT_FIRED, C.NOT_EVALUABLE


def results(rule_id, *outcomes):
    """One condition result per outcome; an outcome may be ``(outcome, [missing inputs])``."""
    rule = CONFIG.rule(rule_id)
    built = []
    for condition, outcome in zip(rule.conditions, outcomes, strict=True):
        if isinstance(outcome, tuple):
            built.append(condition_result(condition, outcome[0], missing_inputs=outcome[1]))
        elif outcome is NOT_EVAL:
            built.append(condition_result(condition, outcome, missing_inputs=[f"input of {condition.id}"]))
        else:
            built.append(condition_result(condition, outcome))
    return rule, built


def run(rule_id, *outcomes):
    rule, built = results(rule_id, *outcomes)
    return aggregate(rule, built)


# --- the three worked examples of J.3 ------------------------------------------------------------------------------------------------


def test_j3_ri004_with_negative_equity_and_missing_borrowings_is_triggered_and_lists_what_was_missing():
    rule, built = results("RI-004", (NOT_EVAL, ["total_borrowings"]), (NOT_EVAL, ["total_borrowings"]), FIRED)

    result = aggregate(rule, built)

    assert result.outcome is R.TRIGGERED and result.severity is Severity.ELEVATED
    assert result.missing_inputs == ("total_borrowings",)  # listed once, from C1 and C2


def test_j3_ri003_with_a_ratio_of_0_84_and_no_comparative_period_is_triggered():
    result = run("RI-003", FIRED, NOT_EVAL)

    assert result.outcome is R.TRIGGERED and result.severity is Severity.ELEVATED  # C1 fired


def test_j3_ri003_with_a_ratio_of_1_20_and_no_comparative_period_is_not_evaluable_not_not_triggered():
    result = run("RI-003", NOT_FIRED, NOT_EVAL)

    assert result.outcome is R.NOT_EVALUABLE and result.severity is None
    assert result.missing_inputs == ("input of C2",)


# --- the rule of FR-008.2 ---------------------------------------------------------------------------------------------------------------


def test_any_fired_condition_triggers_the_rule_whatever_else_is_missing():
    assert run("RI-004", NOT_EVAL, NOT_EVAL, FIRED).outcome is R.TRIGGERED
    assert run("RI-004", FIRED, NOT_FIRED, NOT_EVAL).outcome is R.TRIGGERED


def test_not_triggered_only_if_every_condition_was_evaluable_and_none_fired():
    assert run("RI-004", NOT_FIRED, NOT_FIRED, NOT_FIRED).outcome is R.NOT_TRIGGERED
    assert run("RI-004", NOT_FIRED, NOT_FIRED, NOT_EVAL).outcome is R.NOT_EVALUABLE
    assert run("RI-006", NOT_FIRED).outcome is R.NOT_TRIGGERED


def test_a_rule_whose_conditions_cannot_all_be_evaluated_is_not_evaluable_and_lists_every_missing_input():
    rule, built = results("RI-003", (NOT_EVAL, ["current_ratio.2025-03-31"]), (NOT_EVAL, ["current_ratio.2024-03-31"]))

    result = aggregate(rule, built)

    assert result.outcome is R.NOT_EVALUABLE
    assert result.missing_inputs == ("current_ratio.2025-03-31", "current_ratio.2024-03-31")


def test_a_not_evaluable_rule_is_never_reported_as_not_triggered():
    for outcomes in itertools.product([FIRED, NOT_FIRED, NOT_EVAL], repeat=3):
        result = run("RI-004", *outcomes)
        if NOT_EVAL in outcomes and FIRED not in outcomes:
            assert result.outcome is R.NOT_EVALUABLE


def test_missing_inputs_of_a_rule_come_only_from_conditions_that_could_not_be_evaluated():
    rule, built = results("RI-004", FIRED, (NOT_EVAL, ["equity"]), NOT_FIRED)

    assert aggregate(rule, built).missing_inputs == ("equity",)
    assert aggregate(*results("RI-004", FIRED, NOT_FIRED, NOT_FIRED)).missing_inputs == ()


# --- severity ----------------------------------------------------------------------------------------------------------------------------


def test_the_severity_is_the_highest_among_the_conditions_that_fired():
    assert run("RI-001", FIRED, FIRED).severity is Severity.ELEVATED  # watch and elevated both fire
    assert run("RI-001", FIRED, NOT_FIRED).severity is Severity.WATCH
    assert run("RI-004", FIRED, NOT_FIRED, FIRED).severity is Severity.ELEVATED
    assert run("RI-006", FIRED).severity is Severity.INFO


def test_the_severity_of_a_condition_that_did_not_fire_does_not_count():
    result = run("RI-001", FIRED, NOT_FIRED)  # C2 is elevated in the file but did not fire

    assert result.severity is Severity.WATCH


def test_a_rule_that_is_not_triggered_has_no_severity():
    assert run("RI-004", NOT_FIRED, NOT_FIRED, NOT_FIRED).severity is None
    assert run("RI-004", NOT_FIRED, NOT_FIRED, NOT_EVAL).severity is None


def test_a_rule_result_without_a_severity_cannot_be_triggered_and_vice_versa():
    base = dict(rule_id="RI-X", name="x", conditions=(), missing_inputs=())
    with pytest.raises(ValueError):
        RuleResult(outcome=R.TRIGGERED, severity=None, **base)
    with pytest.raises(ValueError):
        RuleResult(outcome=R.NOT_TRIGGERED, severity=Severity.WATCH, **base)


# --- what each result records (FR-008.2, FR-008.3) ----------------------------------------------------------------------------------------


def test_a_condition_result_carries_the_configured_threshold_and_severity():
    condition = CONFIG.rule("RI-003").condition("C1")

    result = condition_result(condition, FIRED, values_used=[("current_ratio", Decimal("0.84"))], field_ids=["current_assets.2025-03-31.consolidated"], metric_ids=["MET-03.2025-03-31"])

    assert result.threshold == Decimal("1.00") and result.severity is Severity.ELEVATED and result.condition_id == "C1"
    assert result.values_used == (("current_ratio", Decimal("0.84")),) and result.field_ids and result.metric_ids


def test_references_and_missing_inputs_are_listed_once_in_order():
    condition = CONFIG.rule("RI-004").condition("C1")

    result = condition_result(condition, NOT_EVAL, missing_inputs=["a", "b", "a"], field_ids=["f", "f"], metric_ids=["m", "n", "m"])

    assert result.missing_inputs == ("a", "b") and result.field_ids == ("f",) and result.metric_ids == ("m", "n")


def test_a_condition_lists_missing_inputs_exactly_when_it_is_not_evaluable():
    condition = CONFIG.rule("RI-004").condition("C1")
    with pytest.raises(ValueError):
        condition_result(condition, NOT_EVAL)  # nothing says what is missing
    with pytest.raises(ValueError):
        condition_result(condition, FIRED, missing_inputs=["x"])


def test_notes_and_caveats_are_carried_up_to_the_rule_once():
    rule = CONFIG.rule("RI-004")
    built = [
        condition_result(rule.conditions[0], NOT_FIRED, caveats=["borrowings_not_presented_assumption"], note="first"),
        condition_result(rule.conditions[1], FIRED, caveats=["borrowings_not_presented_assumption"]),
        condition_result(rule.conditions[2], NOT_FIRED, note="third"),
    ]

    result = aggregate(rule, built)

    assert result.caveats == ("borrowings_not_presented_assumption",) and result.notes == ("first", "third")


def test_the_conditions_of_the_rule_are_kept_in_order_with_their_outcomes():
    result = run("RI-004", NOT_FIRED, FIRED, NOT_EVAL)

    assert [(c.condition_id, c.outcome) for c in result.conditions] == [("C1", NOT_FIRED), ("C2", FIRED), ("C3", NOT_EVAL)]
    assert [c.condition_id for c in result.fired] == ["C2"]


def test_a_rule_is_aggregated_only_from_its_own_conditions_in_order():
    rule, built = results("RI-004", NOT_FIRED, FIRED, NOT_FIRED)
    with pytest.raises(ValueError):
        aggregate(rule, built[:2])
    with pytest.raises(ValueError):
        aggregate(rule, list(reversed(built)))
    with pytest.raises(ValueError):
        aggregate(CONFIG.rule("RI-003"), built)


# --- no score, no decision (J.5) ---------------------------------------------------------------------------------------------------------------


def test_no_result_type_has_a_score_rating_grade_or_decision_field():
    forbidden = ("score", "rating", "grade", "approve", "approval", "reject", "decision", "rank_total", "total")
    for cls in (ConditionResult, RuleResult):
        names = {f.name for f in dataclasses.fields(cls)}
        assert not [n for n in names if any(word in n for word in forbidden)], (cls.__name__, names)


def test_the_outcome_words_are_the_prds_three_and_nothing_like_a_decision():
    assert {o.value for o in R} == {"triggered", "not_triggered", "not_evaluable"}
    assert {o.value for o in C} == {"fired", "not_fired", "not_evaluable"}
    assert {s.value for s in Severity} == {"info", "watch", "elevated"}


# --- properties --------------------------------------------------------------------------------------------------------------------------------


def test_property_the_rule_result_follows_fr_008_2_for_every_combination_of_outcomes():
    for rule_id in RULE_ORDER:
        count = len(CONFIG.rule(rule_id).conditions)
        for outcomes in itertools.product([FIRED, NOT_FIRED, NOT_EVAL], repeat=count):
            result = run(rule_id, *outcomes)
            rule = CONFIG.rule(rule_id)
            if FIRED in outcomes:
                best = max(c.severity.rank for c, o in zip(rule.conditions, outcomes) if o is FIRED)
                assert result.outcome is R.TRIGGERED and result.severity.rank == best
            elif NOT_EVAL in outcomes:
                assert result.outcome is R.NOT_EVALUABLE and result.severity is None and result.missing_inputs
            else:
                assert result.outcome is R.NOT_TRIGGERED and result.severity is None and not result.missing_inputs


def test_property_the_outcome_does_not_depend_on_the_order_conditions_are_listed_in():
    rng = random.Random(90)
    for _ in range(200):
        rule_id = rng.choice(RULE_ORDER)
        rule = CONFIG.rule(rule_id)
        outcomes = [rng.choice([FIRED, NOT_FIRED, NOT_EVAL]) for _ in rule.conditions]
        rule, built = results(rule_id, *outcomes)
        forward = aggregate(rule, built)
        reordered = RuleResult(rule.id, rule.name, forward.outcome, forward.severity, tuple(reversed(built)), forward.missing_inputs)
        assert (reordered.outcome, reordered.severity) == (forward.outcome, forward.severity)
        assert run(rule_id, *outcomes) == forward  # and aggregation is deterministic
