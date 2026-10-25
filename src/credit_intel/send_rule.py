"""When the command line may send a document's statement pages to the hosted API (PRD SEC-10, the owner's G2 rule; Phase 5 step 5k).

The tuning runner (``evaluation/guard.py``) sends only documents recorded as tuning. A product command line
used on an analyst's own public report would meet that rule on every run, so the command line has this one
(decision 1 of the Phase 5 plan):

* a document recorded as **held out** is never sent, whatever the flags (O.2: no held-out document before the
  held-out run);
* a document recorded as **tuning** is sent;
* a document **not on the record**, or any document when there is no record file (an installed copy), is sent
  only when the analyst has confirmed with ``--confirm-public-document`` that it is public;
* a record that exists but cannot be read fails closed and refuses every document;
* a document under a ``private/`` directory is sent only if it is recorded as tuning **and** the owner approved this run with
  ``CREDIT_INTEL_PRIVATE_APPROVED=1`` (PRD v0.4.31); otherwise it is refused as ``private_path``, even with the confirmation.

The rule applies only when the configured provider sends data off the machine.

A refusal is the catalogued failure ``E-INPUT-SEND-REFUSED`` (PRD v0.4.27). ``check_send`` raises ``SendRefusal`` with one of three fixed
reason words, which the command line appends to the message: ``held_out``, ``not_recorded``, ``record_unreadable`` or ``private_path``. Nothing else is
carried, so a refusal can never show a hash, a path or a document's neutral ID.
"""

from pathlib import Path

from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, is_private_path, load_current_sets

NOTICE = ("Notice: the candidate statement pages of this document will be sent to the hosted API. "
          "Only public or synthetic documents may be sent (SEC-10).")  # fmt: skip


REASONS = ("held_out", "not_recorded", "record_unreadable", "private_path")


class SendRefusal(SendRefused):
    """A document may not be sent. ``reason`` is one of ``REASONS``; the message is the reason and nothing more."""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError("an unknown reason for refusing to send")
        super().__init__(reason)
        self.reason = reason


def check_send(
    sha256: str,
    *,
    external: bool,
    confirmed: bool,
    assignments: Path = ASSIGNMENTS_PATH,
    path: Path | None = None,
    private_approved: bool = False,
) -> str:
    """``"local"``, ``"tuning"`` or ``"confirmed"`` if the document may be sent, else ``SendRefusal`` with a fixed reason word."""
    if not external:
        return "local"
    try:
        known = load_current_sets(assignments).get(sha256) if assignments.exists() else None
    except SendRefused as error:  # the record exists but cannot be read: the rule fails closed
        raise SendRefusal("record_unreadable") from error
    if known is not None and known[1] == "held_out":
        raise SendRefusal("held_out")
    if path is not None and is_private_path(path) and not (private_approved and known is not None):
        raise SendRefusal("private_path")
    if known is not None:
        return "tuning"
    if not confirmed:
        raise SendRefusal("not_recorded")
    return "confirmed"
