"""Statement basis of a field, and the configured-basis filter (PRD H.4.6, D-06).

A statement's basis is read from the title block of a title line on its own page
(``title_block_bases``): exactly one basis named gives that basis; none or both gives
``unknown``. A page with no title line (a continuation page) takes the basis of the
first page of its statement run (FR-013 rule 6). Basis words elsewhere never decide it,
and a statement with no basis wording is not assumed to be standalone (OD-10).

Fields of a basis other than the configured one are ignored by the run, never mixed in
and never an error; the bases that were present are recorded for the memo.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from credit_intel.config import FIELD_STATEMENT_TYPES, LocatorSettings
from credit_intel.extraction.runs import statement_run_start
from credit_intel.ingestion.locator import title_block_bases
from credit_intel.ingestion.models import LocatorResult, PageText
from credit_intel.models import StatementBasis

CITED_PAGE = "cited_page"
RUN_START = "run_start"


def page_basis(page_text: str, settings: LocatorSettings | None = None) -> StatementBasis | None:
    """The basis the page's own title blocks give, or ``None`` if it has no title line.

    Several title blocks that do not all name the same single basis give ``unknown``.
    """
    blocks = title_block_bases(page_text, settings)
    if not blocks:
        return None
    names = {basis for _, basis in blocks}
    if len(names) == 1:  # one block basis, which may itself be "unknown"
        return StatementBasis(names.pop())
    return StatementBasis.UNKNOWN


def field_basis(
    field_name: str,
    page_number: int,
    pages: Mapping[int, PageText],
    located: LocatorResult,
    settings: LocatorSettings | None = None,
) -> tuple[StatementBasis, str | None]:
    """The basis of the statement a field was read from, and where it was read.

    The second item is ``CITED_PAGE``, ``RUN_START`` or ``None`` (no title line on the
    page or at the start of its run: the basis is ``unknown``).
    """
    page = pages.get(page_number)
    if page is None:
        return StatementBasis.UNKNOWN, None
    own = page_basis(page.text, settings)
    if own is not None:
        return own, CITED_PAGE
    start = statement_run_start(located, page_number, FIELD_STATEMENT_TYPES[field_name])
    first = pages.get(start) if start is not None and start != page_number else None
    if first is not None:
        inherited = page_basis(first.text, settings)
        if inherited is not None:
            return inherited, RUN_START
    return StatementBasis.UNKNOWN, None


@dataclass(frozen=True)
class BasisFilter:
    kept: tuple  # the items of the configured basis, and those with no basis to compare
    ignored: tuple  # the items of another known basis
    bases_present: tuple[str, ...]  # every known basis among the items, sorted


def filter_by_basis(items: Sequence, configured: str, basis_of) -> BasisFilter:
    """Keep the items of the ``configured`` basis (D-06).

    ``basis_of(item)`` gives an item's ``StatementBasis``, or ``None`` if it has none
    (it is kept, so the analyst sees it). An item of ``unknown`` basis is kept too: it
    may belong to the configured basis, and it is already ``requires_review``.
    """
    kept, ignored, present = [], [], set()
    for item in items:
        basis = basis_of(item)
        if basis is not None and basis is not StatementBasis.UNKNOWN:
            present.add(basis.value)
        if basis is None or basis is StatementBasis.UNKNOWN or basis.value == configured:
            kept.append(item)
        else:
            ignored.append(item)
    return BasisFilter(tuple(kept), tuple(ignored), tuple(sorted(present)))
