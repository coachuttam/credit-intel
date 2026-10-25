"""The analyst's assertion of the statement basis for the pages of a ``--pages`` run (PRD H.4.6, v0.4.24; OD-10 option 3).

``apply_assertion`` decides, for each page of the range, whether the assertion applies to it:

* a page whose own title block names exactly one basis keeps it (the evidence is the title);
* a page whose basis is the other one than the asserted basis is a **conflict**: the run stops before any
  model call with ``E-EXTRACT-BASIS-UNAVAILABLE``, naming the pages. The assertion never overrides a page's own
  evidence, and a conflicting page is not skipped;
* every other page (no title line, a title block naming no basis, or naming both) has the basis ``unknown``
  by the rules of H.4.6, and the assertion applies to it.

A page range has no statement runs (FR-013 rule 7), so a page with no title line is not given the basis of an
earlier page: it is a page the assertion applies to. Only the decision is made here. How a field and the
``statement_basis`` attribute use it is the next step of the implementation.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from credit_intel.config import LocatorSettings
from credit_intel.extraction.bases import page_basis
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import LocatorResult, PageText
from credit_intel.models import StatementBasis

ASSERTABLE = (StatementBasis.CONSOLIDATED, StatementBasis.STANDALONE)


@dataclass(frozen=True)
class BasisAssertion:
    """What the analyst asserted and where it was needed."""

    basis: StatementBasis
    pages: tuple[int, ...]  # the pages of the range, ascending
    applied_pages: tuple[int, ...]  # the pages whose basis was ``unknown`` and so took the asserted basis, ascending


def apply_assertion(
    pages: Mapping[int, PageText],
    located: LocatorResult,
    asserted: StatementBasis,
    settings: LocatorSettings | None = None,
) -> BasisAssertion:
    """Decide where the assertion applies, or raise ``E-EXTRACT-BASIS-UNAVAILABLE`` if a page names the other basis."""
    if asserted not in ASSERTABLE:
        raise ValueError("the asserted basis is consolidated or standalone")
    if located.method != "page_range":
        raise ValueError("an assertion is for a page range")
    applied: list[int] = []
    conflicting: list[int] = []
    for candidate in sorted(located.candidates, key=lambda c: c.page_number):
        own = page_basis(pages[candidate.page_number].text, settings)
        if own is None or own is StatementBasis.UNKNOWN:
            applied.append(candidate.page_number)
        elif own is not asserted:
            conflicting.append(candidate.page_number)
    if conflicting:
        listed = ", ".join(str(n) for n in conflicting)
        raise IngestionError(
            ErrorCode.BASIS_UNAVAILABLE,
            detail=f"asserted basis: {asserted.value}; pages whose title names the other basis: {listed}",
        )
    return BasisAssertion(asserted, tuple(sorted(c.page_number for c in located.candidates)), tuple(applied))
