"""The held-out ledger: which held-out documents a round has used (PRD O.2, v0.4.41, v0.4.42).

``tests/eval/heldout_runs.jsonl`` is append-only. A ``started`` line is written before the first page of a document is sent, and a
``completed`` line after its report, so a document with either line has used its one shot. A **release** (v0.4.73) is a third kind of line:
the owner's recorded decision that a document's earlier attempt produced no information about it (it stopped before any page was read and
before any model call), so the document counts as unused again. A release carries a ``reason``, in the line itself, and is valid only for a
document that is currently used. Nothing is ever edited or removed; a release is a new line, and a later ``started`` line uses the document
again.

This module only reads and appends the ledger. It is separate from the held-out run tool so that the setup check can ask whether a document is
used without importing the tool that sends held-out documents (a test checks that no other module imports that tool).
"""

import json
import os
from pathlib import Path

from credit_intel.evaluation.guard import PROJECT_ROOT

LEDGER_PATH = PROJECT_ROOT / "tests" / "eval" / "heldout_runs.jsonl"
LEDGER_MEMBERS = ("document_id", "sha256", "run_id", "event", "at", "freeze_commit", "assignments_sha256")
RELEASE_MEMBERS = (*LEDGER_MEMBERS, "reason")
USE_EVENTS = ("started", "completed")
MAX_REASON = 1000


class LedgerUnreadable(Exception):
    """The ledger is malformed. Everything that reads it fails closed."""


def read_ledger(path: Path) -> list[dict]:
    """The ledger's lines; a missing file is an empty ledger (the first run). Anything malformed refuses everything."""
    if not path.exists():
        return []
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise LedgerUnreadable from None
    if "\r" in text or (text and not text.endswith("\n")):
        raise LedgerUnreadable
    records: list[dict] = []
    state: dict[str, bool] = {}  # per document: is it currently used
    for line in text.split("\n")[:-1] if text else []:
        try:
            record = json.loads(line)
        except ValueError:
            raise LedgerUnreadable from None
        if not isinstance(record, dict) or not all(isinstance(value, str) for value in record.values()):
            raise LedgerUnreadable
        event = record.get("event")
        if event in USE_EVENTS and tuple(record) == LEDGER_MEMBERS:
            state[record["sha256"]] = True
        elif event == "released" and tuple(record) == RELEASE_MEMBERS and record["reason"].strip() and len(record["reason"]) <= MAX_REASON:
            if not state.get(record["sha256"], False):
                raise LedgerUnreadable  # a release of a document that is not used: nothing to release
            state[record["sha256"]] = False
        else:
            raise LedgerUnreadable
        records.append(record)
    return records


def used_shas(records: list[dict]) -> set[str]:
    """The documents that are currently used: a ``started`` or ``completed`` line not followed by a later ``released`` line."""
    state: dict[str, bool] = {}
    for record in records:
        state[record["sha256"]] = record["event"] in USE_EVENTS
    return {sha for sha, used in state.items() if used}


def append_ledger(path: Path, record: dict) -> None:
    """Append one line and make it durable before the caller goes on (a ``started`` line must outlive a crash)."""
    assert tuple(record) in (LEDGER_MEMBERS, RELEASE_MEMBERS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def release_line(records: list[dict], sha256: str, *, run_id: str, at: str, freeze_commit: str, assignments_sha256: str, reason: str) -> dict:
    """The ledger line that releases a used document. Raises ``ValueError`` unless the document is currently used and ``run_id`` is the
    run of its latest line, and unless the reason is stated. The caller appends it (``append_ledger``) after the owner has decided."""
    own = [r for r in records if r["sha256"] == sha256]
    if sha256 not in used_shas(records) or not own or own[-1]["run_id"] != run_id:
        raise ValueError("the document is not currently used by that run")
    if not reason.strip() or len(reason) > MAX_REASON:
        raise ValueError("a release states its reason")
    return dict(zip(RELEASE_MEMBERS, (own[-1]["document_id"], sha256, run_id, "released", at, freeze_commit, assignments_sha256, reason), strict=True))
