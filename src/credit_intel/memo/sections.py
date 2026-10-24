"""The memo header and sections 1 to 4 (PRD K.0 to K.1-K.9; Phase 5 step 5f).

Each function takes the ``results.json`` data (``build_results``), never the run's objects, so everything the
memo says is in the file it points to. Values are shown as printed in the document, with scale and currency,
and ratios and percentages are rounded for display only (FR-007.4): the exact stored value stays in
``results.json``. Every statement carries one origin label (K.0); a statement that cannot be traced to evidence
is labelled ``[UNVERIFIED]``.
"""

from typing import Any

from credit_intel.memo.rule_text import condition_text
from credit_intel.memo.text import (
    ANALYST_LABEL, DASH, UNVERIFIED_LABEL, calculated, code, esc, grouped, rounded, rule, source, table,
)  # fmt: skip

DRAFT_STATEMENT = "DRAFT — generated for human review. Not a credit decision. Verify all figures against the cited sources."
PROFILE_LABELS = {"borrower_name": "Borrower name", "industry": "Industry", "facility_requested": "Facility requested", "notes": "Notes"}
CAVEATS = {
    "borrowings_not_presented_assumption":
        "total borrowings may exclude current maturities of long-term borrowings shown under another caption.",
}  # fmt: skip
LEGEND = [
    ("`[SOURCE: p.N]`", "A value or quote taken verbatim from the document and verified on page N."),
    ("`[CALCULATED: ID]`", "Computed deterministically by the platform from source values, or recorded by it about the run. The ID is in `results.json`."),
    ("`[RULE: RI-xxx]`", "Produced by a configured risk rule."),
    ("`[ANALYST-PROVIDED]`", "Supplied in the borrower profile input; not verified against the document."),
    ("`[UNVERIFIED]`", "Could not be traced to evidence."),
]  # fmt: skip (fixed text, already Markdown)


def words(reason: object) -> str:
    return str(reason).replace("_", " ")


def _attribute(results: dict[str, Any], name: str, role: str | None = None) -> dict[str, Any] | None:
    for attribute in results["attributes"]:
        if attribute["attribute"] == name and attribute["period_role"] == role:
            return attribute
    return None


def _attribute_text(attribute: dict[str, Any] | None) -> str:
    """The attribute's value with its source label, or what is wrong with it, labelled ``[UNVERIFIED]``."""
    if attribute is None or attribute["status"] != "extracted":
        status = "not found" if attribute is None else words(attribute["status"])
        return f"{status} {UNVERIFIED_LABEL}"
    return f"{esc(attribute['normalised_value'])} {source(attribute['page_number'])}"


def borrower_line(results: dict[str, Any]) -> str:
    """The analyst's borrower name if the profile has one, else the entity name read from the document."""
    given = results["analyst_provided"].get("borrower_name")
    if given is not None:
        return f"{esc(given)} {ANALYST_LABEL}"
    return _attribute_text(_attribute(results, "entity_name"))


def header(results: dict[str, Any], run_id: str, generated_at: str) -> list[str]:
    document = results["document"]
    lines = [
        "# Draft credit memo", "",
        f"**Borrower:** {borrower_line(results)}  ",
        f"**Document reviewed:** {esc(document['file_name'])} {calculated('document')}  ",
        f"**Run ID:** {code(run_id)}  ",
        f"**Generated:** {code(generated_at)} (UTC)", "",
        f"> **{DRAFT_STATEMENT}**", "",
        "**Origin labels**", "", *table(["Label", "Meaning"], [list(row) for row in LEGEND]), "",
    ]  # fmt: skip
    return lines


