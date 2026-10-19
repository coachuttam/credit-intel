"""Statement runs (PRD FR-013 rule 6).

Consecutive selected pages that share a statement type form one statement run; the
first page of the run is "the first page of the statement" that FR-005.8 searches
for a scale or currency declaration. Derived from the locator result; the locator
itself is unchanged.
"""

from credit_intel.ingestion.models import LocatorResult


def statement_run_start(result: LocatorResult, page_number: int, statement_type: str) -> int | None:
    """The first page of the run of ``statement_type`` that contains ``page_number``.

    ``None`` when the locator did not select that page for that type (including a page
    range, which records no statement types): there is then no run to search.
    """
    types_by_page = {c.page_number: c.statement_types for c in result.candidates}
    if statement_type not in types_by_page.get(page_number, ()):
        return None
    start = page_number
    while statement_type in types_by_page.get(start - 1, ()):
        start -= 1
    return start
