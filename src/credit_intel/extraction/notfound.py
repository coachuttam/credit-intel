"""What can be told of the pages sent when a source field was not found (PRD H.2, v0.4.75).

The code never concludes that the report presents none. It can tell three things, in this order:

* ``statement_not_in_pages_sent``: none of the pages sent is a page of the statement the field is read from (income statement or
  balance sheet: the locator's statement types, or, for a page range, the locator's own page rules over the pages given, v0.4.74);
* ``no_recognised_row``: the statement is among the pages sent and no line on those pages is a row (it holds a figure) whose label the
  configured list accepts for the field. The report may print the row under another name;
* ``recognised_row_not_read``: a row whose label the list accepts is on those pages and the field was still not read.

The same row-label check as FR-005.10 is used, on every line of the statement pages. It informs only: it changes no status.
"""

from collections.abc import Mapping

from credit_intel.config import FIELD_STATEMENT_TYPES, LabelSettings, LocatorSettings
from credit_intel.extraction.labels import check_label
from credit_intel.extraction.runs import range_page_types
from credit_intel.ingestion.locator import PAGE_RANGE, is_nil_token, is_numeric_token, lines_of
from credit_intel.ingestion.models import LocatorResult, PageText
from credit_intel.models import FieldName, StatusReason


def _is_row(line: str) -> bool:
    return any(is_numeric_token(word) or is_nil_token(word) for word in line.split())


def not_found_reason(
    name: FieldName,
    located: LocatorResult,
    pages: Mapping[int, PageText],
    label_settings: LabelSettings | None = None,
    locator_settings: LocatorSettings | None = None,
) -> StatusReason:
    """The reason a source field of the given name reads ``not_found``, from the pages sent (``pages``, the candidate pages)."""
    kind = FIELD_STATEMENT_TYPES[name.value]
    if located.method == PAGE_RANGE:
        types = {number: set(found) for number, found in range_page_types(pages, locator_settings).items()}
    else:
        types = {c.page_number: set(c.statement_types) for c in located.candidates}
    statement_pages = [number for number in sorted(pages) if kind in types.get(number, ())]
    if not statement_pages:
        return StatusReason.STATEMENT_NOT_IN_PAGES_SENT
    for number in statement_pages:
        lines = list(lines_of(pages[number].text))
        for index, line in enumerate(lines):
            if _is_row(line) and check_label(name.value, line, lines, index, label_settings).ok:
                return StatusReason.RECOGNISED_ROW_NOT_READ
    return StatusReason.NO_RECOGNISED_ROW