def section_1(results: dict[str, Any]) -> list[str]:
    basis = results["extraction"]["configured_basis"]
    lines = ["## 1. Borrower overview", ""]
    lines += [
        f"- **Entity name:** {_attribute_text(_attribute(results, 'entity_name'))}",
        f"- **Reporting currency:** {_attribute_text(_attribute(results, 'reporting_currency'))}",
        f"- **Scale:** {_attribute_text(_attribute(results, 'scale'))}",
        f"- **Statement basis used:** {esc(basis)} {calculated('extraction')}",
        f"- **Current period end:** {_attribute_text(_attribute(results, 'period_end', 'current'))}",
        f"- **Comparative period end:** {_attribute_text(_attribute(results, 'period_end', 'comparative'))}",
    ]  # fmt: skip
    stated = _attribute(results, "statement_basis")
    if results["extraction"]["attribute_basis_differs"] and stated is not None:
        lines.append(f"- **Note:** the basis the document states ({esc(stated['normalised_value'])}) differs from the basis used. {calculated('extraction')}")
    lines += ["", "**Analyst-provided profile**", ""]
    given = results["analyst_provided"]
    if not given:
        lines.append("No borrower profile was supplied.")
    else:
        lines += [f"- **{PROFILE_LABELS[key]}:** {esc(value)} {ANALYST_LABEL}" for key, value in given.items()]
        lines += ["", "Profile values are not verified against the document and are never used in calculations or rules."]
    return [*lines, ""]


def section_2(results: dict[str, Any], generated_at: str) -> list[str]:
    document, extraction = results["document"], results["extraction"]
    others = [b for b in extraction["bases_present"] if b != extraction["configured_basis"]]
    pages = ", ".join(str(p) for p in extraction["candidate_pages"]) or "none"
    lines = [
        "## 2. Documents reviewed", "",
        f"- **File name:** {esc(document['file_name'])} {calculated('document')}",
        f"- **SHA-256:** {code(document['sha256'])} {calculated('document')}",
        f"- **Page count:** {document['page_count']} {calculated('document')}",
        f"- **Statement basis used:** {esc(extraction['configured_basis'])} {calculated('extraction')}",
        f"- **Other bases present:** {esc(', '.join(others)) if others else 'none'} {calculated('extraction')}",
        f"- **Pages used:** {pages} (located by {words(extraction['locator_method'])}) {calculated('extraction')}",
    ]  # fmt: skip
    if extraction["range_pages_without_text"]:
        empty = ", ".join(str(p) for p in extraction["range_pages_without_text"])
        lines.append(f"- **Pages in the supplied range without text:** {empty} {calculated('extraction')}")
    if extraction["excluded_candidates"]:
        lines.append(f"- **Candidate pages not sent:** {len(extraction['excluded_candidates'])} {calculated('extraction')}")
    lines.append(f"- **Extraction date:** {code(generated_at)} (UTC) {calculated('document')}")
    return [*lines, ""]


def _printed(record: dict[str, Any], reporting_currency: str | None) -> str:
    """The value as printed in the document, with scale and currency; a derived value in whole units."""
    if record["value"] is None:
        return DASH
    if record["origin"] == "derived":
        unit = record["currency"] or reporting_currency
        return f"{grouped(record['value'])} {esc(unit)}".strip()
    shown = "nil (reported as a dash)" if record["value_interpretation"] == "reported_nil" else esc(record["raw_value"])
    unit = " ".join(part for part in (record["currency"], record["scale"] if record["scale"] != "units" else None) if part)
    return f"{shown} ({esc(unit)})" if unit else shown


def _field_label(record: dict[str, Any]) -> str:
    if record["status"] != "extracted":
        return UNVERIFIED_LABEL
    if record["origin"] == "derived":
        return calculated(record["field_id"])
    return source(record["page_number"])


def _notes(record: dict[str, Any], superseded: bool) -> str:
    notes = []
    if record["status_reason"]:
        notes.append(esc(words(record["status_reason"])))
    if record["origin"] == "derived" and record["derivation"]:
        notes.append(f"{code(record['derivation']['formula'])} ({esc(record['derivation']['method_id'])})")
    if superseded:
        notes.append("no total is reported, so it is derived")
    if record["status"] in ("conflicting", "requires_review"):
        notes.append("see section 7")
    return "; ".join(notes)


