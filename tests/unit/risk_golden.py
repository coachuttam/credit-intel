"""Three fixed synthetic scenarios and the snapshot of their rule results for the Phase 4 golden test. Not a test module.

INR crore, no real document. Calm: every rule quiet. Stressed: falling revenue, a loss, thin liquidity, high and rising
leverage, weak interest coverage, and a missing comparative current-liabilities figure. Review: calm figures, but the
operating profit needs review.
"""

import json

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status, StatusReason as R
from credit_intel.risk.evaluate import RuleSet, evaluate_rules

COMP = PeriodRole.COMPARATIVE

CALM_CURRENT = {F.REVENUE: "1200", F.NET_PROFIT: "96", F.PROFIT_BEFORE_TAX: "150", F.INTEREST_EXPENSE: "30", F.CURRENT_ASSETS: "450",
                F.CURRENT_LIABILITIES: "300", F.BORROWINGS_NON_CURRENT: "500", F.BORROWINGS_CURRENT: "200", F.TOTAL_EQUITY: "800"}  # fmt: skip
CALM_COMPARATIVE = {F.REVENUE: "1000", F.NET_PROFIT: "100", F.PROFIT_BEFORE_TAX: "140", F.INTEREST_EXPENSE: "60", F.CURRENT_ASSETS: "360",
                    F.CURRENT_LIABILITIES: "300", F.BORROWINGS_NON_CURRENT: "400", F.BORROWINGS_CURRENT: "150", F.TOTAL_EQUITY: "700"}  # fmt: skip
STRESSED_CURRENT = {**CALM_CURRENT, F.REVENUE: "850", F.NET_PROFIT: "-20", F.PROFIT_BEFORE_TAX: "-50", F.INTEREST_EXPENSE: "80",
                    F.CURRENT_ASSETS: "270", F.BORROWINGS_NON_CURRENT: "900", F.BORROWINGS_CURRENT: "300", F.TOTAL_EQUITY: "480"}  # fmt: skip
STRESSED_COMPARATIVE = {k: v for k, v in CALM_COMPARATIVE.items() if k is not F.CURRENT_LIABILITIES}


def field_set(current, comparative, extra=()):
    records = [rec(n, v, role=CUR, end=D25) for n, v in current.items()]
    records += [rec(n, v, role=COMP, end=D24) for n, v in comparative.items()]
    records += list(extra)
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ("consolidated",))


def scenarios() -> dict[str, FieldSet]:
    review = rec(F.OPERATING_PROFIT, status=Status.REQUIRES_REVIEW, reason=R.LABEL_NOT_RECOGNISED, role=CUR, end=D25)
    return {
        "calm": field_set(CALM_CURRENT, CALM_COMPARATIVE),
        "stressed": field_set(STRESSED_CURRENT, STRESSED_COMPARATIVE),
        "review": field_set(CALM_CURRENT, CALM_COMPARATIVE, extra=[review]),
    }


def snapshot(rule_set: RuleSet) -> dict:
    text = lambda d: None if d is None else str(d)  # noqa: E731
    rules = []
    for r in rule_set.results:
        rules.append({
            "rule_id": r.rule_id, "name": r.name, "outcome": r.outcome.value, "severity": r.severity.value if r.severity else None,
            "missing_inputs": list(r.missing_inputs), "notes": list(r.notes), "caveats": list(r.caveats),
            "conditions": [
                {"id": c.condition_id, "outcome": c.outcome.value, "severity": c.severity.value, "threshold": text(c.threshold),
                 "values_used": [[n, text(v)] for n, v in c.values_used], "missing_inputs": list(c.missing_inputs),
                 "field_ids": list(c.field_ids), "metric_ids": list(c.metric_ids), "note": c.note, "caveats": list(c.caveats)}
                for c in r.conditions
            ],
        })  # fmt: skip
    return {"provisional_notice": rule_set.provisional_notice, "disabled": list(rule_set.disabled), "rules": rules}


def snapshot_json() -> str:
    out = {}
    for name, fs in scenarios().items():
        out[name] = snapshot(evaluate_rules(fs, calculate_metrics(fs)))
    return json.dumps(out, indent=2, ensure_ascii=True) + "\n"


if __name__ == "__main__":  # pragma: no cover - used by the fresh-process test and to regenerate the golden file
    import sys

    sys.stdout.buffer.write(snapshot_json().encode("ascii"))
