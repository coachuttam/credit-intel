"""Condition and rule results, and how conditions make a rule (PRD FR-008.2, FR-008.3, D-09, J.1; Phase 4 step 4b).

Each condition of a rule is evaluated on its own. A condition is ``fired``, ``not_fired``, or
``not_evaluable`` (one of its own inputs is missing or unusable; it lists them). The rule's result:

- ``triggered`` if any evaluable condition fired, whatever else could not be evaluated;
- ``not_triggered`` only if every condition was evaluable and none fired;
- ``not_evaluable`` otherwise, listing the missing inputs. It is never reported as ``not_triggered``.

The rule's severity is the highest severity among the conditions that fired, and is present only
when the rule is triggered. Nothing here adds anything up: there is no score, rating, grade,
approval or rejection (J.5). An indicator is a prompt for a human to look, nothing more.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from credit_intel.risk.config import ConditionConfig, RuleConfig
from credit_intel.risk.spec import Severity


class ConditionOutcome(StrEnum):
    FIRED = "fired"
    NOT_FIRED = "not_fired"
    NOT_EVALUABLE = "not_evaluable"


class RuleOutcome(StrEnum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class ConditionResult:
    """One condition of one rule: what was applied, to which values, and what came out (FR-008.2, .3)."""

    condition_id: str
    outcome: ConditionOutcome
    severity: Severity  # the configured severity, applying if the condition fired
    threshold: Decimal | None
    values_used: tuple[tuple[str, Decimal], ...] = ()  # (name, value) pairs, as observed
    missing_inputs: tuple[str, ...] = ()  # only for a condition that is not evaluable
    field_ids: tuple[str, ...] = ()  # supporting field references
    metric_ids: tuple[str, ...] = ()  # supporting metric references
    note: str | None = None
    caveats: tuple[str, ...] = ()  # carried from the inputs, e.g. the borrowings caveat

    def __post_init__(self) -> None:
        if (self.outcome is ConditionOutcome.NOT_EVALUABLE) != bool(self.missing_inputs):
            raise ValueError("a condition lists missing inputs exactly when it is not evaluable")


@dataclass(frozen=True)
class RuleResult:
    """One rule: its result, severity if triggered, every condition's outcome, and what was missing."""

    rule_id: str
    name: str
    outcome: RuleOutcome
    severity: Severity | None
    conditions: tuple[ConditionResult, ...]
    missing_inputs: tuple[str, ...]  # of the conditions that could not be evaluated, in order
    notes: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.severity is not None) != (self.outcome is RuleOutcome.TRIGGERED):
            raise ValueError("a rule has a severity exactly when it is triggered")

    @property
    def fired(self) -> tuple[ConditionResult, ...]:
        return tuple(c for c in self.conditions if c.outcome is ConditionOutcome.FIRED)


def condition_result(
    config: ConditionConfig,
    outcome: ConditionOutcome,
    *,
    values_used: Sequence[tuple[str, Decimal]] = (),
    missing_inputs: Sequence[str] = (),
    field_ids: Sequence[str] = (),
    metric_ids: Sequence[str] = (),
    note: str | None = None,
    caveats: Sequence[str] = (),
) -> ConditionResult:
    """A condition's result carrying the severity and threshold the file configured for it."""
    return ConditionResult(
        condition_id=config.id,
        outcome=outcome,
        severity=config.severity,
        threshold=config.threshold,
        values_used=tuple(values_used),
        missing_inputs=tuple(dict.fromkeys(missing_inputs)),
        field_ids=tuple(dict.fromkeys(field_ids)),
        metric_ids=tuple(dict.fromkeys(metric_ids)),
        note=note,
        caveats=tuple(dict.fromkeys(caveats)),
    )


def aggregate(rule: RuleConfig, conditions: Sequence[ConditionResult]) -> RuleResult:
    """The rule's result from its conditions' results (FR-008.2, D-09)."""
    if [c.condition_id for c in conditions] != [c.id for c in rule.conditions]:
        raise ValueError("a rule is aggregated from exactly its own conditions, in order")
    fired = [c for c in conditions if c.outcome is ConditionOutcome.FIRED]
    unevaluable = [c for c in conditions if c.outcome is ConditionOutcome.NOT_EVALUABLE]
    missing = tuple(dict.fromkeys(item for c in unevaluable for item in c.missing_inputs))
    notes = tuple(c.note for c in conditions if c.note)
    caveats = tuple(dict.fromkeys(item for c in conditions for item in c.caveats))
    if fired:
        outcome: RuleOutcome = RuleOutcome.TRIGGERED
        severity: Severity | None = max((c.severity for c in fired), key=lambda s: s.rank)
    elif unevaluable:
        outcome, severity = RuleOutcome.NOT_EVALUABLE, None
    else:
        outcome, severity = RuleOutcome.NOT_TRIGGERED, None
    return RuleResult(rule.id, rule.name, outcome, severity, tuple(conditions), missing, notes, caveats)
