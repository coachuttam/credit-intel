"""``results.json``: fields, metrics, indicators and evidence of a run, as exact deterministic JSON (PRD FR-010.1, FR-012.2; step 5d).

Everything the memo says resolves to an ID in this file (K.10): a field ID (``revenue.2025-03-31.consolidated``),
a metric ID with its period (``MET-03.2025-03-31``) or a rule ID (``RI-003``). The file holds no timestamp, run ID
or other thing that changes between runs of the same input, configuration, code and cached replies, so those
runs give byte-identical files (FR-012.2). Amounts and ratios are exact decimal strings (never floats and never
in exponent form); dates are ISO 8601; keys are sorted; the text is UTF-8 with two-space indentation and a final
newline. Evidence (page, quote, label, raw value) is written as it was stored, never edited.
"""

import json
from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from credit_intel.calculations.calculate import MetricSet
from credit_intel.models import PeriodRole
from credit_intel.risk.evaluate import RuleSet
from credit_intel.risk.rules import metric_ref

SCHEMA_VERSION = "1"


def to_jsonable(value: Any, *, layout: bool = False) -> Any:
    """Plain JSON types from the objects of a run.

    A float is refused: money, ratios and thresholds are ``Decimal``. The one exception is a check's
    ``details`` (the value under a ``details`` key), which records where on the page a figure was found, in
    points (``layout=True`` inside it); those are written as the shortest text that reads back exactly. A
    float that is not finite is refused everywhere.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not layout or value != value or value in (float("inf"), float("-inf")):
            raise TypeError("a float cannot be written: amounts and ratios are Decimal")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("a non-finite decimal cannot be written")
        return format(value, "f")  # never exponent notation
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_jsonable(value.value, layout=layout)
    if isinstance(value, BaseModel):
        return to_jsonable(value.model_dump(mode="python"), layout=layout)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name), layout=layout) for f in dataclass_fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key.value if isinstance(key, Enum) else key): to_jsonable(item, layout=layout or key == "details")
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [to_jsonable(item, layout=layout) for item in items]
    raise TypeError(f"cannot write a {type(value).__name__}")


def _metric_entries(metrics: MetricSet) -> list[dict[str, Any]]:
    entries = []
    for (metric_id, role), result in sorted(metrics.results.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        entries.append({
            "id": metric_ref(result, role),
            "metric_id": metric_id,
            "period_role": role.value if isinstance(role, PeriodRole) else None,
            "name": result.name,
            "unit": result.unit.value,
            "formula": result.formula,
            "value": to_jsonable(result.value),
            "undefined_reason": result.undefined_reason.value if result.undefined_reason else None,
            "input_field_ids": list(result.input_field_ids),
            "input_values": [to_jsonable(v) for v in result.input_values],
            "period_ends": [d.isoformat() for d in result.period_ends],
            "caveats": list(result.caveats),
            "origin": "calculated",
        })  # fmt: skip
    return entries


def build_results(extraction: Any, metrics: MetricSet, rules: RuleSet, profile: Any | None = None) -> dict[str, Any]:
    """The contents of ``results.json`` for one run, as plain JSON types."""
    field_set = extraction.field_set
    derived = [*metrics.derived, *metrics.derived_borrowings]
    return {
        "schema_version": SCHEMA_VERSION,
        "document": {
            "file_name": extraction.source_document.file_name,
            "sha256": extraction.source_document.sha256,
            "page_count": extraction.page_count,
        },
        "extraction": {
            "locator_method": extraction.located.method,
            "candidate_pages": sorted(c.page_number for c in extraction.located.candidates),
            "range_pages_without_text": list(extraction.located.range_pages_without_text),
            "excluded_candidates": to_jsonable(extraction.located.excluded_candidates),
            "configured_basis": field_set.configured_basis.value,
            "bases_present": list(field_set.bases_present),
            "attribute_basis_differs": extraction.attribute_basis_differs,
        },
        "attributes": to_jsonable(list(extraction.attributes.all)),
        "fields": to_jsonable(list(field_set.fields)),
        "derived_fields": to_jsonable(derived),
        "ignored_fields": [r.field_id for r in field_set.ignored],
        "metrics": _metric_entries(metrics),
        "comparisons": {m: to_jsonable({
            "metric_id": c.metric_id, "relative_change_percent": c.relative_change,
            "undefined_reason": c.undefined_reason, "caveats": list(c.caveats),
        }) for m, c in sorted(metrics.comparisons.items())},  # fmt: skip
        "indicators": to_jsonable([_indicator(r) for r in rules.results]),
        "disabled_rules": list(rules.disabled),
        "provisional_notice": rules.provisional_notice,
        "analyst_provided": {} if profile is None else {key: value for key, value in profile.items()},
    }


def _indicator(result: Any) -> dict[str, Any]:
    return {
        "id": result.rule_id,
        "name": result.name,
        "outcome": result.outcome,
        "severity": result.severity,
        "conditions": [
            {
                "condition_id": c.condition_id, "outcome": c.outcome, "severity": c.severity, "threshold": c.threshold,
                "values_used": [{"name": name, "value": value} for name, value in c.values_used],
                "missing_inputs": list(c.missing_inputs), "field_ids": list(c.field_ids), "metric_ids": list(c.metric_ids),
                "note": c.note, "caveats": list(c.caveats),
            }
            for c in result.conditions
        ],  # fmt: skip
        "missing_inputs": list(result.missing_inputs),
        "notes": list(result.notes),
        "caveats": list(result.caveats),
    }


def render_results(extraction: Any, metrics: MetricSet, rules: RuleSet, profile: Any | None = None) -> str:
    """The exact text of ``results.json``: sorted keys, two-space indent, UTF-8 characters, one final newline."""
    return json.dumps(build_results(extraction, metrics, rules, profile), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
