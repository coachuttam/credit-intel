"""The Release 1 rules (PRD J.3): RI-001 to RI-007 (Phase 4 steps 4c to 4e).

Each rule is a small named function. It reads the verified field set and the metric set, evaluates
each of its conditions on its own (a condition that cannot be evaluated lists exactly what it
lacked and why), and lets ``aggregate`` make the rule (FR-008.2). The comparison operator of a
condition is fixed here; the file supplies only the threshold, the severity and the on/off switch.

A metric or field is usable only when it has a value. A missing input is named as
``<reference> (<reason>)``, for example ``MET-03.2024-03-31 (missing_input)``. Nothing is
estimated, and nothing is added up across conditions or rules.
"""

from collections.abc import Callable, Sequence
from decimal import Decimal

from credit_intel.calculations.borrowings import total_borrowings_for
from credit_intel.calculations.calculate import Comparison, MetricSet
from credit_intel.calculations.metrics import MetricReason, MetricResult
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import ExtractedField, FieldName, Origin, PeriodRole, Status
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


def _comparison_condition(
    condition: ConditionConfig,
    names: tuple[str, str, str],
    current: MetricResult,
    comparative: MetricResult,
    comparison: Comparison,
    fires: Callable[[Decimal], bool],
) -> ConditionResult:
    """A condition on the change of a metric between the periods: it needs both results and a usable base.

    ``names`` are the labels of the current value, the comparative value and the relative change.
    """
    caveats = _caveats(current, comparative)
    if comparison.relative_change is None:
        missing = [_missing_metric(r, role) for r, role in ((current, PeriodRole.CURRENT), (comparative, PeriodRole.COMPARATIVE)) if r.value is None]
        reason = comparison.undefined_reason.value if comparison.undefined_reason else "undefined"
        return condition_result(condition, NOT_EVALUABLE, missing_inputs=missing or [f"{current.metric_id} comparison ({reason})"], caveats=caveats)
    return condition_result(
        condition, FIRED if fires(comparison.relative_change) else NOT_FIRED,
        values_used=[(names[0], current.value), (names[1], comparative.value), (names[2], comparison.relative_change)],
        field_ids=[*_supporting_fields(current), *_supporting_fields(comparative)],
        metric_ids=[metric_ref(current), metric_ref(comparative)], caveats=caveats,
    )  # fmt: skip


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

    results.append(_comparison_condition(
        c2, ("current_ratio_current", "current_ratio_comparative", "relative_change_percent"), current, comparative, comparison,
        lambda change: change <= -c2.threshold,
    ))  # fmt: skip
    return aggregate(rule, results)


# --- RI-004 Increasing leverage ---------------------------------------------------------------------------------------------------------------


def increasing_leverage(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires when debt-to-equity (MET-04) rose by at least its threshold (percent) relative to the
    comparative period; C2 when the current period's ratio is above its threshold; C3 when equity in either
    period is at or below its threshold. The borrowings caveat travels with MET-04 into C1, C2 and the rule."""
    current = metrics.get("MET-04", PeriodRole.CURRENT)
    comparative = metrics.get("MET-04", PeriodRole.COMPARATIVE)
    c1, c2, c3 = rule.condition("C1"), rule.condition("C2"), rule.condition("C3")

    first = _comparison_condition(
        c1, ("debt_to_equity_current", "debt_to_equity_comparative", "relative_change_percent"), current, comparative,
        metrics.comparison("MET-04"), lambda change: change >= c1.threshold,
    )  # fmt: skip

    if current.value is None:
        second = condition_result(c2, NOT_EVALUABLE, missing_inputs=[_missing_metric(current, PeriodRole.CURRENT)], caveats=_caveats(current))
    else:
        second = condition_result(c2, FIRED if current.value > c2.threshold else NOT_FIRED, values_used=[("debt_to_equity_current", current.value)],
                                  field_ids=_supporting_fields(current), metric_ids=[metric_ref(current)], caveats=_caveats(current))  # fmt: skip

    return aggregate(rule, [first, second, _equity_condition(c3, field_set)])


def _equity_condition(condition: ConditionConfig, field_set: FieldSet) -> ConditionResult:
    """Fires if any period whose equity is ``extracted`` has it at or below the threshold; ``not_fired`` only if
    both periods' equity is ``extracted`` and above it; otherwise not evaluable (the PRD's rule for C3)."""
    records = {role: field_set.get(FieldName.TOTAL_EQUITY, role) for role in (PeriodRole.CURRENT, PeriodRole.COMPARATIVE)}
    usable = {role: r for role, r in records.items() if r is not None and r.status is Status.EXTRACTED}
    low = [r for r in usable.values() if r.value <= condition.threshold]
    values = [(f"total_equity_{role.value}", r.value) for role, r in usable.items()]
    fields = [r.field_id for r in usable.values()]
    if low:
        return condition_result(condition, FIRED, values_used=values, field_ids=fields, note="negative or zero equity")
    missing = [_missing_field(FieldName.TOTAL_EQUITY, role, records[role]) for role in records if role not in usable]
    if missing:
        return condition_result(condition, NOT_EVALUABLE, missing_inputs=missing)
    return condition_result(condition, NOT_FIRED, values_used=values, field_ids=fields)


# --- RI-005 Weak interest coverage --------------------------------------------------------------------------------------------------------------


def weak_interest_coverage(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires when the current period's interest coverage (MET-05) is below its threshold, C2 when it is below
    the lower one (a negative ratio included). With no interest expense (``not_applicable_no_interest``) neither
    fires and a note says why; any other undefined result makes both conditions not evaluable."""
    coverage = metrics.get("MET-05", PeriodRole.CURRENT)
    if coverage.undefined_reason is MetricReason.NOT_APPLICABLE_NO_INTEREST:
        note = "interest coverage is not applicable: no interest expense in the period"
        return aggregate(rule, [
            condition_result(c, NOT_FIRED, field_ids=_supporting_fields(coverage), metric_ids=[metric_ref(coverage)], note=note)
            for c in rule.conditions
        ])  # fmt: skip
    if coverage.value is None:
        return aggregate(rule, _all_not_evaluable(rule, [_missing_metric(coverage, PeriodRole.CURRENT)]))
    seen = dict(values_used=[("interest_coverage_current", coverage.value)], field_ids=_supporting_fields(coverage), metric_ids=[metric_ref(coverage)])
    return aggregate(rule, [
        condition_result(c, FIRED if coverage.value < c.threshold else NOT_FIRED, **seen) for c in rule.conditions
    ])  # fmt: skip


