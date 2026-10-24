"""Evaluating all the rules of a run (PRD FR-008, J.1, J.2, J.5; Phase 4 step 4f).

``evaluate_rules`` runs every enabled rule over the run's field set and metric set and returns a
``RuleSet``: the rules' results in the file's order, the IDs of the rules that were switched off
(listed, not hidden), and the provisional-thresholds notice that the memo must print wherever
thresholds are shown (J.2). There is no overall score, rating, grade, approval or rejection (J.5):
the result is a list of explainable indicators, each a prompt for a human to look.
"""

from dataclasses import dataclass

from credit_intel.calculations.calculate import MetricSet
from credit_intel.extraction.field_set import FieldSet
from credit_intel.risk.config import RiskRulesConfig, load_risk_rules
from credit_intel.risk.results import RuleOutcome, RuleResult
from credit_intel.risk.rules import RULE_FUNCTIONS


@dataclass(frozen=True)
class RuleSet:
    provisional_notice: str
    results: tuple[RuleResult, ...]  # the enabled rules, in the file's order
    disabled: tuple[str, ...]  # the rules switched off in the file

    def get(self, rule_id: str) -> RuleResult:
        return next(result for result in self.results if result.rule_id == rule_id)

    @property
    def triggered(self) -> tuple[RuleResult, ...]:
        return tuple(r for r in self.results if r.outcome is RuleOutcome.TRIGGERED)


def evaluate_rules(field_set: FieldSet, metrics: MetricSet, config: RiskRulesConfig | None = None) -> RuleSet:
    config = config or load_risk_rules()
    results = []
    for rule in config.rules:
        if not rule.enabled:
            continue
        function = RULE_FUNCTIONS.get(rule.id)
        if function is None:
            raise ValueError(f"no implementation for rule {rule.id}")
        results.append(function(rule, field_set, metrics))
    return RuleSet(config.provisional_notice, tuple(results), tuple(r.id for r in config.rules if not r.enabled))
