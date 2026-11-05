"""Statement runs (PRD FR-013 rule 6).

Consecutive selected pages that share a statement type form one statement run; the
first page of the run is "the first page of the statement" that FR-005.8 searches
for a scale or currency declaration. Derived from the locator result; the locator
itself is unchanged.

For the pages of a page range, which the locator does not classify, the run is worked
out from the pages given (PRD v0.4.74), by the locator's own page rules.
"""

from collections.abc import Mapping, Sequence

from credit_intel.config import LocatorSettings
from credit_intel.ingestion.locator import page_statement_types
from credit_intel.ingestion.models import LocatorResult, PageText


def run_start(types_by_page: Mapping[int, Sequence[str]], page_number: int, statement_type: str) -> int | None:
    """The first page of the run of ``statement_type`` that contains ``page_number``, or ``None`` if the page does not have that type."""
    if statement_type not in types_by_page.get(page_number, ()):
        return None
    start = page_number
    while statement_type in types_by_page.get(start - 1, ()):
        start -= 1
    return start


def statement_run_start(result: LocatorResult, page_number: int, statement_type: str) -> int | None:
    """The first page of the run of ``statement_type`` that contains ``page_number``.

    ``None`` when the locator did not select that page for that type (including a page
    range, which records no statement types): there is then no run to search here; see
    ``range_page_types`` for the pages of a range.
    """
    return run_start({c.page_number: c.statement_types for c in result.candidates}, page_number, statement_type)


def range_page_types(pages: Mapping[int, PageText], settings: LocatorSettings | None = None) -> dict[int, tuple[str, ...]]:
    """The statement types of the pages of a page range (PRD v0.4.74): the locator's own page rules (3a to 3c) over the pages given,
    with no cap and no exclusion. Used only to find the page whose scale and currency declaration a continuation page may rely on
    (FR-005.8); it selects no page and decides no basis."""
    return page_statement_types(list(pages.values()), settings)
