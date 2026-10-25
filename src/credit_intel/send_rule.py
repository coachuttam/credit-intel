"""When the command line may send a document's statement pages to the hosted API (PRD SEC-10, the owner's G2 rule; Phase 5 step 5k).

The tuning runner (``evaluation/guard.py``) sends only documents recorded as tuning. A product command line
used on an analyst's own public report would meet that rule on every run, so the command line has this one
(decision 1 of the Phase 5 plan):

* a document recorded as **held out** is never sent, whatever the flags (O.2: no held-out document before the
  held-out run);
* a document recorded as **tuning** is sent;
* a document **not on the record**, or any document when there is no record file (an installed copy), is sent
  only when the analyst has confirmed with ``--confirm-public-document`` that it is public;
* a record that exists but cannot be read fails closed and refuses every document.

The rule applies only when the configured provider sends data off the machine.
"""

from pathlib import Path

from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, load_current_sets

NOTICE = ("Notice: the candidate statement pages of this document will be sent to the hosted API. "
          "Only public or synthetic documents may be sent (SEC-10).")  # fmt: skip


def check_send(sha256: str, *, external: bool, confirmed: bool, assignments: Path = ASSIGNMENTS_PATH) -> str:
    """``"local"``, ``"tuning"`` or ``"confirmed"`` if the document may be sent, else ``SendRefused`` (no document content in its message)."""
    if not external:
        return "local"
    known = load_current_sets(assignments).get(sha256) if assignments.exists() else None
    if known is not None and known[1] == "held_out":
        raise SendRefused(f"document {known[0]} is held out, so it may not be sent")
    if known is not None:
        return "tuning"
    if not confirmed:
        raise SendRefused("this document is not on the assignment record; to send its statement pages to the hosted API, "
                          "confirm that it is public with --confirm-public-document")  # fmt: skip
    return "confirmed"
