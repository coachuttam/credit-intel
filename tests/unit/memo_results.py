"""Full ``results.json`` data for memo tests from a synthetic field set, with the real metrics and rules. Not a test module."""

import json
from pathlib import Path
from types import SimpleNamespace

from calc_records import DOC
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.export.results import build_results
from credit_intel.risk.config import load_risk_rules
from credit_intel.risk.evaluate import evaluate_rules

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "results_golden.json"
RUN_ID, WHEN = "20261024T101530.123456Z-aaaaaaaa", "20261024T101530.123456Z"


def results_for(field_set, *, config=None):
    """What ``build_results`` writes for a run whose fields are ``field_set`` (attributes taken from the golden file)."""
    metrics = calculate_metrics(field_set)
    rules = evaluate_rules(field_set, metrics, config or load_risk_rules())
    located = SimpleNamespace(method="keywords", candidates=(), range_pages_without_text=(), excluded_candidates=())
    extraction = SimpleNamespace(source_document=DOC, page_count=5, located=located, field_set=field_set,
                                 attributes=SimpleNamespace(all=()), attribute_basis_differs=False)  # fmt: skip
    data = build_results(extraction, metrics, rules)
    data["attributes"] = json.loads(GOLDEN.read_text(encoding="utf-8"))["attributes"]
    return data
