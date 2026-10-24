"""What the seven Release 1 rules are made of (PRD J.3). The code owns the logic; the file owns the numbers.

For each rule this lists its conditions and whether a condition takes a threshold. The comparison
operator of a condition is fixed in the code that evaluates it (``<``, ``<=``, ``>``, ``>=``), so
a configuration file supplies "1.00", never "<" (J.1: configuration supplies parameters, not code).
"""

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """How urgently a human should look. Not creditworthiness (J.1)."""

    INFO = "info"
    WATCH = "watch"
    ELEVATED = "elevated"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Severity.INFO: 0, Severity.WATCH: 1, Severity.ELEVATED: 2}


@dataclass(frozen=True)
class ConditionSpec:
    id: str
    takes_threshold: bool


@dataclass(frozen=True)
class RuleSpec:
    id: str
    conditions: tuple[ConditionSpec, ...]

    def condition(self, condition_id: str) -> ConditionSpec | None:
        return next((c for c in self.conditions if c.id == condition_id), None)


def _rule(rule_id: str, *conditions: tuple[str, bool]) -> RuleSpec:
    return RuleSpec(rule_id, tuple(ConditionSpec(cid, takes) for cid, takes in conditions))


# J.3. RI-006 and RI-007 take no threshold: they look at statuses.
RULE_SPECS: dict[str, RuleSpec] = {
    spec.id: spec
    for spec in (
        _rule("RI-001", ("C1", True), ("C2", True)),
        _rule("RI-002", ("C1", True)),
        _rule("RI-003", ("C1", True), ("C2", True)),
        _rule("RI-004", ("C1", True), ("C2", True), ("C3", True)),
        _rule("RI-005", ("C1", True), ("C2", True)),
        _rule("RI-006", ("C1", False)),
        _rule("RI-007", ("C1", False)),
    )
}
RULE_ORDER: tuple[str, ...] = tuple(RULE_SPECS)
