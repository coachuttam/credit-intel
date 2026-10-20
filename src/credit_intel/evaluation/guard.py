"""Which documents may be sent to the hosted API (PRD SEC-10, the owner's G2 rule).

The G2 rule (``PROGRESS.md``) allows synthetic documents and the public tuning reports
recorded in ``tests/eval/assignments.jsonl``, and nothing else: no held-out document until
the held-out run, and no document that is not on the record. The live tuning runner calls
``check_may_send`` before anything is sent. It fails closed: a missing or malformed record
refuses every document, and the refusal never prints more than a short hash.

A document's current set is the set of its last record, so a ``moved`` line (held out to
tuning after inspection, O.2) takes effect.
"""

import hashlib
import json
from pathlib import Path

ASSIGNMENTS_PATH = Path(__file__).resolve().parents[3] / "tests" / "eval" / "assignments.jsonl"
MEMBERS = ("document_id", "sha256", "set", "assigned_on", "event", "moved_from", "reason")


class SendRefused(Exception):
    """The document may not be sent to the hosted API. The message holds no document content."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_current_sets(path: Path = ASSIGNMENTS_PATH) -> dict[str, tuple[str, str]]:
    """``{sha256: (document_id, set)}`` from the last record of each document.

    Raises ``SendRefused`` if the file is missing or any line is not a valid record.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SendRefused("the assignment record cannot be read") from exc
    current: dict[str, tuple[str, str]] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError as exc:
            raise SendRefused(f"the assignment record is malformed (line {number})") from exc
        if (
            not isinstance(record, dict)
            or tuple(record) != MEMBERS
            or record["set"] not in ("tuning", "held_out")
            or not isinstance(record["sha256"], str)
            or not isinstance(record["document_id"], str)
        ):
            raise SendRefused(f"the assignment record is malformed (line {number})")
        current[record["sha256"]] = (record["document_id"], record["set"])
    return current


def check_may_send(sha256: str, assignments: Path = ASSIGNMENTS_PATH, *, synthetic: bool = False) -> str:
    """The neutral document ID if the document may be sent, else ``SendRefused``.

    ``synthetic=True`` is for tests that build their own documents; the live runner never
    passes it, and a test checks that.
    """
    if synthetic:
        return "synthetic"
    known = load_current_sets(assignments).get(sha256)
    if known is None:
        raise SendRefused(f"document {sha256[:12]} is not on the assignment record, so it may not be sent")
    document_id, current_set = known
    if current_set != "tuning":
        raise SendRefused(f"document {document_id} is not a tuning document, so it may not be sent")
    return document_id
