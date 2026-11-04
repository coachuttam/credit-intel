"""Where each closed phrase of the pipeline came from, and how far the tuning matches rest on phrases taken from the same document (Phase 7c, S-5).

The statement locator, the row-label check and the borrowings classification accept a closed list of phrases (PRD FR-013, FR-005.10, H.5).
The initial values are the PRD's tables; others were added from tuning documents (PRD O.2, AC-E-7). The record of where each came from is
``tests/eval/phrase_provenance.json``: one object per phrase with its list, the phrase, an ``origin`` and, for a phrase added from a
tuning document, the document and (where the repository records it) the date. A test keeps the file and the configured lists the same set,
so a phrase cannot be added without a provenance line and the file cannot name a phrase that is gone.

``origin`` is one of: ``prd_initial`` (the PRD table's initial value), ``tuning_added`` (added from the named tuning document, per the
repository's own record), ``tuning_added_unverified`` (recorded as added from a tuning document, but the record does not support it, AC-E-7),
``unverified`` (no supporting record at all) and ``rule_defined`` (given by a PRD rule, not by a document). The file records only what the
repository says; it never infers a document or a page, and no held-out identifier may appear in it.

    uv run --locked python -m credit_intel.evaluation.provenance --inventory
    uv run --locked python -m credit_intel.evaluation.provenance --fit <labels.json> [--fit ...]

``--inventory`` prints counts of phrases by list and origin. ``--fit`` takes labels files that carry ``row_label`` (S-3) and counts, for the
entries a row label was given for, whether the phrase that accepts the label is an initial value, one added from the same document, one added
from another tuning document, or unverified. Counts only: no phrase, label or value is printed.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from credit_intel.config import BorrowingSettings, LabelSettings, LocatorSettings
from credit_intel.evaluation.score import LabelsError, load_labels
from credit_intel.extraction.labels import check_label

PROVENANCE_PATH = Path(__file__).resolve().parents[3] / "tests" / "eval" / "phrase_provenance.json"
ORIGINS = ("prd_initial", "tuning_added", "tuning_added_unverified", "unverified", "rule_defined")
MEMBERS = ("list", "phrase", "origin", "documents", "date", "record")


def inventory() -> list[tuple[str, str]]:
    """Every phrase of the closed lists the provenance record covers, as (list name, phrase), from the default settings."""
    out: list[tuple[str, str]] = []
    locator, labels, borrowing = LocatorSettings(), LabelSettings(), BorrowingSettings()
    for kind, phrases in locator.title_phrases.items():
        out += [(f"locator.title.{kind}", p) for p in phrases]
    for kind, phrases in locator.line_item_phrases.items():
        out += [(f"locator.line_item.{kind}", p) for p in phrases]
    out += [("locator.title_prefix", p) for p in locator.title_prefix_words]
    out += [("locator.prefix_connector", p) for p in locator.prefix_connectors]
    out += [("locator.other_statement_title", p) for p in locator.other_statement_title_phrases]
    for kind, phrases in locator.basis_phrases.items():
        out += [(f"locator.basis.{kind}", p) for p in phrases]
    for field, rule in labels.rules.items():
        out += [(f"label.{field}", p) for p in rule.phrases]
        out += [(f"label.{field}.sectioned", p) for p in rule.sectioned_phrases]
    out += [("borrowings.inclusion", p) for p in borrowing.inclusion_phrases]
    out += [("borrowings.exclusion", p) for p in borrowing.exclusion_phrases]
    return out


class ProvenanceError(Exception):
    """The provenance file is unusable."""


def load_provenance(path: Path = PROVENANCE_PATH) -> dict[tuple[str, str], dict]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        raise ProvenanceError("the provenance file cannot be read") from None
    table: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not isinstance(row, dict) or tuple(row) != MEMBERS or row["origin"] not in ORIGINS:
            raise ProvenanceError("a provenance line has the wrong members or origin")
        key = (row["list"], row["phrase"])
        if key in table:
            raise ProvenanceError("a phrase is recorded twice")
        table[key] = row
    return table


def fit(labels_paths: list[Path], table: dict[tuple[str, str], dict] | None = None) -> dict:
    """Counts of the row-labelled entries by the origin of the phrase that accepts the label, relative to the document the entry is in."""
    table = table if table is not None else load_provenance()
    settings = LabelSettings()
    counts: Counter = Counter()
    per_document: dict[str, Counter] = {}
    for path in labels_paths:
        labels = load_labels(path)
        for entry in labels.entries:
            if entry.absent or entry.row_label is None:
                continue
            check = check_label(entry.field.value, f"{entry.row_label} 1", settings=settings)
            if check.matched_phrase is None:
                kind = "off_list"
            else:
                sectioned = check.matched_phrase in settings.rules[entry.field.value].sectioned_phrases
                row = table.get((f"label.{entry.field.value}{'.sectioned' if sectioned else ''}", check.matched_phrase))
                if row is None:
                    kind = "not_recorded"
                elif row["origin"] in ("tuning_added", "tuning_added_unverified"):
                    kind = ("added_from_this_document" if labels.document_id in row["documents"] else "added_from_another_tuning_document") + (
                        "_unverified" if row["origin"].endswith("unverified") else ""
                    )
                else:
                    kind = row["origin"]
            counts[kind] += 1
            per_document.setdefault(labels.document_id, Counter())[kind] += 1
    return {
        "set": "tuning",
        "row_labelled_entries": sum(counts.values()),
        "by_origin": dict(sorted(counts.items())),
        "by_document": {d: dict(sorted(c.items())) for d, c in sorted(per_document.items())},
    }


def summary(table: dict[tuple[str, str], dict] | None = None) -> dict:
    table = table if table is not None else load_provenance()
    by_list: dict[str, Counter] = {}
    for (list_name, _), row in table.items():
        by_list.setdefault(list_name.split(".")[0], Counter())[row["origin"]] += 1
    return {
        "phrases": len(table),
        "by_origin": dict(sorted(Counter(r["origin"] for r in table.values()).items())),
        "by_group": {g: dict(sorted(c.items())) for g, c in sorted(by_list.items())},
        "not_in_record": len(set(inventory()) - set(table)),
        "recorded_but_not_configured": len(set(table) - set(inventory())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--inventory", action="store_true", help="count the configured phrases by list group and origin")
    parser.add_argument("--fit", action="append", type=Path, metavar="LABELS", default=[], help="a labels file with row labels (repeatable)")
    args = parser.parse_args(argv)
    if not args.inventory and not args.fit:
        parser.error("give --inventory or --fit LABELS")
    try:
        if args.inventory:
            print("provenance: " + json.dumps(summary(), sort_keys=True))
        if args.fit:
            print("provenance: " + json.dumps(fit(args.fit), sort_keys=True))
    except (ProvenanceError, LabelsError) as error:
        print(f"provenance: refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
