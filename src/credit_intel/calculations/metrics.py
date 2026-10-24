"""Financial metrics (PRD Section I; Phase 3 steps 3c to 3e): MET-01 and MET-02 so far.

Every metric is a pure function of verified field records. It returns a ``MetricResult``: a
value, or an explicit undefined reason, never both and never a guess (I.1). Arithmetic is
``Decimal`` in a fixed context, so a result does not depend on the caller's global context.

Inputs must be ``extracted`` (a missing record counts as ``not_found``). Where several
inputs are not, the first reason by this precedence applies: ``missing_input``, then
``input_conflicting``, then ``input_requires_review``. Then the inputs must share a
currency (``currency_mismatch``), and for a growth metric the two periods must be consecutive
(``period_mismatch``). Only then do the metric's own edge cases apply.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal
from enum import StrEnum

from credit_intel.extraction.periods import periods_are_consecutive
from credit_intel.models import ExtractedField, FieldName, PeriodRole, Status

# One fixed context for every metric: 28 significant digits, ties to even. Display rounding
# belongs to the memo (Phase 5), not here.
CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
HUNDRED = Decimal(100)


class MetricReason(StrEnum):
    """Why a metric is undefined (PRD I.1)."""

    MISSING_INPUT = "missing_input"
    INPUT_CONFLICTING = "input_conflicting"
    INPUT_REQUIRES_REVIEW = "input_requires_review"
    ZERO_DENOMINATOR = "zero_denominator"
    NON_POSITIVE_BASE = "non_positive_base"
    NOT_MEANINGFUL_NEGATIVE_EQUITY = "not_meaningful_negative_equity"
    NOT_APPLICABLE_NO_INTEREST = "not_applicable_no_interest"
    CURRENCY_MISMATCH = "currency_mismatch"
    PERIOD_MISMATCH = "period_mismatch"


class Unit(StrEnum):
    PERCENT = "percent"
    RATIO = "ratio"


@dataclass(frozen=True)
class MetricResult:
    """One metric for one pair or period (FR-007.2): value or reason, with its inputs."""

    metric_id: str
    name: str
    unit: Unit
    formula: str
    value: Decimal | None
    undefined_reason: MetricReason | None
    input_field_ids: tuple[str, ...]
    input_values: tuple[Decimal | None, ...]
    period_ends: tuple[date, ...]

    def __post_init__(self) -> None:
        if (self.value is None) == (self.undefined_reason is None):
            raise ValueError("a metric result has a value or an undefined reason, never both or neither")
        if self.value is not None and not isinstance(self.value, Decimal):
            raise TypeError("a metric value is a Decimal")

    @property
    def defined(self) -> bool:
        return self.value is not None


_INPUT_REASON = {
    Status.NOT_FOUND: MetricReason.MISSING_INPUT,
    Status.CONFLICTING: MetricReason.INPUT_CONFLICTING,
    Status.REQUIRES_REVIEW: MetricReason.INPUT_REQUIRES_REVIEW,
}
_PRECEDENCE = (MetricReason.MISSING_INPUT, MetricReason.INPUT_CONFLICTING, MetricReason.INPUT_REQUIRES_REVIEW)


def _result(metric_id, name, unit, formula, expected, records, value=None, reason=None) -> MetricResult:
    """``expected`` are the field names and periods the metric reads, aligned with ``records``."""
    ids, values, ends = [], [], []
    for (field, period_end), record in zip(expected, records, strict=True):
        if record is not None:
            ids.append(record.field_id)
        else:  # no record: name the field, and its period if it is known
            ids.append(field.value if period_end is None else f"{field.value}.{period_end.isoformat()}")
        values.append(record.value if record is not None else None)
        if period_end is not None:
            ends.append(period_end)
    return MetricResult(metric_id, name, unit, formula, value, reason, tuple(ids), tuple(values), tuple(dict.fromkeys(ends)))


def _input_reason(records: Sequence[ExtractedField | None]) -> MetricReason | None:
    """The reason the inputs are unusable by status, in the fixed precedence, or ``None``."""
    found = {
        _INPUT_REASON[record.status if record is not None else Status.NOT_FOUND]
        for record in records
        if record is None or record.status is not Status.EXTRACTED
    }
    return next((reason for reason in _PRECEDENCE if reason in found), None)


def _check_same_basis(records: Sequence[ExtractedField | None]) -> None:
    present = [record for record in records if record is not None]
    if len({record.statement_basis for record in present}) > 1:
        raise ValueError("a metric uses inputs of one basis")


def revenue_growth(revenue_current: ExtractedField | None, revenue_comparative: ExtractedField | None) -> MetricResult:
    """MET-01: (current - comparative) / comparative x 100, in percent."""
    records = (revenue_current, revenue_comparative)
    for record, role in zip(records, (PeriodRole.CURRENT, PeriodRole.COMPARATIVE), strict=True):
        if record is not None and record.period_role is not role:
            raise ValueError("revenue growth takes the current period first and the comparative period second")
    _check_same_basis(records)
    ends = [(FieldName.REVENUE, r.period_end if r is not None else None) for r in records]
    args = ("MET-01", "Revenue growth", Unit.PERCENT, "(revenue_current - revenue_comparative) / revenue_comparative x 100", ends, records)

    reason = _input_reason(records)
    if reason is None:
        current, comparative = records
        if current.currency != comparative.currency:
            reason = MetricReason.CURRENCY_MISMATCH
        elif not periods_are_consecutive(current.period_end, comparative.period_end):
            reason = MetricReason.PERIOD_MISMATCH
        elif comparative.value == 0:
            reason = MetricReason.ZERO_DENOMINATOR
        elif comparative.value < 0:
            reason = MetricReason.NON_POSITIVE_BASE
        elif current.value < 0:  # defensive: FR-006.5 already makes a negative revenue requires_review
            reason = MetricReason.INPUT_REQUIRES_REVIEW
    if reason is not None:
        return _result(*args, reason=reason)
    change = CONTEXT.divide(CONTEXT.subtract(current.value, comparative.value), comparative.value)
    return _result(*args, value=CONTEXT.multiply(change, HUNDRED))


def net_profit_margin(net_profit: ExtractedField | None, revenue: ExtractedField | None) -> MetricResult:
    """MET-02: net_profit / revenue x 100, in percent, for one period."""
    records = (net_profit, revenue)
    _check_same_basis(records)
    present = [r for r in records if r is not None]
    if len({r.period_role for r in present}) > 1:
        raise ValueError("a margin uses inputs of one period role")
    end = present[0].period_end if present else None
    expected = [(FieldName.NET_PROFIT, end), (FieldName.REVENUE, end)]
    args = ("MET-02", "Net profit margin", Unit.PERCENT, "net_profit / revenue x 100", expected, records)

    reason = _input_reason(records)
    if reason is None:
        if net_profit.currency != revenue.currency:
            reason = MetricReason.CURRENCY_MISMATCH
        elif net_profit.period_end != revenue.period_end:
            reason = MetricReason.PERIOD_MISMATCH
        elif revenue.value == 0:
            reason = MetricReason.ZERO_DENOMINATOR
        elif revenue.value < 0:  # defensive: FR-006.5 already makes a negative revenue requires_review
            reason = MetricReason.NON_POSITIVE_BASE
    if reason is not None:
        return _result(*args, reason=reason)
    return _result(*args, value=CONTEXT.multiply(CONTEXT.divide(net_profit.value, revenue.value), HUNDRED))
