"""The fixed synthetic field set and the snapshot of its metrics used by the Phase 3 golden test. Not a test module.

INR crore. Current: operating profit not found (so EBIT-PBT), no total of borrowings and no current-maturities
row (so BORR-SUM, not presented). Comparative: interest expense a reported nil (so interest coverage is not
applicable), no total of borrowings either.
"""

import json
from decimal import Decimal

from calc_records import CUR, D24, D25, rec
from credit_intel.calculations.calculate import MetricSet, calculate_metrics
from credit_intel.extraction.field_set import FieldSet
from credit_intel.models import FieldName as F, PeriodRole, StatementBasis as Basis, Status

COMP = PeriodRole.COMPARATIVE

CURRENT = {F.REVENUE: "1200", F.NET_PROFIT: "96", F.PROFIT_BEFORE_TAX: "150", F.INTEREST_EXPENSE: "30",
           F.CURRENT_ASSETS: "450", F.CURRENT_LIABILITIES: "300", F.BORROWINGS_NON_CURRENT: "500",
           F.BORROWINGS_CURRENT: "200", F.TOTAL_EQUITY: "800"}  # fmt: skip
COMPARATIVE = {F.REVENUE: "1000", F.NET_PROFIT: "100", F.PROFIT_BEFORE_TAX: "140", F.INTEREST_EXPENSE: "0",
               F.CURRENT_ASSETS: "360", F.CURRENT_LIABILITIES: "300", F.BORROWINGS_NON_CURRENT: "400",
               F.BORROWINGS_CURRENT: "150", F.TOTAL_EQUITY: "700"}  # fmt: skip


def golden_field_set() -> FieldSet:
    records = [rec(n, v, role=CUR, end=D25) for n, v in CURRENT.items()]
    records += [rec(n, v, role=COMP, end=D24) for n, v in COMPARATIVE.items()]
    records.append(rec(F.OPERATING_PROFIT, status=Status.NOT_FOUND, role=CUR, end=D25))
    return FieldSet(Basis.CONSOLIDATED, tuple(records), (), (), ("consolidated",))


def snapshot(metrics: MetricSet) -> dict:
    """Everything a result says, as plain JSON types: Decimals as strings, dates as ISO text."""
    out = lambda d: None if d is None else str(d)  # noqa: E731
    results = {}
    for (metric, role), r in sorted(metrics.results.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        results[f"{metric}/{role.value if role else '-'}"] = {
            "value": out(r.value), "undefined_reason": r.undefined_reason.value if r.undefined_reason else None,
            "unit": r.unit.value, "formula": r.formula, "input_field_ids": list(r.input_field_ids),
            "input_values": [out(v) for v in r.input_values], "period_ends": [d.isoformat() for d in r.period_ends],
            "caveats": list(r.caveats),
        }  # fmt: skip
    comparisons = {
        m: {"relative_change": out(c.relative_change), "undefined_reason": c.undefined_reason.value if c.undefined_reason else None,
            "caveats": list(c.caveats)}
        for m, c in sorted(metrics.comparisons.items())
    }  # fmt: skip
    derived = [
        {"field_id": d.field_id, "status": d.status.value, "value": out(d.value), "method": d.derivation.method_id,
         "classification": d.derivation.component_classification, "input_field_ids": list(d.derivation.input_field_ids)}
        for d in metrics.derived
    ]  # fmt: skip
    return {"results": results, "comparisons": comparisons, "derived": derived}


def snapshot_json() -> str:
    return json.dumps(snapshot(calculate_metrics(golden_field_set())), indent=2, ensure_ascii=True) + "\n"


if __name__ == "__main__":  # pragma: no cover - used by the fresh-process test and to regenerate the golden file
    import sys

    sys.stdout.buffer.write(snapshot_json().encode("ascii"))
