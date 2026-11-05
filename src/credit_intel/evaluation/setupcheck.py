"""A model-free check of a labels file or gate reference against its own document (Phase 7c, S-4).

The held-out run gives one shot per document, and the page range and basis assertion in a reference are fixed by hand before it. A wrong
page, a range that leaves out a labelled page, or a page the basis gate drops looks the same, in the result, as a pipeline fault. This
tool finds such setup errors **without the model and without sending anything**, by testing what the owner wrote against the document's
own text layer and against the same offline steps the run starts with (the locator and the basis gate, as in ``dry_run``).

For each labelled value it asks: is the labelled page inside the document and inside the reference's page range, does the page have a text
layer, does a figure with the printed magnitude occur on it (as one token, or split by a single space in the text layer), and does the printed text occur exactly as written. For the document it asks: does the
SHA-256 match, does the range cover every labelled page, does the basis gate pass with the reference's assertion, and is every labelled page
among the candidate pages the run would send (after the pages whose title names no basis are dropped). The answer is booleans and counts.
It prints no page text, value, label or path.

    uv run --locked python -m credit_intel.evaluation.setupcheck --labels <pdf> <labels.json> [--labels ...]
    uv run --locked python -m credit_intel.evaluation.setupcheck --gate-reference <pdf> <reference.json> [--gate-reference ...]

It works on a tuning document, and on a held-out document that no round has used, before its one shot (the owner's decision of 2026-11-05,
recorded in ``docs/PHASE7c_diagnosis_plan.md`` section 8). It never calls the model and prints no gate field value, only booleans and counts:
it tests what the person who wrote the reference wrote, so that a setup error (a wrong page, a range that leaves out a page, a page the
basis gate drops) is found before the one shot is spent on it. A held-out document that a round has used, in the ledger, stays closed, and
so does a document that is not on the assignment record.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from credit_intel.config import ENV_TOKEN_CEILING, LLMSettings, load_llm_settings
from credit_intel.evaluation.dry_run import dry_run
from credit_intel.evaluation.gate import GateReferenceError, load_reference
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, file_sha256, load_current_sets
from credit_intel.evaluation.ledger import LEDGER_PATH, LedgerUnreadable, read_ledger, used_shas
from credit_intel.evaluation.score import LabelsError, load_labels
from credit_intel.extraction.normalise import parse_value
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import parse_page_range

_EDGE = re.compile(r"^[^\w(+-]+|[^\w)%]+$")


class SetupCheckError(Exception):
    """The file cannot be checked. The message names the problem, never a value."""


@dataclass(frozen=True)
class Item:
    printed: str
    pages: tuple[int, ...]  # the labelled page(s) of the figure


@dataclass(frozen=True)
class Setup:
    document_id: str
    sha256: str
    basis: str
    pages: str | None
    assert_basis: str | None
    items: tuple[Item, ...]


def _items(entries: list) -> tuple[Item, ...]:
    """The printed figures and their pages, from the entries of a file the loaders have already accepted."""
    out = []
    for entry in entries:
        if entry.get("absent") or entry.get("presented") is False:
            continue
        if "parts" in entry:
            out += [Item(part["printed"], (part["page"],)) for part in entry["parts"]]
        else:
            pages = entry["pages"] if "pages" in entry else [entry["page"]]
            out.append(Item(entry["printed"], tuple(sorted(set(pages)))))
    return tuple(out)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def setup_from_labels(path: Path) -> Setup:
    try:
        labels = load_labels(path)
    except LabelsError as error:
        raise SetupCheckError(str(error)) from None
    data = _read(path)
    return Setup(labels.document_id, labels.sha256, labels.basis.value, labels.pages, labels.assert_basis.value if labels.assert_basis else None, _items(data["entries"]))


def setup_from_gate_reference(path: Path) -> Setup:
    try:
        reference = load_reference(path)
    except GateReferenceError as error:
        raise SetupCheckError(str(error)) from None
    data = _read(path)
    return Setup(reference.document_id, reference.sha256, reference.basis.value, reference.pages, reference.assert_basis.value if reference.assert_basis else None, _items(data["entries"]))


def _magnitudes(text: str) -> set[Decimal]:
    """The magnitudes of every token on a page that reads as a figure (a nil dash counts as zero)."""
    found: set[Decimal] = set()
    for token in text.split():
        parsed = parse_value(_EDGE.sub("", token) or token)
        if parsed is not None:
            found.add(abs(parsed.value))
    return found


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _spaced(printed: str, text: str) -> bool:
    """Whether the printed text occurs on the page exactly or with one single space inside it, set off from other digits (a figure whose
    text layer is split by a gap, which the pipeline itself reads, FR-005 column settings). Not a squashed substring: that could run two
    figures together."""
    squashed = _squash(printed)
    if not squashed:
        return False
    variants = [squashed, *(squashed[:k] + " " + squashed[k:] for k in range(1, len(squashed)))]
    pattern = r"(?<![\w.,])(?:" + "|".join(re.escape(v) for v in variants) + r")(?![\w.,])"
    return re.search(pattern, text) is not None


def _figure(printed: str) -> Decimal | None:
    """The magnitude of a printed figure. A currency symbol or a space around it ("$ 1,234") is not part of the figure."""
    for candidate in (printed, _squash(printed), _EDGE.sub("", _squash(printed))):
        parsed = parse_value(candidate)
        if parsed is not None:
            return abs(parsed.value)
    return None


def _guard(sha256: str, assignments: Path, ledger: Path) -> tuple[str, str]:
    """``(document id, set)`` of a document the check may read: a tuning document, or a held-out document no round has used. Fails closed."""
    try:
        known = load_current_sets(assignments).get(sha256) if assignments.exists() else None
        used = used_shas(read_ledger(ledger))
    except (SendRefused, LedgerUnreadable):
        raise SendRefused("the assignment record or the ledger cannot be read") from None
    if known is None:
        raise SendRefused(f"the document ({sha256[:12]}) is not on the assignment record")
    if known[1] == "held_out" and sha256 in used:
        raise SendRefused(f"the document ({sha256[:12]}) is held out and a round has used it: it stays closed")
    return known


def check_setup(setup: Setup, pdf: Path, llm: LLMSettings, assignments: Path = ASSIGNMENTS_PATH, ledger: Path = LEDGER_PATH) -> dict:
    """Booleans and counts for one document and its reference (a tuning document, or a held-out document no round has used)."""
    sha256 = file_sha256(pdf)
    document_id, kind = _guard(sha256, assignments, ledger)
    sha_ok = sha256 == setup.sha256 and document_id == setup.document_id
    if not sha_ok:
        raise SetupCheckError("the file was not written for this document")
    document = ingest(pdf)
    by_number = {p.page_number: p for p in document.pages}
    count = document.file_info.page_count
    in_range = set(parse_page_range(setup.pages, count, count)) if setup.pages else None
    figures = setup.items
    labelled = sorted({page for item in figures for page in item.pages})

    inside = all(p in by_number for p in labelled)
    covers = in_range is None or set(labelled) <= in_range
    with_text = [item for item in figures if all(p in by_number and by_number[p].has_text for p in item.pages)]
    found, literal = 0, 0
    for item in figures:
        pages = [by_number[p] for p in item.pages if p in by_number]
        target = _figure(item.printed)
        if (target is not None and any(target in _magnitudes(p.text) for p in pages)) or any(_spaced(item.printed, p.text) for p in pages):
            found += 1
        if any(item.printed in p.text for p in pages):
            literal += 1

    run = dry_run(pdf, llm, basis=setup.basis, page_range=setup.pages, assert_basis=setup.assert_basis, assignments=assignments, allow_unused_held_out=kind == "held_out")
    candidates = set(run["candidate_pages"])
    gate = run["basis_gate"]
    all_candidates = bool(labelled) and set(labelled) <= candidates
    report = {
        "set": kind,
        "pre_run_setup_check": kind == "held_out",
        "document_id": document_id,
        "sha256_matches": True,
        "values": len(figures),
        "labelled_pages": len(labelled),
        "labelled_pages_in_document": inside,
        "page_range_covers_labelled_pages": covers,
        "values_on_text_layer_pages": len(with_text),
        "figure_found_on_labelled_page": found,
        "printed_text_found_literally": literal,
        "locator": run["locator"],
        "candidate_pages_sent": len(candidates),
        "basis_gate_passes": gate["passes"] is True,
        "basis_gate_error": gate["error_code"],
        "pages_dropped_for_unknown_basis": len(run["removed_for_unknown_basis"]),
        "every_labelled_page_is_sent": all_candidates,
    }
    report["ready"] = (
        inside and covers and len(with_text) == len(figures) and found == len(figures) and report["basis_gate_passes"] and all_candidates
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--labels", nargs=2, action="append", metavar=("PDF", "LABELS"), default=[])
    parser.add_argument("--gate-reference", nargs=2, action="append", metavar=("PDF", "REFERENCE"), default=[])
    parser.add_argument("--assignments", type=Path, default=ASSIGNMENTS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.labels and not args.gate_reference:
        parser.error("give --labels PDF LABELS or --gate-reference PDF REFERENCE")
    jobs = [(setup_from_labels, pdf, file) for pdf, file in args.labels] + [(setup_from_gate_reference, pdf, file) for pdf, file in args.gate_reference]
    try:
        setups = [(reader(Path(file)), Path(pdf)) for reader, pdf, file in jobs]  # the files first: a bad one is refused before anything is read
        llm = load_llm_settings(env={**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1")})  # no call is made
        reports = [check_setup(setup, pdf, llm, args.assignments, args.ledger) for setup, pdf in setups]
    except (SetupCheckError, SendRefused) as error:
        print(f"setupcheck: refused: {error}", file=sys.stderr)
        return 2
    except IngestionError as error:
        print(f"setupcheck: stopped {error.code.value}", file=sys.stderr)
        return 2
    for report in reports:
        print("setupcheck: " + json.dumps(report, sort_keys=True))
    return 0 if all(r["ready"] for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
