"""Loading ``config/risk_rules.toml`` (PRD FR-008.1, J.1, J.2; Phase 4 step 4a).

The file is read with the standard-library ``tomllib``, with every float read as an exact
``Decimal`` (``parse_float``), so a threshold never passes through a binary float. It is checked
against the rule specifications: the seven rules of J.3, each with exactly its conditions, a
valid severity, an ``enabled`` flag, and a threshold where the condition takes one and nowhere
else. A problem raises ``E-CONFIG-INVALID`` whose detail names the setting by position
(``rule[2].condition[0].threshold``), never its value. Changing a threshold needs no code change.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from credit_intel.config import _invalid
from credit_intel.ingestion.errors import IngestionError
from credit_intel.risk.spec import RULE_SPECS, Severity

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[3] / "config" / "risk_rules.toml"

_TOP_KEYS = {"provisional_notice", "rule"}
_RULE_KEYS = {"id", "name", "description", "enabled", "inputs", "condition"}
_CONDITION_KEYS = {"id", "severity", "threshold"}


@dataclass(frozen=True)
class ConditionConfig:
    id: str
    severity: Severity
    threshold: Decimal | None


@dataclass(frozen=True)
class RuleConfig:
    id: str
    name: str
    description: str
    enabled: bool
    inputs: tuple[str, ...]  # metric or field IDs the rule reads (documentation and references)
    conditions: tuple[ConditionConfig, ...]

    def condition(self, condition_id: str) -> ConditionConfig:
        return next(c for c in self.conditions if c.id == condition_id)


@dataclass(frozen=True)
class RiskRulesConfig:
    provisional_notice: str  # J.2: the memo states this wherever thresholds are shown
    rules: tuple[RuleConfig, ...]  # in the file's order

    def rule(self, rule_id: str) -> RuleConfig:
        return next(r for r in self.rules if r.id == rule_id)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(where)
    return value.strip()


def _threshold(value: object, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise _invalid(where)
    number = Decimal(value)
    if not number.is_finite():
        raise _invalid(where)
    return number


def _condition(table: object, where: str, rule_id: str) -> ConditionConfig:
    if not isinstance(table, dict):
        raise _invalid(where)
    for key in table:
        if key not in _CONDITION_KEYS:
            raise _invalid(f"{where}.{key}")
    condition_id = _text(table.get("id"), f"{where}.id")
    spec = RULE_SPECS[rule_id].condition(condition_id)
    if spec is None:
        raise _invalid(f"{where}.id")
    try:
        severity = Severity(table.get("severity"))
    except ValueError:
        raise _invalid(f"{where}.severity") from None
    if spec.takes_threshold:
        threshold = _threshold(table.get("threshold"), f"{where}.threshold")
    elif "threshold" in table:
        raise _invalid(f"{where}.threshold")
    else:
        threshold = None
    return ConditionConfig(condition_id, severity, threshold)


def _rule(table: object, index: int) -> RuleConfig:
    where = f"rule[{index}]"
    if not isinstance(table, dict):
        raise _invalid(where)
    for key in table:
        if key not in _RULE_KEYS:
            raise _invalid(f"{where}.{key}")
    rule_id = _text(table.get("id"), f"{where}.id")
    if rule_id not in RULE_SPECS:
        raise _invalid(f"{where}.id")
    enabled = table.get("enabled")
    if not isinstance(enabled, bool):
        raise _invalid(f"{where}.enabled")
    inputs = table.get("inputs")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(i, str) and i.strip() for i in inputs):
        raise _invalid(f"{where}.inputs")
    raw_conditions = table.get("condition")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise _invalid(f"{where}.condition")
    conditions = tuple(_condition(c, f"{where}.condition[{n}]", rule_id) for n, c in enumerate(raw_conditions))
    if [c.id for c in conditions] != [c.id for c in RULE_SPECS[rule_id].conditions]:
        raise _invalid(f"{where}.condition")  # exactly the rule's conditions, once each, in order
    return RuleConfig(
        id=rule_id,
        name=_text(table.get("name"), f"{where}.name"),
        description=_text(table.get("description"), f"{where}.description"),
        enabled=enabled,
        inputs=tuple(i.strip() for i in inputs),
        conditions=conditions,
    )


def load_risk_rules(path: Path = DEFAULT_RULES_PATH) -> RiskRulesConfig:
    """Read and validate the rules file. Raises ``IngestionError`` (``E-CONFIG-INVALID``)."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise _invalid("risk rules file") from None
    for key in data:
        if key not in _TOP_KEYS:
            raise _invalid(key)
    notice = _text(data.get("provisional_notice"), "provisional_notice")
    raw_rules = data.get("rule")
    if not isinstance(raw_rules, list):
        raise _invalid("rule")
    rules = tuple(_rule(table, n) for n, table in enumerate(raw_rules))
    ids = [r.id for r in rules]
    if len(set(ids)) != len(ids) or set(ids) != set(RULE_SPECS):
        raise _invalid("rule")  # each of the seven rules exactly once
    return RiskRulesConfig(provisional_notice=notice, rules=rules)
