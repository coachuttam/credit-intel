"""The SC-12 counting report: statement-page recall of the locator, per document (PRD SC-12, OD-3, v0.4.49).

SC-12's target: every ground-truth primary-statement page (income statement and balance sheet, continuation pages included) is among
the locator's candidate pages, per document. A document with any missed page fails and the missed page numbers are listed. A document
with more qualifying pages than ``max_candidates`` is reported as cap-limited and counts as failed. Nothing is merged into a
percentage of pages; a run reports "N of M documents passed".

* A labels file holds, for one document, the owner's list of statement pages (``load_labels`` checks its shape and never repeats a
  page list in a message). The format is documented in ``docs/sc12_labels_format.md``; the real files stay in ``private/eval/``.
* The report runs only the text reading and the locator: no model, no network, no key. A held-out document is refused before any
  page is read (O.2), so this report cannot be used on one before the held-out run.
* Output is counts and page numbers. It holds no text, label, value, path or hash.

    uv run --locked python -m credit_intel.evaluation.recall --check-labels <labels.json>
    uv run --locked python -m credit_intel.evaluation.recall --report <pdf> <labels.json> [--report <pdf> <labels.json> ...]
"""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from credit_intel.config import LocatorSettings
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, file_sha256, load_current_sets, refuse_if_held_out
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import CAP, KEYWORDS, locate_statements
from credit_intel.ingestion.models import LocatorResult

MAX_BYTES = 64 * 1024
TOP_KEYS = ("document_id", "sha256", "statement_pages")
STATEMENTS = ("income_statement", "balance_sheet")
SHA = re.compile(r"[0-9a-f]{64}")


class LabelsError(Exception):
    """A labels file is unusable. The message names the problem, never a page list."""


@dataclass(frozen=True)
class Labels:
    document_id: str
    sha256: str
    income_statement: tuple[int, ...]
    balance_sheet: tuple[int, ...]

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.income_statement) | set(self.balance_sheet)))


@dataclass(frozen=True)
class RecallResult:
    """One document's SC-12 result: counts and page numbers only."""

    document_id: str
    truth_pages: int
    candidate_pages: int
    found: int
    missed: tuple[int, ...]
    qualifying_pages: int
    cap_limited: bool
    passed: bool

    def as_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "truth_pages": self.truth_pages,
            "candidate_pages": self.candidate_pages,
            "found": self.found,
            "missed": list(self.missed),
            "qualifying_pages": self.qualifying_pages,
            "cap_limited": self.cap_limited,
            "passed": self.passed,
        }


def _page_list(data: dict, key: str, label: str) -> tuple[int, ...]:
    pages = data.get(key)
    if not isinstance(pages, list) or not pages:
        raise LabelsError(f"{label} must be a non-empty list of page numbers")
    if any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in pages):
        raise LabelsError(f"{label} holds an entry that is not a page number of 1 or more")
    if len(set(pages)) != len(pages) or pages != sorted(pages):
        raise LabelsError(f"{label} must be in ascending order with no repeated page")
    return tuple(pages)


def parse_labels(text: str) -> Labels:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LabelsError("the labels file is not valid JSON") from exc
    if not isinstance(data, dict) or tuple(data) != TOP_KEYS:
        raise LabelsError(f"the labels file must hold exactly these keys, in order: {', '.join(TOP_KEYS)}")
    if not isinstance(data["document_id"], str) or not data["document_id"]:
        raise LabelsError("document_id must be a non-empty string")
    if not isinstance(data["sha256"], str) or not SHA.fullmatch(data["sha256"]):
        raise LabelsError("sha256 must be 64 lowercase hex characters")
    statements = data["statement_pages"]
    if not isinstance(statements, dict) or tuple(statements) != STATEMENTS:
        raise LabelsError(f"statement_pages must hold exactly these keys, in order: {', '.join(STATEMENTS)}")
    return Labels(
        data["document_id"], data["sha256"],
        _page_list(statements, "income_statement", "income_statement"),
        _page_list(statements, "balance_sheet", "balance_sheet"),
    )  # fmt: skip


def load_labels(path: Path) -> Labels:
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise LabelsError("the labels file is larger than 64 KB")
        return parse_labels(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise LabelsError("the labels file cannot be read") from exc


def score_document(labels: Labels, located: LocatorResult, page_count: int | None = None) -> RecallResult:
    """Compare the candidate pages with the labels (pure). Only a keyword location is a locator result: a page range is refused."""
    if located.method != KEYWORDS:
        raise LabelsError("SC-12 measures the keyword locator; a supplied page range has no locator result")
    truth = labels.pages
    if page_count is not None and truth[-1] > page_count:
        raise LabelsError("a labelled page is outside the document")
    candidates = {c.page_number for c in located.candidates}
    missed = tuple(p for p in truth if p not in candidates)
    capped = {e.page_number for e in located.excluded_candidates if e.reason == CAP}
    qualifying = candidates | {e.page_number for e in located.excluded_candidates}
    cap_limited = bool(capped)
    return RecallResult(
        labels.document_id, len(truth), len(candidates), len(truth) - len(missed), missed,
        len(qualifying), cap_limited, passed=not missed and not cap_limited,
    )  # fmt: skip


def report_document(pdf: Path, labels_path: Path, *, settings: LocatorSettings | None = None, assignments: Path = ASSIGNMENTS_PATH) -> RecallResult:
    """Ingest and locate one tuning document and score it. A held-out document is refused before any page is read."""
    labels = load_labels(labels_path)
    sha256 = file_sha256(pdf)
    refuse_if_held_out(sha256, assignments)
    if sha256 != labels.sha256:
        raise LabelsError("the labels file was written for a different document")
    known = load_current_sets(assignments).get(sha256)
    if known is None or known[0] != labels.document_id:
        raise LabelsError("the document is not on the assignment record under the labels file's document_id")
    document = ingest(pdf)
    located = locate_statements(document.pages, settings or LocatorSettings())
    return score_document(labels, located, document.file_info.page_count)


def summary(results: Sequence[RecallResult]) -> dict:
    return {
        "set": "tuning",
        "documents": [r.as_dict() for r in results],
        "passed": sum(1 for r in results if r.passed),
        "of": len(results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check-labels", type=Path, metavar="LABELS", help="check the shape of a labels file and print nothing from it")
    parser.add_argument("--report", nargs=2, action="append", metavar=("PDF", "LABELS"), help="a tuning document and its labels (repeatable)")
    args = parser.parse_args(argv)
    if bool(args.check_labels) == bool(args.report):
        parser.error("give --check-labels or --report")
    try:
        if args.check_labels:
            labels = load_labels(args.check_labels)
            print("recall: labels ok " + json.dumps({"document_id": labels.document_id, "pages": len(labels.pages)}, sort_keys=True))
            return 0
        results = [report_document(Path(pdf), Path(labels)) for pdf, labels in args.report]
    except LabelsError as error:
        print(f"recall: labels unusable ({error})", file=sys.stderr)
        return 1
    except SendRefused as refusal:
        print(f"recall: refused ({refusal})", file=sys.stderr)
        return 1
    except IngestionError as error:
        print(f"recall: stopped {error.code.value}", file=sys.stderr)
        return 1
    print("recall: " + json.dumps(summary(results), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
