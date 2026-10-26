"""Memo section 8: questions for the credit analyst (PRD K.1-K.9 row 8, K.8; Phase 5 step 5h).

Every question is produced from a field, an attribute or a rule result in ``results.json`` by a fixed sentence,
so the same results always give the same questions in the same order. Nothing is asked about a value the run
holds. The sentences are a draft for the owner's review (decision 2); they change here and nowhere else.

Order: triggered indicators, conflicting fields, fields to review, fields not found, rules that could not be
evaluated, the borrowings caveat, and details of the document that were not confirmed. Fields that exist only to
support another (operating profit, current maturities) are not asked about when absent, and the two components of
borrowings are not asked about when a total is reported, because nothing needs them.
"""

from typing import Any

from credit_intel.memo.rule_text import condition_text
from credit_intel.memo.sections import CAVEATS, SEVERITY_ORDER, listed_records, words
from credit_intel.memo.text import UNVERIFIED_LABEL, calculated, code, esc, page_phrase, rule

FIELD_NAMES = {
    "revenue": "Revenue",
    "net_profit": "Net profit",
    "operating_profit": "Operating profit",
    "profit_before_tax": "Profit before tax",
    "interest_expense": "Interest expense",
    "current_assets": "Current assets",
    "current_liabilities": "Current liabilities",
    "total_borrowings": "Total borrowings",
    "borrowings_non_current": "Non-current borrowings",
    "borrowings_current": "Current borrowings",
    "current_maturities_long_term_borrowings": "Current maturities of long-term borrowings",
    "total_equity": "Total equity",
    "ebit": "EBIT",
}
NOT_ASKED_WHEN_ABSENT = {"operating_profit", "current_maturities_long_term_borrowings"}  # they only support other values
COMPONENTS = {"borrowings_non_current", "borrowings_current"}
NOT_ASKED_RULES = {"RI-006", "RI-007"}  # the fields they name are asked about one by one
NONE_TEXT = ("No questions were generated: no indicator was triggered and no field is missing, conflicting or awaiting review. "
             "A qualified human must still review this memo.")  # fmt: skip


def _subject(record: dict[str, Any]) -> str:
    return f"{FIELD_NAMES[record['field_name']]} for the period ending {record['period_end']}"


def _triggered(indicator: dict[str, Any]) -> str:
    fired = [c for c in indicator["conditions"] if c["outcome"] == "fired"]
    what = "; ".join(condition_text(indicator["id"], c["condition_id"], c["threshold"]) for c in fired)
    return (f"{esc(indicator['id'])} {esc(indicator['name'])} was triggered ({esc(indicator['severity'])}): {esc(what)}. "
            f"What explains it, and does it need follow-up with the borrower? {rule(indicator['id'])}")  # fmt: skip


def _conflicting(record: dict[str, Any]) -> str:
    seen = "; ".join(f"{esc(c['raw_value'])} on page {c['page_number']}" for c in record["candidates"])
    return f"{_subject(record)} has conflicting values on the pages reviewed ({seen}). Which figure is correct? {UNVERIFIED_LABEL}"


OCR_QUESTION = "Check this value against the page image."


def _review(record: dict[str, Any]) -> str:
    if record.get("evidence_source") == "ocr":
        reason = f" ({esc(words(record['status_reason']))})" if record["status_reason"] else ""
        return f"{_subject(record)} was read by OCR as {esc(record['raw_value'])} on page {record['page_number']} and could not be verified{reason}. {OCR_QUESTION} {UNVERIFIED_LABEL}"
    reason = f" ({esc(words(record['status_reason']))})" if record["status_reason"] else ""
    found = f" as {esc(record['raw_value'])} on page {record['page_number']}" if record["evidence_quote"] is not None else ""
    return f"{_subject(record)} was read{found} but could not be verified{reason}. Confirm the figure from the audited statements. {UNVERIFIED_LABEL}"


def _not_found(record: dict[str, Any], pages: str) -> str:
    return f"{_subject(record)} was not found on {pages} — confirm the figure from the audited statements. {UNVERIFIED_LABEL}"


def _unevaluable(indicator: dict[str, Any]) -> str:
    missing = list(dict.fromkeys(m for c in indicator["conditions"] for m in c["missing_inputs"]))
    return (f"{esc(indicator['id'])} {esc(indicator['name'])} could not be evaluated because of missing inputs ("
            + ", ".join(code(m) for m in missing) + f"). Can they be provided? {rule(indicator['id'])}")  # fmt: skip


def _attribute(attribute: dict[str, Any]) -> str:
    role = f" ({esc(attribute['period_role'])})" if attribute["period_role"] else ""
    return f"The {esc(words(attribute['attribute']))}{role} of the document could not be confirmed. Please confirm it from the document. {UNVERIFIED_LABEL}"


def questions(results: dict[str, Any]) -> list[str]:
    pages = page_phrase(results["extraction"]["candidate_pages"])
    records = listed_records(results)
    total_ok = {r["period_end"] for r in records if r["field_name"] == "total_borrowings" and r["status"] == "extracted"}
    indicators = results["indicators"]
    out = [_triggered(i) for i in sorted((i for i in indicators if i["outcome"] == "triggered" and i["id"] not in NOT_ASKED_RULES),
                                         key=lambda i: (SEVERITY_ORDER[i["severity"]], i["id"]))]  # fmt: skip
    source = [r for r in records if r["origin"] != "derived"]  # a derived value is asked about through its inputs
    out += [_conflicting(r) for r in source if r["status"] == "conflicting"]
    out += [_review(r) for r in source if r["status"] == "requires_review"]
    for r in source:
        if r["status"] != "not_found" or r["field_name"] in NOT_ASKED_WHEN_ABSENT:
            continue
        if r["field_name"] in COMPONENTS and r["period_end"] in total_ok:
            continue
        out.append(_not_found(r, pages))
    out += [_unevaluable(i) for i in indicators if i["outcome"] == "not_evaluable"]
    caveats = dict.fromkeys(c for m in results["metrics"] if m["value"] is not None for c in m["caveats"])
    for caveat in caveats:
        ids = " ".join(calculated(m["id"]) for m in results["metrics"] if caveat in m["caveats"] and m["value"] is not None)
        out.append(f"{esc(CAVEATS.get(caveat, words(caveat))).capitalize()} Please confirm. {ids}")
    out += [_attribute(a) for a in results["attributes"] if a["status"] != "extracted"]
    return out


def section_8(results: dict[str, Any]) -> list[str]:
    lines = ["## 8. Questions for the credit analyst", ""]
    asked = questions(results)
    if not asked:
        return [*lines, NONE_TEXT, ""]
    return [*lines, *(f"{n}. {text}" for n, text in enumerate(asked, 1)), ""]