# --- RI-006 Missing financial information -----------------------------------------------------------------------------------------------------

# What MET-01 to MET-05 read, in metric order. Total borrowings and EBIT are taken after the H.5 methods: a total derived
# from components, or an EBIT derived from profit before tax and interest, counts as present, and an absent optional
# operating profit is not counted when its derived alternative is available.
_SOURCE_INPUTS = (FieldName.REVENUE, FieldName.NET_PROFIT, FieldName.CURRENT_ASSETS, FieldName.CURRENT_LIABILITIES)


def _is_absent(record: ExtractedField | None) -> bool:
    return record is None or record.status is Status.NOT_FOUND


def missing_financial_information(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires if any input the five metrics need is ``not_found`` in either period, after the H.5 methods.
    It is always evaluable. A field that was found but needs review is not missing (RI-007 reports it)."""
    condition = rule.condition("C1")
    ebit = {r.period_role: r for r in metrics.derived}
    absent: list[tuple[str, str]] = []  # (field name, reference)
    for role in (PeriodRole.CURRENT, PeriodRole.COMPARATIVE):
        inputs: list[tuple[FieldName, ExtractedField | None]] = [(name, field_set.get(name, role)) for name in _SOURCE_INPUTS]
        inputs += [
            (FieldName.TOTAL_BORROWINGS, total_borrowings_for(field_set, role)),
            (FieldName.TOTAL_EQUITY, field_set.get(FieldName.TOTAL_EQUITY, role)),
            (FieldName.EBIT, ebit.get(role)),
            (FieldName.INTEREST_EXPENSE, field_set.get(FieldName.INTEREST_EXPENSE, role)),
        ]
        absent += [(name.value, f"{name.value}.{role.value}" if record is None else record.field_id) for name, record in inputs if _is_absent(record)]
    if not absent:
        return aggregate(rule, [condition_result(condition, NOT_FIRED, values_used=[("inputs_not_found", Decimal(0))])])
    return aggregate(rule, [condition_result(
        condition, FIRED, values_used=[("inputs_not_found", Decimal(len(absent)))], field_ids=[ref for _, ref in absent],
        note="not found: " + ", ".join(ref for _, ref in absent),
    )])  # fmt: skip


# --- RI-007 Conflicting or unverified source values --------------------------------------------------------------------------------------------


def unverified_source_values(rule: RuleConfig, field_set: FieldSet, metrics: MetricSet) -> RuleResult:
    """C1 fires if any source field of the run is ``conflicting`` or ``requires_review``, whether or not a metric
    reads it. Derived values and fields of another basis are not counted. It is always evaluable."""
    condition = rule.condition("C1")
    flagged = [r for r in field_set.fields if r.origin is Origin.SOURCE and r.status in (Status.CONFLICTING, Status.REQUIRES_REVIEW)]
    conflicting = sum(1 for r in flagged if r.status is Status.CONFLICTING)
    values = [("fields_conflicting", Decimal(conflicting)), ("fields_requires_review", Decimal(len(flagged) - conflicting))]
    if not flagged:
        return aggregate(rule, [condition_result(condition, NOT_FIRED, values_used=values)])
    def why(r: ExtractedField) -> str:
        return f"{r.field_id} ({r.status.value}" + (f": {r.status_reason.value})" if r.status_reason else ")")
    return aggregate(rule, [condition_result(
        condition, FIRED, values_used=values, field_ids=[r.field_id for r in flagged], note="; ".join(why(r) for r in flagged),
    )])  # fmt: skip


RULE_FUNCTIONS = {
    "RI-001": declining_revenue,
    "RI-002": negative_net_profit,
    "RI-003": deteriorating_liquidity,
    "RI-004": increasing_leverage,
    "RI-005": weak_interest_coverage,
    "RI-006": missing_financial_information,
    "RI-007": unverified_source_values,
}