def listed_records(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Every source and derived field once. A derived total has the ID of the reported total it stands in for
    (BORR-SUM runs only when none is reported); the derived record is the one the metrics read, so it takes the
    place of the source record."""
    derived_ids = {r["field_id"] for r in results["derived_fields"]}
    return [r for r in results["fields"] if r["field_id"] not in derived_ids] + results["derived_fields"]


def section_3(results: dict[str, Any]) -> list[str]:
    currency = (_attribute(results, "reporting_currency") or {}).get("normalised_value")
    records = listed_records(results)
    rows = [
        [code(r["field_id"]), _printed(r, currency), words(r["status"]), _field_label(r), _notes(r, r["origin"] == "derived" and r["field_name"] == "total_borrowings")]
        for r in records
    ]  # fmt: skip
    lines = ["## 3. Financial performance", ""]
    if not rows:
        return [*lines, "No fields were extracted.", ""]
    lines += ["Values are shown as printed in the document, with scale and currency; derived values are in whole units. The exact stored values are in `results.json`.", ""]
    return [*lines, *table(["Field ID", "Value", "Status", "Origin", "Notes"], rows), ""]


def _metric_value(metric: dict[str, Any]) -> str:
    if metric["value"] is None:
        return f"not defined: {words(metric['undefined_reason'])}"
    return rounded(metric["value"], 1) + "%" if metric["unit"] == "percent" else rounded(metric["value"], 2)


def section_4(results: dict[str, Any]) -> list[str]:
    metrics = results["metrics"]
    lines = ["## 4. Financial ratios", ""]
    if not metrics:
        return [*lines, "No metrics were computed.", ""]
    rows = [
        [code(m["id"]), esc(m["name"]), _metric_value(m), code(m["formula"]), ", ".join(code(i) for i in m["input_field_ids"]), calculated(m["id"])]
        for m in metrics
    ]  # fmt: skip
    lines += ["Ratios are rounded for display (percentages to one decimal place, ratios to two); `results.json` keeps full precision.", ""]
    lines += [*table(["Metric ID", "Metric", "Value", "Formula", "Inputs", "Origin"], rows), ""]
    for m in metrics:
        for caveat in m["caveats"]:
            lines.append(f"- **Caveat for {code(m['id'])}:** {esc(CAVEATS.get(caveat, words(caveat)))} {calculated(m['id'])}")
    if any(m["caveats"] for m in metrics):
        lines.append("")
    comparisons = results["comparisons"]
    if comparisons:
        lines += ["**Change from the comparative period to the current period**", ""]
        crows = []
        for metric_id, c in comparisons.items():
            change = c["relative_change_percent"]
            shown = f"{rounded(change, 1)}%" if change is not None else f"not defined: {words(c['undefined_reason'])}"
            crows.append([code(metric_id), shown, calculated(metric_id)])
        lines += [*table(["Metric", "Relative change", "Origin"], crows), ""]
        for metric_id, c in comparisons.items():
            for caveat in c["caveats"]:
                lines.append(f"- **Caveat for the change in {code(metric_id)}:** {esc(CAVEATS.get(caveat, words(caveat)))} {calculated(metric_id)}")
    return lines


# --- section 5: potential risk indicators ----------------------------------------------------------------------------------------------------

SEVERITY_ORDER = {"elevated": 0, "watch": 1, "info": 2}


def _value_text(name: str, value: str, currency: str | None) -> str:
    """A value a rule used, in the display form of its kind: percentages one decimal place, ratios two, amounts whole."""
    if name.endswith("_percent"):
        return rounded(value, 1) + "%"
    if name.startswith(("current_ratio", "debt_to_equity", "interest_coverage")):
        return rounded(value, 2)
    if name.startswith(("net_profit", "total_equity")):
        return f"{grouped(value)} {esc(currency)}".strip()
    return esc(value)  # a count


def _used_name(name: str) -> str:
    name = name.removesuffix("_percent")  # the value is shown with its % sign
    for suffix, period in (("_current", " (current period)"), ("_comparative", " (comparative period)")):
        if name.endswith(suffix):
            return words(name[: -len(suffix)]) + period
    return words(name)


def _threshold_text(rule_id: str, condition: dict[str, Any]) -> str:
    return esc(condition_text(rule_id, condition["condition_id"], condition["threshold"]))


def _field_inputs(results: dict[str, Any], field_ids: list[str], currency: str | None) -> str:
    """The input fields of a condition, each with its value as printed and its own label."""
    known = {r["field_id"]: r for r in listed_records(results)}
    parts = []
    for field_id in field_ids:
        record = known.get(field_id)
        if record is None:
            parts.append(f"{code(field_id)} {UNVERIFIED_LABEL}")
        elif record["status"] != "extracted":
            parts.append(f"{code(field_id)} {words(record['status'])} {UNVERIFIED_LABEL}")
        else:
            parts.append(f"{code(field_id)} {_printed(record, currency)} {_field_label(record)}")
    return "; ".join(parts)


def _caveat_words(caveats: list[str]) -> str:
    return "; ".join(esc(CAVEATS.get(c, words(c))) for c in dict.fromkeys(caveats))


def _indicator_block(results: dict[str, Any], indicator: dict[str, Any], currency: str | None) -> list[str]:
    rid, label = indicator["id"], rule(indicator["id"])
    lines = [f"> **{esc(rid)} {esc(indicator['name'])} — {esc(indicator['severity'])}** {label}", ">"]
    for c in indicator["conditions"]:
        if c["outcome"] != "fired":
            continue
        lines.append(f"> Condition {esc(c['condition_id'])} ({esc(c['severity'])}): {_threshold_text(rid, c)}"
                     + (" (provisional threshold, configurable)." if c["threshold"] is not None else ".") + f" {label}")  # fmt: skip
        if c["values_used"]:
            seen = ", ".join(f"{_used_name(v['name'])} = {_value_text(v['name'], v['value'], currency)}" for v in c["values_used"])
            metrics = " ".join(calculated(m) for m in c["metric_ids"])
            lines.append(f"> Observed: {seen} {metrics} {label}".replace("  ", " "))
        if c["note"] and rid != "RI-006" and rid != "RI-007":
            lines.append(f"> Note: {esc(c['note'])} {label}")
        if rid in ("RI-006", "RI-007"):
            lines.append(f"> Fields: {_field_inputs(results, c['field_ids'], currency)}")
        elif c["field_ids"]:
            lines.append(f"> From: {_field_inputs(results, c['field_ids'], currency)}")
        if c["caveats"]:
            lines.append(f"> Caveat: {_caveat_words(c['caveats'])} {label}")
    others = [c for c in indicator["conditions"] if c["outcome"] != "fired"]
    if others:
        parts = []
        for c in others:
            text = f"{esc(c['condition_id'])} {words(c['outcome'])}"
            if c["missing_inputs"]:
                text += " (missing: " + ", ".join(code(m) for m in c["missing_inputs"]) + ")"
            parts.append(text)
        lines.append(f"> Other conditions: {'; '.join(parts)} {label}")
    # Lines of one block quote would run together as one paragraph, so each ends with a hard line break.
    return [line + "  " if i + 1 < len(lines) and line != ">" and lines[i + 1] != ">" else line for i, line in enumerate(lines)]


def section_5(results: dict[str, Any]) -> list[str]:
    currency = (_attribute(results, "reporting_currency") or {}).get("normalised_value")
    indicators = results["indicators"]
    triggered = sorted((i for i in indicators if i["outcome"] == "triggered"), key=lambda i: (SEVERITY_ORDER[i["severity"]], i["id"]))
    lines = ["## 5. Potential risk indicators", "", f"> {esc(results['provisional_notice'])} {calculated('provisional_notice')}", ""]
    lines += ["Indicators are prompts for a human to investigate. They are not a rating, a score or a credit decision.", ""]
    if not triggered:
        lines += ["No risk indicators triggered by the configured rules.", ""]
    for indicator in triggered:
        lines += [*_indicator_block(results, indicator, currency), ""]
    unevaluable = [i for i in indicators if i["outcome"] == "not_evaluable"]
    if unevaluable:
        lines += ["**Rules that could not be evaluated**", ""]
        for i in unevaluable:
            missing = list(dict.fromkeys(m for c in i["conditions"] for m in c["missing_inputs"]))
            lines.append(f"- **{esc(i['id'])} {esc(i['name'])}:** not evaluable; missing " + ", ".join(code(m) for m in missing) + f" {rule(i['id'])}")
        lines.append("")
    quiet = [i for i in indicators if i["outcome"] == "not_triggered"]
    if quiet:
        lines += ["**Rules evaluated and not triggered:** " + ", ".join(f"{esc(i['id'])} {esc(i['name'])}" for i in quiet) + " " + " ".join(rule(i["id"]) for i in quiet), ""]
    if results["disabled_rules"]:
        lines += ["**Rules disabled in the configuration:** " + ", ".join(esc(r) for r in results["disabled_rules"]) + " " + " ".join(rule(r) for r in results["disabled_rules"]), ""]
    return lines


# --- section 6: evidence and source references -----------------------------------------------------------------------------------------------


def _evidence_lines(evidence: dict[str, Any], label: str | None = None) -> list[str]:
    """Where a value was found: page, line item and value as printed, then the quote. ``label`` defaults to the
    source label; evidence that is not verified (a candidate, a field to review) passes ``[UNVERIFIED]``."""
    page = f"page {evidence['page_number']}" + (f", page label {esc(evidence['page_label'])}" if evidence["page_label"] else "")
    return [f"{page}, line item “{esc(evidence['line_item_label'])}”, value as printed {esc(evidence['raw_value'])} {label or source(evidence['page_number'])}",
            "", f"> {esc(evidence['evidence_quote'])}"]  # fmt: skip


def section_6(results: dict[str, Any]) -> list[str]:
    lines = ["## 6. Evidence and source references", ""]
    sourced = [r for r in results["fields"] if r["evidence_quote"] is not None and r["status"] == "extracted"]
    derived = results["derived_fields"]
    if not sourced and not derived:
        return [*lines, "No evidence was recorded.", ""]
    for record in sourced:
        evidence = {k: record[k] for k in ("page_number", "page_label", "line_item_label", "raw_value", "evidence_quote")}
        first, blank, quote = _evidence_lines(evidence)
        lines += [f"**{code(record['field_id'])}** — {first}", blank, quote, ""]
        for other in record["corroborating_evidence"]:
            f2, b2, q2 = _evidence_lines(other)
            lines += [f"Also found: {f2}", b2, q2, ""]
    if derived:
        lines += ["**Derived values**", ""]
        for record in derived:
            d = record["derivation"]
            inputs = ", ".join(code(i) for i in d["input_field_ids"])
            lines.append(f"- {code(record['field_id'])} — method {esc(d['method_id'])}: {code(d['formula'])}; inputs {inputs} {calculated(record['field_id'])}")
        lines.append("")
    return lines


# --- section 7: missing information and conflicts ---------------------------------------------------------------------------------------------


def section_7(results: dict[str, Any]) -> list[str]:
    lines = ["## 7. Missing information and conflicts", ""]
    flagged = [r for r in listed_records(results) if r["status"] != "extracted"]
    attributes = [a for a in results["attributes"] if a["status"] != "extracted"]
    if not flagged and not attributes:
        return [*lines, "No field is missing, conflicting or awaiting review.", ""]
    for status, heading in (("not_found", "Not found"), ("conflicting", "Conflicting"), ("requires_review", "Requires review")):
        group = [r for r in flagged if r["status"] == status]
        if not group:
            continue
        lines += [f"**{heading}** ({len(group)})", ""]
        for record in group:
            reason = f" — {esc(words(record['status_reason']))}" if record["status_reason"] else ""
            lines.append(f"- {code(record['field_id'])}{reason} {UNVERIFIED_LABEL}")
            for candidate in record["candidates"]:
                lines += ["", f"  Candidate {esc(candidate['raw_value'])}: " + _evidence_lines(candidate, UNVERIFIED_LABEL)[0], "", f"  > {esc(candidate['evidence_quote'])}"]
            if status == "requires_review" and record["evidence_quote"] is not None:
                lines += ["", "  Evidence: " + _evidence_lines({k: record[k] for k in ("page_number", "page_label", "line_item_label", "raw_value", "evidence_quote")}, UNVERIFIED_LABEL)[0], "", f"  > {esc(record['evidence_quote'])}"]
            if record["candidates"] or (status == "requires_review" and record["evidence_quote"] is not None):
                lines.append("")
        lines.append("")
    if attributes:
        lines += [f"**Document details not confirmed** ({len(attributes)})", ""]
        for a in attributes:
            role = f" ({esc(a['period_role'])})" if a["period_role"] else ""
            reason = f" — {esc(words(a['status_reason']))}" if a["status_reason"] else ""
            lines.append(f"- {esc(words(a['attribute']))}{role}: {esc(words(a['status']))}{reason} {UNVERIFIED_LABEL}")
        lines.append("")
    return lines
