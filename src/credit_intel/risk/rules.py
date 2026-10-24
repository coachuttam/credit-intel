"""The Release 1 rules (PRD J.3): RI-001, RI-002 and RI-003 so far (Phase 4 step 4c).

Each rule is a small named function. It reads the verified field set and the metric set, evaluates
each of its conditions on its own (a condition that cannot be evaluated lists exactly what it
lacked and why), and lets ``aggregate`` make the rule (FR-008.2). The comparison operator of a
condition is fixed here; the file supplies only the threshold, the severity and the on/off switch.

A metric or field is usable only when it has a value. A missing input is named as
``<reference> (<reason>)``, for example ``MET-03.2024-03-31 (missing_input)``. Nothing is
estimated, and nothing is added up across conditions or rules.
"""

from collections.abc import Sequence
from decimal import Decimal

from credit_intel.calculations.calculate import MetricSet
from credit_intel.calculations.metrics import MetricResult
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import ExtractedField, FieldName, PeriodRole, Status
from credit_intel.risk.config import ConditionConfig, RuleConfig
from credit_intel.risk.results import ConditionOutcome, ConditionResult, RuleResult, aggregate, condition_result

FIRED, NOT_FIRED, NOT_EVALUABLE = ConditionOutcome.FIRED, ConditionOutcome.NOT_FIRED, ConditionOutcome.NOT_EVALUABLE


# --- reading the inputs ---------------------------------------------------------------------------------------------------------------------


def metric_ref(result: MetricResult, role: PeriodRole | None = None) -> str:
    """A reference to a metric result, with its period end when it has one (``MET-03.2025-03-31``)."""
    if result.period_ends:
        return f"{result.metric_id}.{result.period_ends[0].isoformat()}"
    return result.metric_id if role is None else f"{result.metric_id}.{role.value}"


def _missing_metric(result: MetricResult, role: PeriodRole | None = None) -> str:
    return f"{metric_ref(result, role)} ({result.undefined_reason.value})"


def _supporting_fields(result: MetricResult) -> list[str]:
    """The field IDs of the inputs that had a value."""
    return [field_id for field_id, value in zip(result.input_field_ids, result.input_values, strict=True) if value is not None]


def _missing_field(name: FieldName, role: PeriodRole, record: ExtractedField | None) -> str:
    status = Status.NOT_FOUND if record is None else record.status
    where = role.value if record is None else record.period_end.isoformat()
    return f"{name.value}.{where} ({status.value})"


def _caveats(*results: MetricResult) -> list[str]:
    return [caveat for result in results for caveat in result.caveats]


def _all_not_evaluable(rule: RuleConfig, missing: Sequence[str]) -> list[ConditionResult]:
    return [condition_result(c, NOT_EVALUABLE, missing_inputs=missing) for c in rule.conditions]


# --- RI-001 Declining revenue ---------------------------------------------------------------------------------------------------------------


def declining_revenue(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires when revenue growth (MET-01) is below its threshold; C2 when it is at or below its threshold."""
    growth = metrics.get("MET-01")
    if growth.value is None:
        return aggregate(rule, _all_not_evaluable(rule, [_missing_metric(growth)]))
    seen = dict(values_used=[("revenue_growth_percent", growth.value)], field_ids=_supporting_fields(growth), metric_ids=[metric_ref(growth)])
    c1, c2 = rule.condition("C1"), rule.condition("C2")
    return aggregate(rule, [
        condition_result(c1, FIRED if growth.value < c1.threshold else NOT_FIRED, **seen),
        condition_result(c2, FIRED if growth.value <= c2.threshold else NOT_FIRED, **seen),
    ])  # fmt: skip


# --- RI-002 Negative net profit -----------------------------------------------------------------------------------------------------------


def negative_net_profit(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires when the current period's net profit is below its threshold."""
    record = field_set.get(FieldName.NET_PROFIT, PeriodRole.CURRENT)
    condition = rule.condition("C1")
    if record is None or record.status is not Status.EXTRACTED:
        return aggregate(rule, _all_not_evaluable(rule, [_missing_field(FieldName.NET_PROFIT, PeriodRole.CURRENT, record)]))
    outcome = FIRED if record.value < condition.threshold else NOT_FIRED
    return aggregate(rule, [condition_result(condition, outcome, values_used=[("net_profit", record.value)], field_ids=[record.field_id])])


# --- RI-003 Deteriorating liquidity -------------------------------------------------------------------------------------------------------


def deteriorating_liquidity(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires when the current ratio (MET-03) of the current period is below its threshold;
    C2 when it fell by at least its threshold (percent) relative to the comparative period."""
    current = metrics.get("MET-03", PeriodRole.CURRENT)
    comparative = metrics.get("MET-03", PeriodRole.COMPARATIVE)
    comparison = metrics.comparison("MET-03")
    c1, c2 = rule.condition("C1"), rule.condition("C2")
    results = []

    if current.value is None:
        results.append(condition_result(c1, NOT_EVALUABLE, missing_inputs=[_missing_metric(current, PeriodRole.CURRENT)]))
    else:
        outcome = FIRED if current.value < c1.threshold else NOT_FIRED
        results.append(condition_result(c1, outcome, values_used=[("current_ratio_current", current.value)],
                                        field_ids=_supporting_fields(current), metric_ids=[metric_ref(current)]))  # fmt: skip

    if comparison.relative_change is None:
        missing = [_missing_metric(r, role) for r, role in ((current, PeriodRole.CURRENT), (comparative, PeriodRole.COMPARATIVE)) if r.value is None]
        results.append(condition_result(c2, NOT_EVALUABLE, missing_inputs=missing or [f"MET-03 comparison ({comparison.undefined_reason.value})"]))
    else:
        outcome = FIRED if comparison.relative_change <= -c2.threshold else NOT_FIRED
        results.append(condition_result(
            c2, outcome,
            values_used=[("current_ratio_current", current.value), ("current_ratio_comparative", comparative.value), ("relative_change_percent", comparison.relative_change)],
            field_ids=[*_supporting_fields(current), *_supporting_fields(comparative)], metric_ids=[metric_ref(current), metric_ref(comparative)],
        ))  # fmt: skip
    return aggregate(rule, results)


RULE_FUNCTIONS = {
    "RI-001": declining_revenue,
    "RI-002": negative_net_profit,
    "RI-003": deteriorating_liquidity,
}
