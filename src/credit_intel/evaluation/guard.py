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
from collections.abc import Mapping
from pathlib import Path

from credit_intel.config import ENV_PRIVATE_APPROVED

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSIGNMENTS_PATH = PROJECT_ROOT / "tests" / "eval" / "assignments.jsonl"
MEMBERS = ("document_id", "sha256", "set", "assigned_on", "event", "moved_from", "reason")


class SendRefused(Exception):
    """The document may not be sent to the hosted API. The message holds no document content."""


def is_private_path(path: Path) -> bool:
    """Whether the document sits in the owner's ``private/`` folder (the project's, or the current directory's), links followed.

    Only those two folders count, not any directory that happens to be called ``private`` (a system temporary directory
    can be, on macOS), so the rule is about the owner's real documents and nothing else.
    """
    target = path.expanduser().resolve()
    return any(target.is_relative_to((base / "private").resolve()) for base in (PROJECT_ROOT, Path.cwd()))


def check_private_path(path: Path, env: Mapping[str, str]) -> None:
    """Refuse a document under ``private/`` unless the owner approved this run (v0.4.31, SEC-10).

    The two tuning reports live there, so a run on them needs ``CREDIT_INTEL_PRIVATE_APPROVED=1`` in the environment of that
    run, set by the owner, and the document must also be recorded as tuning (``check_may_send``). Neither model is ever run on
    a document under ``private/`` otherwise. The message holds no path.
    """
    if is_private_path(path) and env.get(ENV_PRIVATE_APPROVED) != "1":
        raise SendRefused("a document under private/ may not be sent without the owner's approval of this run")


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


def refuse_if_held_out(sha256: str, assignments: Path = ASSIGNMENTS_PATH) -> None:
    """Refuse to look at a held-out document before the held-out evaluation run (PRD O.2).

    Reading its statement pages, even offline and counting only, is an inspection. A document
    that is on the record as tuning, or not on it at all, is not refused here (an unrecorded
    document is only an offline question). A missing or malformed record refuses everything.
    """
    known = load_current_sets(assignments).get(sha256)
    if known is not None and known[1] == "held_out":
        raise SendRefused(f"document {known[0]} is held out, so it may not be inspected before the held-out run")


def allow_held_out_send(sha256: str, assignments: Path = ASSIGNMENTS_PATH) -> str:
    """The neutral ID of a document recorded as held out, so that the held-out run tool may send it (PRD v0.4.41, O.2).

    This is the only way to send a held-out document and **one module calls it**: ``credit_intel.evaluation.heldout``
    (a test fails if any other module does). ``check_may_send`` keeps refusing a held-out document whatever the options.
    A document recorded as tuning, or not on the record, is refused here, so a held-out run never mislabels a tuning one.
    """
    known = load_current_sets(assignments).get(sha256)
    if known is None or known[1] != "held_out":
        raise SendRefused("the document is not recorded as held out")
    return known[0]
