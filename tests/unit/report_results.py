"""Synthetic results for the report tests: the reviewed golden results with revenue and net profit filled in (and, optionally, one value read by OCR)."""

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402,F401


def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def set_field(data, field_id, raw, whole, *, page=1, status="extracted", reason=None, source="text_layer"):
    record = next(r for r in [*data["fields"], *data["derived_fields"]] if r["field_id"] == field_id)
    record.update(
        status=status, status_reason=reason, value=whole, currency="INR", raw_value=raw, scale="crore", page_number=page,
        evidence_quote="x", value_interpretation="number", evidence_source=source,
    )  # fmt: skip
    if source == "ocr":
        record["ocr_evidence"] = {"engine": "fake-ocr", "engine_version": "1", "dpi": 300, "min_word_confidence": "60.0", "mean_word_confidence": "80.0", "page_mean_confidence": "85.0"}
    return record


def rich(*, ocr_net_profit=False, inputs_for_coverage=False):
    """Revenue 14,823.00 and 12,100.50, net profit (310.00) and 850.25 (INR crore). Optionally the current net profit is read by OCR,
    and the inputs of interest coverage are extracted so that it is plotted too."""
    data = copy.deepcopy(golden())
    set_field(data, "revenue.2025-03-31.consolidated", "14,823.00", "148230000000")
    set_field(data, "revenue.2024-03-31.consolidated", "12,100.50", "121005000000")
    if ocr_net_profit:
        set_field(data, "net_profit.2025-03-31.consolidated", "(310.00)", None, status="requires_review", reason="ocr_unconfirmed", source="ocr")
    else:
        set_field(data, "net_profit.2025-03-31.consolidated", "(310.00)", "-3100000000")
    set_field(data, "net_profit.2024-03-31.consolidated", "850.25", "8502500000")
    for metric in data["metrics"]:
        if metric["id"] == "MET-05.2025-03-31":
            metric.update(value="2.5", undefined_reason=None)
        if metric["id"] == "MET-05.2024-03-31":
            metric.update(value="7.25", undefined_reason=None)
    if inputs_for_coverage:
        for year, ebit, interest in (("2025", "500", "200"), ("2024", "290", "40")):
            set_field(data, f"ebit.{year}-03-31.consolidated", ebit + ".00", ebit + "0000000")
            set_field(data, f"interest_expense.{year}-03-31.consolidated", interest + ".00", interest + "0000000")
    return data
