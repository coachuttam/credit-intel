"""The gate before any held-out run: profit before tax, interest expense and borrowings against hand-checked values (PRD Phase 2 exit, O.2; Phase 5 Part 2).

The owner's conditions (2026-10-24): no held-out run until profit before tax, interest expense and borrowings all
extract on **both tuning reports**; the extraction is compared with **reference values the owner wrote by hand** from
the rendered pages and keeps in ``private/eval/``; the comparison is **counts only** (match, mismatch, missing, per
field); an extracted value that differs from its reference **fails the gate**.

* A reference file holds, for one tuning document, the six values the gate needs (three fields, two periods): as
  printed on the page, with the scale the page declares, the page number and the period end. ``load_reference``
  checks its shape and never repeats a value in a message.
* ``replay`` reads the model's reply from the response cache (nothing is sent: the provider refuses to be called),
  verifies it as a normal run would, and compares. A cache miss is a failure to replay, not a pass.
* A reference may name the `pages` and the `assert_basis` of the live run it was written for (H.4.6, v0.4.24). The cache key covers the
  page set, so a replay must use the same pages, and a document that never names its basis (tuning report R2) passes the basis gate only
  with the same assertion. The report then shows, per value, whether its basis came from a title or from the assertion.
* "Borrowings" is the **total** the metrics use: the reported total, or the sum of non-current and current
  borrowings derived by ``BORR-SUM``. A reference for a total that the report does not print gives the parts, and the
  expected total is their sum.
* The gate passes only if **every tuning document on the assignment record** was replayed and matched on all six
  values. A held-out document is refused, and so is a document the reference was not written for.

    uv run --locked python -m credit_intel.evaluation.gate --report <pdf> <reference.json> [--report <pdf> <reference.json> ...]
    uv run --locked python -m credit_intel.evaluation.gate --check-reference <reference.json>

Output is counts, field names, period roles, page agreement flags and reason codes. It holds no value, quote or label.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from credit_intel.calculations.borrowings import total_borrowings_for
from credit_intel.config import DEFAULT_SETTINGS_PATH, ENV_TOKEN_CEILING, LLMSettings, load_llm_settings
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, check_may_send, file_sha256, load_current_sets, refuse_if_held_out
from credit_intel.extraction.field_set import FieldSet
from credit_intel.extraction.normalise import apply_scale, parse_value
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import DEFAULT_PROMPT, Prompt, load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.locator import parse_page_range
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.provider import LLMRequest, LLMResponse
from credit_intel.models import ExtractedField, FieldName, PeriodRole, Scale, StatementBasis, Status

GATE_FIELDS = (FieldName.PROFIT_BEFORE_TAX, FieldName.INTEREST_EXPENSE, FieldName.TOTAL_BORROWINGS)
ROLES = (PeriodRole.CURRENT, PeriodRole.COMPARATIVE)
MAX_BYTES = 64 * 1024
REQUIRED_KEYS = ("document_id", "sha256", "basis", "entries")
TOP_KEYS = ("document_id", "sha256", "basis", "pages", "assert_basis", "entries")  # the canonical order; pages and assert_basis are optional
ENTRY_KEYS = {"field", "period", "period_end", "page", "printed", "scale", "parts"}
PART_KEYS = {"printed", "scale", "page"}
SHA = re.compile(r"[0-9a-f]{64}")


class GateReferenceError(Exception):
    """A reference file is unusable. The message names the problem and the entry, never a value."""


@dataclass(frozen=True)
class Entry:
    field: FieldName
    role: PeriodRole
    period_end: date
    expected: Decimal
    pages: tuple[int, ...]  # the pages the owner read the value (or its parts) from


@dataclass(frozen=True)
class Reference:
    document_id: str
    sha256: str
    basis: StatementBasis
    entries: tuple[Entry, ...]
    pages: str | None = None  # the ``--pages`` of the live run the reply came from (the cache key covers the page set)
    assert_basis: StatementBasis | None = None  # the ``--assert-basis`` of that run (H.4.6, v0.4.24); needs ``pages``


def _amount(source: object, where: str) -> Decimal:
    if not isinstance(source, dict) or not isinstance(source.get("printed"), str):
        raise GateReferenceError(f"{where}: printed must be a string")
    parsed = parse_value(source["printed"])
    if parsed is None:
        raise GateReferenceError(f"{where}: printed cannot be read as a figure")
    try:
        scale = Scale(source.get("scale"))
    except ValueError:
        raise GateReferenceError(f"{where}: scale is not one of {', '.join(s.value for s in Scale)}") from None
    return apply_scale(parsed.value, scale)


def _page(source: dict, where: str) -> int:
    page = source.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise GateReferenceError(f"{where}: page must be a whole number of 1 or more")
    return page


def _entry(raw: object, index: int) -> Entry:
    where = f"entry {index}"
    if not isinstance(raw, dict):
        raise GateReferenceError(f"{where}: must be an object")
    for key in raw:
        if key not in ENTRY_KEYS:
            raise GateReferenceError(f"{where}: unknown key {key!r}")
    try:
        field, role = FieldName(raw.get("field")), PeriodRole(raw.get("period"))
    except ValueError:
        raise GateReferenceError(f"{where}: field or period is not recognised") from None
    if field not in GATE_FIELDS or role not in ROLES:
        raise GateReferenceError(f"{where}: the gate covers only profit_before_tax, interest_expense and total_borrowings, current and comparative")
    try:
        period_end = date.fromisoformat(raw.get("period_end"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise GateReferenceError(f"{where}: period_end must be an ISO date") from None
    if "parts" in raw:
        if field is not FieldName.TOTAL_BORROWINGS or any(k in raw for k in ("printed", "scale", "page")):
            raise GateReferenceError(f"{where}: parts are for total_borrowings only and replace printed, scale and page")
        parts = raw["parts"]
        if not isinstance(parts, list) or len(parts) < 2:
            raise GateReferenceError(f"{where}: parts must list at least two components")
        for number, part in enumerate(parts, 1):
            if not isinstance(part, dict) or set(part) != PART_KEYS:
                raise GateReferenceError(f"{where}, part {number}: keys must be exactly printed, scale and page")
        return Entry(field, role, period_end, sum((_amount(p, f"{where}, part {n}") for n, p in enumerate(parts, 1)), Decimal(0)),
                     tuple(_page(p, f"{where}, part {n}") for n, p in enumerate(parts, 1)))  # fmt: skip
    return Entry(field, role, period_end, _amount(raw, where), (_page(raw, where),))


def load_reference(path: Path) -> Reference:
    """Read and check a reference file. Raises ``GateReferenceError``; the message holds no figure."""
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise GateReferenceError("the reference file is larger than 64 KiB")
        data = json.loads(path.read_text(encoding="utf-8"))
    except GateReferenceError:
        raise
    except (OSError, UnicodeDecodeError):
        raise GateReferenceError("the reference file cannot be read") from None
    except ValueError:
        raise GateReferenceError("the reference file is not valid JSON") from None
    expected = tuple(k for k in TOP_KEYS if isinstance(data, dict) and k in data)
    if not isinstance(data, dict) or tuple(data) != expected or any(k not in data for k in REQUIRED_KEYS):
        raise GateReferenceError(
            f"the reference file must be an object with the keys {', '.join(REQUIRED_KEYS)}, in the order {', '.join(TOP_KEYS)}"
            " (pages and assert_basis are optional)"
        )
    document_id, sha256, basis, raw_entries = (data[k] for k in REQUIRED_KEYS)
    pages, asserted = data.get("pages"), data.get("assert_basis")
    if "pages" in data:
        try:
            if not isinstance(pages, str):
                raise ValueError
            parse_page_range(pages, 10**6, 10**6)  # the syntax only; the pages are checked against the document when it is replayed
        except (ValueError, IngestionError):
            raise GateReferenceError("pages must be a page range such as 36-38 or 10-12,20") from None
    if "assert_basis" in data:
        if asserted not in ("consolidated", "standalone"):
            raise GateReferenceError("assert_basis must be consolidated or standalone")
        if "pages" not in data:
            raise GateReferenceError("assert_basis needs pages")
    if not isinstance(document_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", document_id):
        raise GateReferenceError("document_id must be a short plain identifier")
    if not isinstance(sha256, str) or not SHA.fullmatch(sha256):
        raise GateReferenceError("sha256 must be 64 lowercase hexadecimal characters")
    if basis not in ("consolidated", "standalone"):
        raise GateReferenceError("basis must be consolidated or standalone")
    if not isinstance(raw_entries, list):
        raise GateReferenceError("entries must be a list")
    entries = tuple(_entry(raw, number) for number, raw in enumerate(raw_entries, 1))
    seen = [(e.field, e.role) for e in entries]
    wanted = [(f, r) for f in GATE_FIELDS for r in ROLES]
    if len(set(seen)) != len(seen):
        raise GateReferenceError("an entry is repeated: each field and period appears once")
    if set(seen) != set(wanted):
        missing = sorted(f"{f.value}.{r.value}" for f, r in set(wanted) - set(seen))
        raise GateReferenceError(f"the gate needs all six entries; missing: {', '.join(missing)}")
    return Reference(document_id, sha256, StatementBasis(basis), entries, pages, StatementBasis(asserted) if asserted else None)


def _record(field_set: FieldSet, entry: Entry) -> ExtractedField | None:
    if entry.field is FieldName.TOTAL_BORROWINGS:
        return total_borrowings_for(field_set, entry.role)
    return field_set.get(entry.field, entry.role)


def compare(reference: Reference, field_set: FieldSet) -> dict:
    """Counts only: per entry ``match``, ``mismatch`` or ``missing``, with a reason code or a flag, never a value.

    The field set must be of the reference's basis. A record of the other basis is never used (``FieldSet.get``), so a
    value read from the wrong statement shows as ``missing``.
    """
    if field_set.configured_basis is not reference.basis:
        raise ValueError("the field set is of another statement basis than the reference")
    results = []
    for entry in reference.entries:
        record = _record(field_set, entry)
        out = {"field": entry.field.value, "period": entry.role.value, "origin": None, "reason": None, "page_agrees": None, "basis_evidence": None}
        if record is None or record.status is not Status.EXTRACTED:
            out["outcome"] = "missing"
            out["reason"] = "no_record" if record is None else (record.status_reason.value if record.status_reason else record.status.value)
        else:
            out["origin"] = record.origin.value
            out["basis_evidence"] = record.basis_evidence.value  # which values rest on the analyst's assertion
            wrong = []
            if record.value != entry.expected:
                wrong.append("value_differs")
            if record.period_end != entry.period_end:
                wrong.append("period_end_differs")
            out["outcome"] = "mismatch" if wrong else "match"
            out["reason"] = ",".join(wrong) or None
            if record.origin.value == "source" and record.page_number is not None:
                out["page_agrees"] = record.page_number in entry.pages  # informational: a right value from another page is worth a look
        results.append(out)
    counts = {name: sum(1 for r in results if r["outcome"] == name) for name in ("match", "mismatch", "missing")}
    return {"document_id": reference.document_id, "replayed": True, "entries": results, "counts": counts, "passed": counts["match"] == len(results)}


class _NoCallProvider:
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("the gate replay is offline: the reply was not in the cache")


def replay(
    path: Path,
    reference: Reference,
    *,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    config: Path = DEFAULT_SETTINGS_PATH,
    llm: LLMSettings | None = None,
    prompt: Prompt | None = None,
) -> dict:
    """Replay a document from the response cache and compare it with its reference. Nothing is sent."""
    sha256 = file_sha256(path)
    refuse_if_held_out(sha256, assignments)
    document_id = check_may_send(sha256, assignments)  # tuning documents only, as for a send
    if sha256 != reference.sha256 or document_id != reference.document_id:
        raise GateReferenceError("the reference was not written for this document")
    llm = llm or load_llm_settings(config, {**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1000000")})
    failed = {"document_id": document_id, "replayed": False, "passed": False, "counts": {"match": 0, "mismatch": 0, "missing": len(reference.entries)}}
    try:
        run = run_extraction(
            path, _NoCallProvider(), llm, basis=reference.basis, cache_dir=cache_dir, prompt=prompt,
            page_range=reference.pages, assert_basis=reference.assert_basis,
        )  # fmt: skip
    except RuntimeError:
        return {**failed, "reason": "cache_miss"}
    except IngestionError as error:
        return {**failed, "reason": error.code.value}
    report = compare(reference, run.field_set)
    assertion = run.basis_assertion
    report["basis_assertion"] = None if assertion is None else {"basis": assertion.basis.value, "pages": list(assertion.pages), "applied_pages": list(assertion.applied_pages)}
    return report


def evaluate_gate(reports: list[dict], assignments: Path = ASSIGNMENTS_PATH) -> dict:
    """The gate: every tuning document on the record, each replayed and matched on all six values."""
    tuning = sorted(document_id for document_id, group in load_current_sets(assignments).values() if group == "tuning")
    reported = sorted(r["document_id"] for r in reports)
    passed = reported == tuning and all(r["passed"] for r in reports)
    return {"passed": passed, "tuning_documents": tuning, "reported": reported, "documents_passed": sum(1 for r in reports if r["passed"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", nargs=2, action="append", metavar=("PDF", "REFERENCE"), default=[])
    parser.add_argument("--check-reference", action="append", type=Path, metavar="REFERENCE", default=[])
    parser.add_argument("--assignments", type=Path, default=ASSIGNMENTS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML")
    args = parser.parse_args(argv)
    if not args.report and not args.check_reference:
        parser.error("give --report PDF REFERENCE or --check-reference REFERENCE")
    try:
        for reference_path in args.check_reference:
            reference = load_reference(reference_path)
            print("gate: " + json.dumps({"reference_ok": True, "document_id": reference.document_id, "entries": len(reference.entries), "pages": reference.pages,
                                   "assert_basis": reference.assert_basis.value if reference.assert_basis else None}, sort_keys=True))
        if not args.report:
            return 0
        prompt = load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT))
        reports = []
        for pdf, reference_path in args.report:
            report = replay(Path(pdf), load_reference(Path(reference_path)), assignments=args.assignments, config=args.config, prompt=prompt)
            reports.append(report)
            print("gate: " + json.dumps(report, sort_keys=True, ensure_ascii=True))
        verdict = evaluate_gate(reports, args.assignments)
    except (GateReferenceError, SendRefused) as error:
        print(f"gate: refused: {error}", file=sys.stderr)
        return 2
    except IngestionError as error:
        print(f"gate: stopped {error.code.value}", file=sys.stderr)
        return 2
    print("gate: " + json.dumps(verdict, sort_keys=True))
    print(f"GATE: {'PASS' if verdict['passed'] else 'FAIL'}")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
