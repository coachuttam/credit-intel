"""Evidence presence (PRD FR-005.1 and FR-005.2).

The quote must occur on the cited page's text, and the raw value must occur within
the quote. Both comparisons use one normalisation only: NFKC, then every run of
whitespace (including line breaks) collapsed to a single space. There is no
case folding, punctuation folding or other fuzzy matching.
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass


def normalise_for_match(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


@dataclass(frozen=True)
class PresenceCheck:
    evidence_verified: bool  # FR-005.1: the quote is on the cited page
    value_in_evidence: bool  # FR-005.2: the raw value is in the quote


def check_presence(
    pages: Mapping[int, str], page_number: int, evidence_quote: str, raw_value: str
) -> PresenceCheck:
    """``pages`` maps the candidate page numbers to their text.

    A page that is not in ``pages`` (not a candidate, or not in the document) cannot
    support a quote. An empty quote or raw value, after normalisation, is never found.
    """
    quote = normalise_for_match(evidence_quote)
    raw = normalise_for_match(raw_value)
    page = pages.get(page_number)
    verified = page is not None and bool(quote) and quote in normalise_for_match(page)
    return PresenceCheck(evidence_verified=verified, value_in_evidence=bool(raw) and raw in quote)
