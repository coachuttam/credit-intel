"""The memo header and sections 1 to 4 (PRD K.0 to K.1-K.9; Phase 5 step 5f).

Each function takes the ``results.json`` data (``build_results``), never the run's objects, so everything the
memo says is in the file it points to. Values are shown as printed in the document, with scale and currency,
and ratios and percentages are rounded for display only (FR-007.4): the exact stored value stays in
``results.json``. Every statement carries one origin label (K.0); a statement that cannot be traced to evidence
is labelled ``[UNVERIFIED]``.
"""

from typing import Any

from credit_intel.memo.text import (
    ANALYST_LABEL, DASH, UNVERIFIED_LABEL, calculated, code, esc, grouped, rounded, source, table,
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


def section_3(results: dict[str, Any]) -> list[str]:
    currency = (_attribute(results, "reporting_currency") or {}).get("normalised_value")
    derived_ids = {r["field_id"] for r in results["derived_fields"]}
    # A derived total has the ID of the reported total it stands in for (BORR-SUM runs only when none is
    # reported); the derived record is the one the metrics read, so it takes the place of the source record.
    records = [r for r in results["fields"] if r["field_id"] not in derived_ids] + results["derived_fields"]
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
