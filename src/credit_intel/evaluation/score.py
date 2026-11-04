"""Score a tuning document against full-field-set labels: SC-01 to SC-05 and the ``requires_review`` reasons (PRD O.2, O.3 step 1; Phase 7b, OD-41 to OD-43).

The owner writes one labels file per tuning document, by hand, from the rendered pages, and keeps it in ``private/eval/``. It
holds an entry for **every** extractable field and period (twelve fields, current and comparative): either the value as printed
(with its scale, currency, period end and page) or ``"absent": true`` for a field the report does not present. Nothing is
inferred from the pipeline's output. ``total_borrowings`` is the total the metrics use, as in the gate: the printed total, or
``parts`` that the tool adds, or ``absent``.

    {"document_id": "R1", "sha256": "<64 hex>", "basis": "consolidated", "pages": "36-38", "assert_basis": "consolidated",
     "entries": [
       {"field": "revenue", "period": "current", "period_end": "2025-03-31", "printed": "1,234.5", "scale": "millions",
        "currency": "INR", "page": 37},
       {"field": "total_borrowings", "period": "current", "period_end": "2025-03-31", "currency": "INR",
        "parts": [{"printed": "10", "scale": "millions", "page": 38}, {"printed": "5", "scale": "millions", "page": 38}]},
       {"field": "interest_expense", "period": "comparative", "absent": true}, ...]}

``pages`` and ``assert_basis`` name the page range and the analyst's basis assertion of the live run (the cache key covers
them), exactly as in a gate reference. ``page`` may be ``pages``: a list when the value is printed on more than one page.

What is counted (the denominators are the owner's labels, never the pipeline's output):

* **SC-01** over the labelled-present entries: a match needs status ``extracted`` and the same value, period end, currency and,
  for a source value with a scale, the same scale. A mismatch lists the differing aspects as codes. A miss lists the status
  or reason code.
* **SC-02** (investigate every occurrence): ``extracted`` for a field labelled absent, and ``extracted`` with a different
  value. The tool cannot see the document text, so it counts the candidates and the owner looks at each.
* **SC-03** over the labelled-absent entries: correct is status ``not_found`` (or no record). A ``requires_review`` or
  ``conflicting`` field gives no value but is counted apart, not as correct; ``extracted`` is wrong.
* **SC-04** over ``extracted`` source records: every deterministic check passed. This shows consistency with the cited
  text, not correctness (PRD SC-04).
* **SC-05** over ``extracted`` source records whose value matched: the cited page is one of the labelled pages. A value that
  differs has no ground-truth page, so it is not scored here. A derived total has no cited page and is left out.
* Counts of each ``requires_review`` reason and of each status over the run's records.

Output is counts, field names, period roles and reason codes. It holds no value, quote or label. The replay reads the model's
reply from the response cache (nothing is sent); a cache miss is a failed replay, not a score. A held-out document, or one
the labels were not written for, is refused.

    uv run --locked python -m credit_intel.evaluation.score --skeleton <document_id> > <labels.json>
    uv run --locked python -m credit_intel.evaluation.score --check-labels <labels.json>
    uv run --locked python -m credit_intel.evaluation.score --report <pdf> <labels.json> [--report <pdf> <labels.json> ...]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from types import SimpleNamespace
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from credit_intel.calculations.borrowings import total_borrowings_for
from credit_intel.config import DEFAULT_SETTINGS_PATH, ENV_TOKEN_CEILING, LLMSettings, load_llm_settings
from credit_intel.evaluation.gate import GateReferenceError, _amount, _NoCallProvider, _not_presented, _page
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, check_may_send, file_sha256, load_current_sets, refuse_if_held_out
from credit_intel.extraction.field_set import FieldSet
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import DEFAULT_PROMPT, Prompt, load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.locator import parse_page_range
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.models import ExtractedField, FieldName, Origin, PeriodRole, StatementBasis, Status

SCORED_FIELDS = tuple(name for name in FieldName if name is not FieldName.EBIT)  # ebit is derived, never extracted
ROLES = (PeriodRole.CURRENT, PeriodRole.COMPARATIVE)
MAX_BYTES = 64 * 1024
REQUIRED_KEYS = ("document_id", "sha256", "basis", "entries")
OPTIONAL_KEYS = ("pages", "assert_basis")
ENTRY_KEYS = {"field", "period", "period_end", "printed", "scale", "currency", "page", "pages", "parts", "absent"}
PART_KEYS = {"printed", "scale", "page"}
SHA = re.compile(r"[0-9a-f]{64}")
CURRENCY = re.compile(r"[A-Z]{3}")


class LabelsError(Exception):
    """A labels file is unusable. The message names the problem and the entry, never a value."""


@dataclass(frozen=True)
class Label:
    field: FieldName
    role: PeriodRole
    absent: bool
    period_end: date | None = None
    expected: Decimal | None = None
    currency: str | None = None
    scale: str | None = None  # the scale printed on the page; ``None`` for a total built from parts
    pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class Labels:
    document_id: str
    sha256: str
    basis: StatementBasis
    entries: tuple[Label, ...]
    pages: str | None = None
    assert_basis: StatementBasis | None = None


def _pages_of(raw: dict, where: str) -> tuple[int, ...]:
    if ("page" in raw) == ("pages" in raw):
        raise LabelsError(f"{where}: give exactly one of page and pages")
    if "page" in raw:
        return (_checked(_page, raw, where),)
    listed = raw["pages"]
    if not isinstance(listed, list) or not listed:
        raise LabelsError(f"{where}: pages must be a non-empty list")
    return tuple(sorted({_checked(_page, {"page": p}, where) for p in listed}))


def _checked(call, *args):
    """The gate's amount and page readers share their checks; their message names the entry and never a value."""
    try:
        return call(*args)
    except GateReferenceError as error:
        raise LabelsError(str(error)) from None


