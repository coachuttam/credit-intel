"""The labels a page classifier gives a page, and what each may cause (PRD v0.4.31).

A label is advice about which pages the extraction model needs. It is never evidence: nothing in a field, a
verification record or the memo's origin labels refers to it.
"""

from dataclasses import dataclass
from enum import StrEnum


class PageType(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    PROFIT_LOSS = "profit_loss"
    CASH_FLOW = "cash_flow"
    NOTES = "notes"
    OTHER = "other"


class PageBasis(StrEnum):
    STANDALONE = "standalone"
    CONSOLIDATED = "consolidated"
    UNCLEAR = "unclear"


# A page the extraction model does not need. Notes are never here: interest expense and borrowings often sit in a note.
DROPPABLE_TYPES = frozenset({PageType.CASH_FLOW, PageType.OTHER})


@dataclass(frozen=True)
class PageClassification:
    """What a classifier said about one page. Confidences are 0 to 1; ``probabilities`` keep the full answer for evaluation."""

    page_type: PageType
    type_confidence: float
    basis: PageBasis
    basis_confidence: float
    model_id: str  # the versioned ID that answered (an alias such as jev-latest moves)
    input_tokens: int
    latency_ms: int
    cached: bool = False
    type_probabilities: tuple[tuple[str, float], ...] = ()
    basis_probabilities: tuple[tuple[str, float], ...] = ()


class ClassifierError(Exception):
    """A classification failed. ``reason`` is one of ``FAILURE_REASONS``; the message is the reason and never a document's text."""

    def __init__(self, reason: str) -> None:
        if reason not in FAILURE_REASONS:
            raise ValueError("an unknown failure reason")
        super().__init__(reason)
        self.reason = reason


FAILURE_REASONS = (
    "timeout",
    "connection",
    "rate_limit",
    "auth",
    "bad_request",
    "server",
    "invalid_reply",
    "sdk_error",
    "error",
)
