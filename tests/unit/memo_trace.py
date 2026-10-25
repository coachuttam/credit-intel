"""A checker for the traceability rule (PRD K.10) and for well-formed Markdown (FR-010.2). Not a test module.

``problems(memo, results)`` returns a list of what is wrong with a memo, empty when it is sound:

* every origin label is one of the five forms, and every unescaped bracket is a label;
* ``[CALCULATED: x]`` names a metric, a derived field, a comparison or one of ``document``, ``extraction``,
  ``provisional_notice``; ``[RULE: x]`` names an indicator; ``[SOURCE: p.N]`` names a page that the fields it sits
  with were read on; ``[ANALYST-PROVIDED]`` sits beside a value the profile holds;
* every field, metric and rule ID written in the memo exists in the results;
* in the field and metric tables a row is labelled ``[UNVERIFIED]`` exactly when the field is not ``extracted``, and
  the value shown is the one in the results (as printed, whole units, or rounded half to even);
* a sentence about an asserted basis (K.0) carries ``[ANALYST-PROVIDED]`` and exists only if ``extraction.basis_assertion`` does; the header
  sentence is there when an assertion was given (applied or not needed); the sentence under sections 4 and 5 is there exactly when an
  extracted field of the run has ``basis_evidence = analyst_assertion``;
* headings are the title, then sections 1 to 9 in order; tables are rectangular; code spans are closed; no
  unescaped HTML, link or heading marker reaches the text.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal

from credit_intel.memo.text import esc

LABEL = re.compile(r"(?<!\\)\[([^\]\\]*)\]")
FIELD_ID = re.compile(r"\b[a-z_]+\.\d{4}-\d{2}-\d{2}\.(?:consolidated|standalone)\b")
METRIC_ID = re.compile(r"\bMET-0\d(?:\.\d{4}-\d{2}-\d{2})?\b")
RULE_ID = re.compile(r"\bRI-00\d\b")
CODE = re.compile(r"`([^`]*)`")
TOP_LEVEL = {"document", "extraction", "provisional_notice"}
ASSERTION_MARKERS = ("asserted by the analyst", "analyst assertion of the basis")
ASSERTED_INPUTS = "These figures rest on a statement basis that was asserted by the analyst, not established by the document."
FORMS = [re.compile(p) for p in (r"SOURCE: p\.\d+", r"CALCULATED: [A-Za-z0-9_.\-]+", r"RULE: [A-Za-z0-9_.\-]+", r"ANALYST-PROVIDED", r"UNVERIFIED")]


def split_cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def _known(results):
    fields = {r["field_id"]: r for r in results["fields"]}
    fields.update({r["field_id"]: r for r in results["derived_fields"]})  # the derived record is the one a total stands for
    metrics = {m["id"]: m for m in results["metrics"]}
    return fields, metrics


def _pages_of(record):
    pages = {record["page_number"]} if record.get("page_number") else set()
    pages |= {e["page_number"] for e in record.get("corroborating_evidence", [])}
    pages |= {c["page_number"] for c in record.get("candidates", [])}
    return pages


def problems(memo: str, results: dict) -> list[str]:
    found: list[str] = []
    fields, metrics = _known(results)
    all_source = {r["field_id"]: r for r in results["fields"]}
    attributes = {a["id"]: a for a in results["attributes"]}  # document-level attributes by ID (H.1.2, v0.4.27)
    calculated_ids = set(metrics) | {f for f, r in fields.items() if r["origin"] == "derived"} | set(results["comparisons"]) | TOP_LEVEL
    rule_ids = {i["id"] for i in results["indicators"]}
    profile = results["analyst_provided"]
    assertion = results["extraction"].get("basis_assertion")
    lines = memo.split("\n")
    headings = [l for l in lines if l.startswith("#")]
    if [h.split(" ")[0] for h in headings] != ["#"] + ["##"] * 9 or [re.match(r"## (\d)\.", h).group(1) for h in headings[1:] if re.match(r"## (\d)\.", h)] != list("123456789"):
        found.append(f"headings are not the title and sections 1 to 9: {headings}")
    if not memo.endswith("\n") or memo.endswith("\n\n"):
        found.append("the memo must end with exactly one newline")

    if assertion is not None:
        header_sentence = "**Basis asserted by the analyst**" if assertion["applied_pages"] else "was not needed."
        if header_sentence not in memo.split("\n## 1. ")[0]:  # in the header itself, not only in section 1
            found.append("an assertion of the basis was given but the memo does not disclose it")
    rests = any(r["status"] == "extracted" and r.get("basis_evidence") == "analyst_assertion" for r in fields.values())
    standalone = sum(1 for line in lines if line == f"{ASSERTED_INPUTS} [ANALYST-PROVIDED]")  # whole lines: a profile note that quotes it is not one
    if standalone != (2 if rests else 0):
        found.append(f"the sentence about figures resting on an asserted basis appears {standalone} times, expected {2 if rests else 0}")

    section, current_field, in_table, table_width = 0, None, False, None
    for number, line in enumerate(lines, 1):
        where = f"line {number}"
        heading = re.match(r"## (\d)\.", line)
        if heading:
            section = int(heading.group(1))
        masked = line.replace("\\`", "\x00")  # an escaped backtick is text, not a code span
        if masked.count("`") % 2:
            found.append(f"{where}: unclosed code span")
        codes = CODE.findall(masked)
        text = CODE.sub("", masked).replace("\x00", "\\`")
        if re.search(r"(?<!\\)<", text) or re.search(r"(?<!\\)\]\(", text):
            found.append(f"{where}: raw HTML or a link")
        if re.match(r"\s*#{1,6}\s", line) and not line.startswith(("# ", "## ")):
            found.append(f"{where}: a heading that is not the title or a section")
        # tables are rectangular
        if line.startswith("|"):
            width = len(split_cells(line))
            if in_table and width != table_width:
                found.append(f"{where}: table row has {width} cells, the table has {table_width}")
            in_table, table_width = True, table_width if in_table else width
        else:
            in_table = False
        # identifiers written in the memo exist
        in_code = " ".join(codes) + " " + text
        for match in re.finditer(FIELD_ID, " ".join(codes)):
            if match.group(0) not in fields and match.group(0) not in all_source:
                found.append(f"{where}: unknown field ID {match.group(0)}")
        for match in re.finditer(METRIC_ID, " ".join(codes) + " " + text):
            ident = match.group(0)
            if ident not in metrics and ident not in results["comparisons"] and not any(m.startswith(ident + ".") for m in metrics):
                found.append(f"{where}: unknown metric ID {ident}")
        for ident in RULE_ID.findall(in_code):
            if ident not in rule_ids:
                found.append(f"{where}: unknown rule ID {ident}")
        line_fields = [c for c in FIELD_ID.findall(" ".join(codes)) if c in fields]
        if line_fields:
            current_field = line_fields[0]
        # attribute IDs written in section 1 exist, and the label agrees with the attribute's status
        for code_text in codes:
            if re.fullmatch(r"(?:entity_name|statement_basis|reporting_currency|scale|period_end\.\w+)", code_text) and code_text not in attributes:
                found.append(f"{where}: unknown attribute ID {code_text}")
        for code_text in codes:
            if code_text in attributes and section == 1 and line.startswith("- **"):
                extracted = attributes[code_text]["status"] == "extracted"
                if ("[UNVERIFIED]" in line) == extracted:
                    found.append(f"{where}: the label does not agree with the status of {code_text}")
        # labels
        if text.count("[") != len(LABEL.findall(text)) + text.count("\\["):
            found.append(f"{where}: a bracket that is not a label and not escaped")
        for label in LABEL.findall(text):
            if not any(f.fullmatch(label) for f in FORMS):
                found.append(f"{where}: unknown label [{label}]")
            elif label.startswith("CALCULATED: ") and label[12:] not in calculated_ids:
                found.append(f"{where}: [{label}] names nothing in the results")
            elif label.startswith("RULE: ") and label[6:] not in rule_ids:
                found.append(f"{where}: [{label}] names no indicator")
            elif label.startswith("SOURCE: p."):
                page = int(label[10:])
                if section <= 1:
                    named = [attributes[c] for c in codes if c in attributes]
                    if not named and section == 0:  # the header's Borrower line is the entity name
                        named = [attributes["entity_name"]]
                    ok = any(a["page_number"] == page for a in named)
                else:
                    ids = line_fields or [current_field]
                    ok = any(page in (_pages_of(fields[i]) | _pages_of(all_source.get(i, fields[i]))) for i in ids if i in fields)
                if not ok:
                    found.append(f"{where}: [{label}] is not a page the field or attribute beside it was read on")
            elif label == "ANALYST-PROVIDED" and not any(esc(v) in text for v in profile.values()):
                if not (assertion is not None and any(marker in text for marker in ASSERTION_MARKERS)):
                    found.append(f"{where}: [ANALYST-PROVIDED] beside text the profile does not hold and no assertion records")
        # field and metric tables
        cells = split_cells(line) if line.startswith("| `") else []
        if section == 3 and cells and cells[0].strip("`") in fields:
            record = fields[cells[0].strip("`")]
            extracted = record["status"] == "extracted"
            if cells[2] != record["status"].replace("_", " "):
                found.append(f"{where}: status shown is not the status held")
            if ("[UNVERIFIED]" not in cells[3]) != extracted:
                found.append(f"{where}: label does not agree with the status")
            if extracted and record["origin"] == "derived" and not cells[1].startswith(format(Decimal(record["value"]), ",f")):
                found.append(f"{where}: derived value shown is not the one held")
            if extracted and record["origin"] == "source" and not (cells[1].startswith(esc(record["raw_value"])) or record["value_interpretation"] == "reported_nil"):
                found.append(f"{where}: value shown is not the value as printed")
            if not extracted and cells[1] != "—" and record["status"] != "requires_review":
                found.append(f"{where}: a value is shown for a field that is not extracted")
        if section == 4 and cells and cells[0].strip("`") in metrics:
            metric = metrics[cells[0].strip("`")]
            if metric["value"] is None:
                want = "not defined: " + metric["undefined_reason"].replace("_", " ")
            elif metric["unit"] == "percent":
                want = format(Decimal(metric["value"]).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN), "f") + "%"
            else:
                want = format(Decimal(metric["value"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), "f")
            if cells[2] != want:
                found.append(f"{where}: metric value shown is {cells[2]!r}, expected {want!r}")
            if cells[5] != f"[CALCULATED: {metric['id']}]":
                found.append(f"{where}: metric label does not name its own ID")
    return found