def _label(raw: object, index: int) -> Label:
    where = f"entry {index}"
    if not isinstance(raw, dict):
        raise LabelsError(f"{where}: must be an object")
    for key in raw:
        if key not in ENTRY_KEYS:
            raise LabelsError(f"{where}: unknown key {key!r}")
    try:
        field, role = FieldName(raw.get("field")), PeriodRole(raw.get("period"))
    except ValueError:
        raise LabelsError(f"{where}: field or period is not recognised") from None
    if field not in SCORED_FIELDS:
        raise LabelsError(f"{where}: {field.value} is derived and not labelled")
    if "absent" in raw:
        if raw["absent"] is not True or set(raw) != {"field", "period", "absent"}:
            raise LabelsError(f"{where}: absent must be true and replaces every other key except field and period")
        return Label(field, role, True)
    try:
        period_end = date.fromisoformat(raw.get("period_end"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise LabelsError(f"{where}: period_end must be an ISO date") from None
    currency = raw.get("currency")
    if not isinstance(currency, str) or not CURRENCY.fullmatch(currency):
        raise LabelsError(f"{where}: currency must be three capital letters")
    if "parts" in raw:
        if field is not FieldName.TOTAL_BORROWINGS or any(k in raw for k in ("printed", "scale", "page", "pages")):
            raise LabelsError(f"{where}: parts are for total_borrowings only and replace printed, scale and page")
        parts = raw["parts"]
        if not isinstance(parts, list) or len(parts) < 2:
            raise LabelsError(f"{where}: parts must list at least two components")
        for number, part in enumerate(parts, 1):
            if not isinstance(part, dict) or set(part) != PART_KEYS:
                raise LabelsError(f"{where}, part {number}: keys must be exactly printed, scale and page")
        amounts = [_checked(_amount, part, f"{where}, part {n}") for n, part in enumerate(parts, 1)]
        pages = tuple(sorted({_checked(_page, part, f"{where}, part {n}") for n, part in enumerate(parts, 1)}))
        return Label(field, role, False, period_end, sum(amounts, Decimal(0)), currency, None, pages)
    amount = _checked(_amount, raw, where)
    return Label(field, role, False, period_end, amount, currency, raw["scale"], _pages_of(raw, where))


def load_labels(path: Path) -> Labels:
    """Read and check a labels file. Raises ``LabelsError``; the message holds no figure."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise LabelsError("the labels file is larger than 64 KiB")
        data = json.loads(path.read_text(encoding="utf-8"))
    except LabelsError:
        raise
    except (OSError, UnicodeDecodeError):
        raise LabelsError("the labels file cannot be read") from None
    except ValueError:
        raise LabelsError("the labels file is not valid JSON") from None
    if not isinstance(data, dict) or any(k not in data for k in REQUIRED_KEYS) or any(k not in (*REQUIRED_KEYS, *OPTIONAL_KEYS) for k in data):
        raise LabelsError(f"the labels file must be an object with the keys {', '.join(REQUIRED_KEYS)} (and optionally {', '.join(OPTIONAL_KEYS)})")
    document_id, sha256, basis, raw_entries = (data[k] for k in REQUIRED_KEYS)
    pages, asserted = data.get("pages"), data.get("assert_basis")
    if "pages" in data:
        try:
            if not isinstance(pages, str):
                raise ValueError
            parse_page_range(pages, 10**6, 10**6)
        except (ValueError, IngestionError):
            raise LabelsError("pages must be a page range such as 36-38 or 10-12,20") from None
    if "assert_basis" in data:
        if asserted not in ("consolidated", "standalone"):
            raise LabelsError("assert_basis must be consolidated or standalone")
        if "pages" not in data:
            raise LabelsError("assert_basis needs pages")
    if not isinstance(document_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", document_id):
        raise LabelsError("document_id must be a short plain identifier")
    if not isinstance(sha256, str) or not SHA.fullmatch(sha256):
        raise LabelsError("sha256 must be 64 lowercase hexadecimal characters")
    if basis not in ("consolidated", "standalone"):
        raise LabelsError("basis must be consolidated or standalone")
    if not isinstance(raw_entries, list):
        raise LabelsError("entries must be a list")
    entries = tuple(_label(raw, number) for number, raw in enumerate(raw_entries, 1))
    seen = [(e.field, e.role) for e in entries]
    if len(set(seen)) != len(seen):
        raise LabelsError("an entry is repeated: each field and period appears once")
    wanted = {(f, r) for f in SCORED_FIELDS for r in ROLES}
    if set(seen) != wanted:
        missing = sorted(f"{f.value}.{r.value}" for f, r in wanted - set(seen))
        raise LabelsError(f"every field and period needs an entry; missing: {', '.join(missing)}")
    for role in ROLES:
        ends = {e.period_end for e in entries if e.role is role and not e.absent}
        if len(ends) > 1:
            raise LabelsError(f"the {role.value} entries do not share one period_end")
    return Labels(document_id, sha256, StatementBasis(basis), entries, pages, StatementBasis(asserted) if asserted else None)


def skeleton(document_id: str, sha256: str) -> dict:
    """An unfilled labels file: every entry present with its shape and nothing in it, so ``load_labels`` refuses it until it is filled in.

    To fill it, set ``basis`` (and add ``pages`` and ``assert_basis`` if the live run used them), then for each entry either give
    ``period_end``, ``printed``, ``scale``, ``currency`` and ``page`` or replace the entry with ``{"field": ..., "period": ..., "absent": true}``.
    A ``total_borrowings`` entry may instead carry ``currency``, ``period_end`` and ``parts`` (see the module docstring).
    """
    entries = [
        {"field": name.value, "period": role.value, "period_end": None, "printed": None, "scale": None, "currency": None, "page": None}
        for name in SCORED_FIELDS
        for role in ROLES
    ]
    return {"document_id": document_id, "sha256": sha256, "basis": None, "entries": entries}


def _record(field_set: FieldSet, label: Label) -> ExtractedField | None:
    if label.field is FieldName.TOTAL_BORROWINGS:
        return total_borrowings_for(field_set, label.role)
    return field_set.get(label.field, label.role)


def _present(label: Label, record: ExtractedField | None) -> dict:
    out: dict = {"outcome": None, "reason": None, "page_agrees": None, "sc02": None}
    if record is None or record.status is not Status.EXTRACTED:
        out["outcome"] = "missing"
        out["reason"] = "no_record" if record is None else (record.status_reason.value if record.status_reason else record.status.value)
        return out
    wrong = []
    if record.value != label.expected:
        wrong.append("value_differs")
    if record.period_end != label.period_end:
        wrong.append("period_end_differs")
    if record.currency != label.currency:
        wrong.append("currency_differs")
    if record.origin is Origin.SOURCE and label.scale is not None and record.scale is not None and record.scale.value != label.scale:
        wrong.append("scale_differs")
    out["outcome"] = "mismatch" if wrong else "match"
    out["reason"] = ",".join(wrong) or None
    if "value_differs" in wrong:
        out["sc02"] = "value_differs"
    if out["outcome"] == "match" and record.origin is Origin.SOURCE and record.page_number is not None:
        out["page_agrees"] = record.page_number in label.pages
    return out


def _absent(field_set: FieldSet, label: Label, record: ExtractedField | None) -> dict:
    out: dict = {"outcome": None, "reason": None, "page_agrees": None, "sc02": None}
    if label.field is FieldName.TOTAL_BORROWINGS:
        outcome, reason = _not_presented(field_set, SimpleNamespace(field=label.field, role=label.role))  # type: ignore[arg-type]  # it reads only these two
        out["outcome"], out["reason"] = {"match": "correct", "mismatch": "wrong", "missing": "undecided"}[outcome], reason
    elif record is None or record.status is Status.NOT_FOUND:
        out["outcome"] = "correct"
    elif record.status is Status.EXTRACTED:
        out["outcome"], out["reason"] = "wrong", "value_present"
    else:
        out["outcome"] = "undecided"
        out["reason"] = record.status_reason.value if record.status_reason else record.status.value
    if out["outcome"] == "wrong":
        out["sc02"] = "extracted_for_absent"
    return out


def score_document(labels: Labels, field_set: FieldSet) -> dict:
    """Counts only (pure). The field set must be of the labels' basis; a record of another basis is never used."""
    if field_set.configured_basis is not labels.basis:
        raise ValueError("the field set is of another statement basis than the labels")
    entries = []
    for label in labels.entries:
        record = _record(field_set, label)
        scored = _absent(field_set, label, record) if label.absent else _present(label, record)
        entries.append({"field": label.field.value, "period": label.role.value, "labelled": "absent" if label.absent else "present", **scored})
    present = [e for e in entries if e["labelled"] == "present"]
    absent = [e for e in entries if e["labelled"] == "absent"]
    extracted_source = [r for r in field_set.fields if r.status is Status.EXTRACTED and r.origin is Origin.SOURCE]
    paged = [e for e in present if e["page_agrees"] is not None]
    counts = {
        "sc01": {"match": sum(e["outcome"] == "match" for e in present), "of": len(present)},
        "sc02": {
            "extracted_for_absent": sum(e["sc02"] == "extracted_for_absent" for e in entries),
            "value_differs": sum(e["sc02"] == "value_differs" for e in entries),
        },
        "sc03": {"correct": sum(e["outcome"] == "correct" for e in absent), "undecided": sum(e["outcome"] == "undecided" for e in absent), "of": len(absent)},
        "sc04": {"passed": sum(r.validation is not None and r.validation.all_passed() for r in extracted_source), "of": len(extracted_source)},
        "sc05": {"page_agrees": sum(bool(e["page_agrees"]) for e in paged), "of": len(paged)},
    }
    records = field_set.fields
    return {
        "document_id": labels.document_id,
        "entries": entries,
        "counts": counts,
        "statuses": field_set.counts,
        "reasons": dict(sorted(Counter(r.status_reason.value for r in records if r.status_reason).items())),
    }


def aggregate(reports: Sequence[dict]) -> dict:
    """Sum the counts of the replayed documents. A document that did not replay adds nothing and is listed."""
    done = [r for r in reports if r.get("replayed", True)]
    total: dict = {"sc01": {"match": 0, "of": 0}, "sc02": {"extracted_for_absent": 0, "value_differs": 0},
                   "sc03": {"correct": 0, "undecided": 0, "of": 0}, "sc04": {"passed": 0, "of": 0}, "sc05": {"page_agrees": 0, "of": 0}}  # fmt: skip
    reasons: Counter = Counter()
    for report in done:
        for measure, values in report["counts"].items():
            for key, number in values.items():
                total[measure][key] += number
        reasons.update(report["reasons"])
    return {
        "set": "tuning",
        "documents": [r["document_id"] for r in reports],
        "not_replayed": sorted(r["document_id"] for r in reports if not r.get("replayed", True)),
        "counts": total,
        "fractions": {
            "sc01": f"{total['sc01']['match']}/{total['sc01']['of']}",
            "sc03": f"{total['sc03']['correct']}/{total['sc03']['of']}",
            "sc04": f"{total['sc04']['passed']}/{total['sc04']['of']}",
            "sc05": f"{total['sc05']['page_agrees']}/{total['sc05']['of']}",
        },
        "reasons": dict(sorted(reasons.items())),
    }


def replay(
    path: Path,
    labels: Labels,
    *,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    config: Path = DEFAULT_SETTINGS_PATH,
    llm: LLMSettings | None = None,
    prompt: Prompt | None = None,
) -> dict:
    """Replay a tuning document from the response cache and score it. Nothing is sent; a held-out document is refused before any page is read."""
    sha256 = file_sha256(path)
    refuse_if_held_out(sha256, assignments)
    document_id = check_may_send(sha256, assignments)
    if sha256 != labels.sha256 or document_id != labels.document_id:
        raise LabelsError("the labels were not written for this document")
    llm = llm or load_llm_settings(config, {**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1000000")})
    failed = {"set": "tuning", "document_id": document_id, "replayed": False}
    try:
        run = run_extraction(
            path, _NoCallProvider(), llm, basis=labels.basis, cache_dir=cache_dir, prompt=prompt,
            page_range=labels.pages, assert_basis=labels.assert_basis,
        )  # fmt: skip
    except RuntimeError:
        return {**failed, "reason": "cache_miss"}
    except IngestionError as error:
        return {**failed, "reason": error.code.value}
    return {"set": "tuning", "replayed": True, "sha256_prefix": sha256[:12], **score_document(labels, run.field_set)}


def _assignments_commit(assignments: Path) -> str | None:
    """The short hash of the last commit that touched the assignment record, for the report; ``None`` if git cannot say."""
    try:
        done = subprocess.run(
            ["git", "log", "-1", "--format=%h", "--", str(assignments)], cwd=assignments.parent, capture_output=True, text=True, timeout=10, check=False
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.strip()
    return text if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", text) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", nargs=2, action="append", metavar=("PDF", "LABELS"), default=[])
    parser.add_argument("--skeleton", metavar="DOCUMENT_ID", help="print an unfilled labels file for a tuning document on the assignment record")
    parser.add_argument("--check-labels", action="append", type=Path, metavar="LABELS", default=[])
    parser.add_argument("--assignments", type=Path, default=ASSIGNMENTS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML")
    args = parser.parse_args(argv)
    if not args.report and not args.check_labels and not args.skeleton:
        parser.error("give --report PDF LABELS, --check-labels LABELS or --skeleton DOCUMENT_ID")
    try:
        if args.skeleton:
            known = {document_id: (sha256, group) for sha256, (document_id, group) in load_current_sets(args.assignments).items()}
            if args.skeleton not in known or known[args.skeleton][1] != "tuning":
                raise LabelsError("a skeleton is for a tuning document on the assignment record")
            print(json.dumps(skeleton(args.skeleton, known[args.skeleton][0]), indent=2))
            return 0
        for labels_path in args.check_labels:
            labels = load_labels(labels_path)
            present = sum(not e.absent for e in labels.entries)
            print("score: labels ok " + json.dumps({"document_id": labels.document_id, "entries": len(labels.entries), "present": present,
                                                    "absent": len(labels.entries) - present, "pages": labels.pages}, sort_keys=True))  # fmt: skip
        if not args.report:
            return 0
        prompt = load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT))
        reports = []
        for pdf, labels_path in args.report:
            report = replay(Path(pdf), load_labels(Path(labels_path)), assignments=args.assignments, config=args.config, prompt=prompt)
            reports.append(report)
            print("score: " + json.dumps(report, sort_keys=True, ensure_ascii=True))
        recorded = sorted(d for d, group in load_current_sets(args.assignments).values() if group == "tuning")
        summary = {**aggregate(reports), "date": date.today().isoformat(), "assignments_commit": _assignments_commit(args.assignments),
                   "tuning_documents_on_record": recorded}  # fmt: skip
    except (LabelsError, SendRefused) as error:
        print(f"score: refused: {error}", file=sys.stderr)
        return 2
    except IngestionError as error:
        print(f"score: stopped {error.code.value}", file=sys.stderr)
        return 2
    print("score: " + json.dumps(summary, sort_keys=True, ensure_ascii=True))
    return 0 if not summary["not_replayed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
