"""All five metrics for both periods from a run's field set, and the period comparison (PRD I.1, I.3; Phase 3 step 3e).

``calculate_metrics`` reads only the field set's records of the configured basis (fields of another
basis were set aside by the run and are never used). It derives EBIT for each period (H.5), then
computes MET-01 once and MET-02 to MET-05 for the current and the comparative period. Nothing is
estimated: an input that is missing or not ``extracted`` makes the metric undefined with a reason.

A comparison (I.3) is the relative change of a metric between the two periods, in percent. It is
defined only if both periods' results are, and a zero or negative comparative base is undefined
too. The risk rules of Phase 4 apply their own thresholds to these.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from credit_intel.calculations.borrowings import total_borrowings_for
from credit_intel.calculations.derived import derive_ebit_for
from credit_intel.calculations.metrics import (
    CONTEXT,
    HUNDRED,
    MetricReason,
    MetricResult,
    current_ratio,
    debt_to_equity,
    interest_coverage,
    net_profit_margin,
    revenue_growth,
)
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import ExtractedField, FieldName, PeriodRole, StatementBasis

CURRENT, COMPARATIVE = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
PERIODIC = ("MET-02", "MET-03", "MET-04", "MET-05")  # computed per period; MET-01 spans both


@dataclass(frozen=True)
class Comparison:
    """The change of one metric from the comparative period to the current one (I.3)."""

    metric_id: str
    current: MetricResult
    comparative: MetricResult
    relative_change: Decimal | None  # percent: (current - comparative) / comparative x 100
    undefined_reason: MetricReason | None
    caveats: tuple[str, ...] = ()  # the caveats of either result (PRD v0.4.23)

    def __post_init__(self) -> None:
        if (self.relative_change is None) == (self.undefined_reason is None):
            raise ValueError("a comparison has a change or an undefined reason, never both or neither")


def compare(current: MetricResult, comparative: MetricResult) -> Comparison:
    """The relative change between two results of one metric, undefined if either is (I.3)."""
    if current.metric_id != comparative.metric_id:
        raise ValueError("a comparison uses two results of one metric")
    reason = current.undefined_reason or comparative.undefined_reason
    caveats = tuple(dict.fromkeys((*current.caveats, *comparative.caveats)))
    if reason is None:
        if comparative.value == 0:
            reason = MetricReason.ZERO_DENOMINATOR
        elif comparative.value < 0:
            reason = MetricReason.NON_POSITIVE_BASE
    if reason is not None:
        return Comparison(current.metric_id, current, comparative, None, reason, caveats)
    change = CONTEXT.divide(CONTEXT.subtract(current.value, comparative.value), comparative.value)
    return Comparison(current.metric_id, current, comparative, CONTEXT.multiply(change, HUNDRED), None, caveats)


@dataclass(frozen=True)
class MetricSet:
    """Every metric result of a run, the derived records they used, and the period comparisons."""

    configured_basis: StatementBasis
    derived: tuple[ExtractedField, ...]  # the EBIT records, current period first
    results: Mapping[tuple[str, PeriodRole | None], MetricResult]
    comparisons: Mapping[str, Comparison]

    def get(self, metric_id: str, role: PeriodRole | None = None) -> MetricResult:
        """MET-01 has no role; the others are asked for by period."""
        return self.results[(metric_id, role)]

    def comparison(self, metric_id: str) -> Comparison:
        return self.comparisons[metric_id]


def calculate_metrics(field_set: FieldSet) -> MetricSet:
    ebit = {role: derive_ebit_for(field_set, role) for role in (CURRENT, COMPARATIVE)}
    results: dict[tuple[str, PeriodRole | None], MetricResult] = {}

    def get(name: FieldName, role: PeriodRole) -> ExtractedField | None:
        return field_set.get(name, role)

    results[("MET-01", None)] = revenue_growth(get(FieldName.REVENUE, CURRENT), get(FieldName.REVENUE, COMPARATIVE))
    for role in (CURRENT, COMPARATIVE):
        results[("MET-02", role)] = net_profit_margin(get(FieldName.NET_PROFIT, role), get(FieldName.REVENUE, role))
        results[("MET-03", role)] = current_ratio(get(FieldName.CURRENT_ASSETS, role), get(FieldName.CURRENT_LIABILITIES, role))
        results[("MET-04", role)] = debt_to_equity(total_borrowings_for(field_set, role), get(FieldName.TOTAL_EQUITY, role))
        results[("MET-05", role)] = interest_coverage(ebit[role], get(FieldName.INTEREST_EXPENSE, role))

    comparisons = {m: compare(results[(m, CURRENT)], results[(m, COMPARATIVE)]) for m in PERIODIC}
    return MetricSet(
        configured_basis=field_set.configured_basis,
        derived=tuple(record for record in (ebit[CURRENT], ebit[COMPARATIVE]) if record is not None),
        results=MappingProxyType(results),
        comparisons=MappingProxyType(comparisons),
    )
