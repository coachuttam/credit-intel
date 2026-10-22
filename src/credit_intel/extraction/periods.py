"""Period-end validation (PRD FR-005.9, H.1.1, D-11; Phase 2 step 7a).

A period-end is accepted only in the forms FR-005.9 lists; anything else is never
guessed. This module has no I/O and no dependency on a model's output:

- ``parse_full_date``: a written date, an ISO date, or an unambiguous numeric date,
  optionally preceded by "as at", "as of", "year ended" or "for the year ended";
- ``parse_year_token``: a year-only or financial-year header (``2025``, ``FY2025``,
  ``2024-25``, ``FY 2024-25``), reduced to its (later) year;
- ``resolve_anchor_texts``: which anchors validate, and how (a full date; a year token
  matched by the one full date of that year in the page's title or column-header block; or the comparative derived
  from the current period, v0.4.13);
- ``periods_are_consecutive``: the consecutive-period rule (H.1.1);
- ``page_period_resolver``: the ``resolve_period`` callable the column check (6b) takes.
"""

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from credit_intel.config import ColumnSettings, LocatorSettings
from credit_intel.extraction.columns import PeriodAnchor, find_anchors, group_lines, header_block
from credit_intel.ingestion.locator import is_figure_word, lines_of
from credit_intel.ingestion.models import PageWords

_MONTH_NUMBERS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
_MONTH = "|".join(sorted(_MONTH_NUMBERS, key=len, reverse=True))
_PREFIX = r"(?:(?:for the year ended|year ended|as at|as of)\s+)?"
_DAY = r"(?P<{}>[0-9]{{1,2}})(?:st|nd|rd|th)?,?"

_DAY_MONTH_YEAR = rf"{_DAY.format('d1')}\s+(?P<m1>{_MONTH})\.?\s+(?P<y1>[0-9]{{4}})"
_MONTH_DAY_YEAR = rf"(?P<m2>{_MONTH})\.?\s+{_DAY.format('d2')}\s+(?P<y2>[0-9]{{4}})"
_ISO = r"(?P<y3>[0-9]{4})-(?P<m3>[0-9]{2})-(?P<d3>[0-9]{2})"
_NUMERIC = r"(?P<a>[0-9]{1,2})(?P<sep>[./-])(?P<b>[0-9]{1,2})(?P=sep)(?P<y4>[0-9]{4})"
_FORMS = f"(?:{_DAY_MONTH_YEAR}|{_MONTH_DAY_YEAR}|{_ISO}|{_NUMERIC})"

_FULL_DATE = re.compile(rf"{_PREFIX}{_FORMS}", re.IGNORECASE)
# In page text a date must not be glued to other digits or date separators.
_SCAN = re.compile(rf"(?<![0-9./-]){_PREFIX}{_FORMS}(?![0-9])", re.IGNORECASE)
_YEAR_TOKEN = re.compile(r"(?:FY\s?)?(?P<start>[0-9]{4})(?:-(?P<end>[0-9]{2}))?", re.IGNORECASE)


class Form(StrEnum):
    """What an anchor's text is, before any check against the page."""

    FULL_DATE = "full_date"
    AMBIGUOUS_NUMERIC_DATE = "ambiguous_numeric_date"
    INVALID_DATE = "invalid_date"
    YEAR_TOKEN = "year_token"
    BAD_FINANCIAL_YEAR = "bad_financial_year"
    UNRECOGNISED = "unrecognised"


class Method(StrEnum):
    FULL_DATE = "full_date"
    YEAR_WITH_PAGE_DATE = "year_with_page_date"
    DERIVED_COMPARATIVE = "derived_comparative"


class Reason(StrEnum):
    """Why an anchor is not validated (always reported as ``period_mismatch``, FR-005.9)."""

    UNRECOGNISED_FORM = "unrecognised_form"
    AMBIGUOUS_NUMERIC_DATE = "ambiguous_numeric_date"
    INVALID_DATE = "invalid_date"
    BAD_FINANCIAL_YEAR = "bad_financial_year"
    AMBIGUOUS_PAGE_DATE = "ambiguous_page_date"
    NO_VALIDATED_CURRENT = "no_validated_current"
    NOT_ONE_YEAR_EARLIER = "not_one_year_earlier"
    CURRENT_ENDS_IN_FEBRUARY = "current_ends_in_february"


@dataclass(frozen=True)
class PeriodEvidence:
    """A validated period-end with its raw text (H.1.2) and how it was validated."""

    raw_text: str
    period_end: date
    method: Method
    derived_from: date | None = None  # the current period-end, for a derived comparative


@dataclass(frozen=True)
class PeriodResolution:
    evidence: PeriodEvidence | None
    reason: Reason | None = None


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _build(match: re.Match[str]) -> tuple[Form, date | None]:
    groups = match.groupdict()
    try:
        if groups["y1"]:
            return Form.FULL_DATE, date(int(groups["y1"]), _MONTH_NUMBERS[groups["m1"].lower()], int(groups["d1"]))
        if groups["y2"]:
            return Form.FULL_DATE, date(int(groups["y2"]), _MONTH_NUMBERS[groups["m2"].lower()], int(groups["d2"]))
        if groups["y3"]:
            return Form.FULL_DATE, date(int(groups["y3"]), int(groups["m3"]), int(groups["d3"]))
        first, second, year = int(groups["a"]), int(groups["b"]), int(groups["y4"])
    except ValueError:
        return Form.INVALID_DATE, None
    if first == 0 or second == 0:
        return Form.INVALID_DATE, None
    # A numeric date is read one way only: day and month equal, or one greater than 12.
    if first == second or (first > 12 and second <= 12):
        day, month = first, second
    elif second > 12 and first <= 12:
        day, month = second, first
    elif first <= 12 and second <= 12:
        return Form.AMBIGUOUS_NUMERIC_DATE, None
    else:
        return Form.INVALID_DATE, None
    try:
        return Form.FULL_DATE, date(year, month, day)
    except ValueError:
        return Form.INVALID_DATE, None


def parse_full_date(text: str) -> date | None:
    """The date in ``text`` if it is exactly one accepted full-date form, else ``None``."""
    match = _FULL_DATE.fullmatch(_normalise(text))
    if match is None:
        return None
    form, value = _build(match)
    return value if form is Form.FULL_DATE else None


def parse_year_token(text: str) -> int | None:
    """The (later) year of a year-only or financial-year header, else ``None``.

    ``2024-25`` is the year 2025; the two-digit end must be the year after the start,
    modulo 100 (so ``1999-00`` is 2000 and ``2024-26`` is not a financial year).
    """
    match = _YEAR_TOKEN.fullmatch(_normalise(text))
    if match is None:
        return None
    start = int(match["start"])
    if match["end"] is None:
        return start
    return start + 1 if int(match["end"]) == (start + 1) % 100 else None


def classify(text: str) -> Form:
    """Which form an anchor's text has (for reporting and the 6b agreement test)."""
    clean = _normalise(text)
    match = _FULL_DATE.fullmatch(clean)
    if match is not None:
        return _build(match)[0]
    if _YEAR_TOKEN.fullmatch(clean):
        return Form.YEAR_TOKEN if parse_year_token(clean) is not None else Form.BAD_FINANCIAL_YEAR
    return Form.UNRECOGNISED


def find_full_dates(page_text: str) -> frozenset[date]:
    """Every full date in an accepted form that appears in ``page_text``.

    Ambiguous numeric dates and impossible dates are not dates here.
    """
    found: set[date] = set()
    for line in lines_of(page_text):
        for match in _SCAN.finditer(line):
            value = _build(match)[1]  # None for an ambiguous or impossible date
            if value is not None:
                found.add(value)
    return frozenset(found)


def header_lines(page_text: str) -> tuple[str, ...]:
    """The lines above the page's first figure line: its title and column-header block
    (FR-005.9, v0.4.20). The same region the period-end quote must come from (H.1.2)."""
    lines = lines_of(page_text)
    stop = next((i for i, line in enumerate(lines) if any(is_figure_word(w) for w in line.split())), len(lines))
    return lines[:stop]


def find_header_dates(page_text: str) -> frozenset[date]:
    """Every full date in an accepted form in the page's title and column-header block.

    A date whose words are on two consecutive lines of the block is read as one date
    (v0.4.20). Nothing is joined across a figure line, because the block ends there, and
    a date elsewhere on the page (a signature block, a note) is not found.
    """
    lines = header_lines(page_text)
    windows = [*lines, *(f"{a} {b}" for a, b in zip(lines, lines[1:]))]
    found: set[date] = set()
    for window in windows:
        for match in _SCAN.finditer(window):
            value = _build(match)[1]  # None for an ambiguous or impossible date
            if value is not None:
                found.add(value)
    return frozenset(found)


def header_year_tokens(page_text: str) -> tuple[tuple[str, str], ...]:
    """Year-only and financial-year tokens in the page's title and column-header block,
    each with the header line that holds it, in reading order (FR-005.9, v0.4.22).

    A word that belongs to a full date (even a wrapped one, or an ambiguous one) is not a
    year header: ``2024`` in ``31 March 2024`` is part of a date, and a date elsewhere in the
    block must not stand in for a heading. ``FY`` followed by a token is read as one token.
    """
    lines = header_lines(page_text)
    joined = "\n".join(lines)
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    covered = [match.span() for match in _SCAN.finditer(joined)]

    def free(span: tuple[int, int]) -> bool:
        return not any(span[0] < end and start < span[1] for start, end in covered)

    def line_of(offset: int) -> str:
        index = max(i for i, start in enumerate(starts) if start <= offset)
        return lines[index]

    words = [(m.group(), m.span()) for m in re.finditer(r"\S+", joined)]
    found: list[tuple[str, str]] = []
    joined_with_previous = False  # this word was read as the number of an "FY 2024-25" token
    for i, (word, span) in enumerate(words):
        if joined_with_previous:
            joined_with_previous = False
            continue
        if not free(span):
            continue
        if word.casefold() == "fy" and i + 1 < len(words):
            follower, follower_span = words[i + 1]
            if free(follower_span) and line_of(follower_span[0]) == line_of(span[0]):
                combined = f"{word} {follower}"
                if parse_year_token(combined) is not None:
                    found.append((combined, line_of(span[0])))
                    joined_with_previous = True
                    continue
        if parse_year_token(word) is not None:
            found.append((word, line_of(span[0])))
    return tuple(found)


def _is_february_end(day: date) -> bool:
    return day.month == 2 and day.day in (28, 29)


def periods_are_consecutive(current: date, comparative: date) -> bool:
    """H.1.1: the comparative ends in the previous calendar year on the same month and
    day; 28 and 29 February count as the same day."""
    if comparative.year != current.year - 1:
        return False
    if _is_february_end(current) and _is_february_end(comparative):
        return True
    return (comparative.month, comparative.day) == (current.month, current.day)


_REASONS_BY_FORM = {
    Form.UNRECOGNISED: Reason.UNRECOGNISED_FORM,
    Form.AMBIGUOUS_NUMERIC_DATE: Reason.AMBIGUOUS_NUMERIC_DATE,
    Form.INVALID_DATE: Reason.INVALID_DATE,
    Form.BAD_FINANCIAL_YEAR: Reason.BAD_FINANCIAL_YEAR,
}


def resolve_anchor_texts(
    anchor_texts: Iterable[str], page_text: str, known_current: date | None = None
) -> dict[str, PeriodResolution]:
    """Validate each distinct anchor text of one statement page (FR-005.9).

    A full date validates itself. A year token is validated only by the one full date
    of that year on the page (none, or two different ones, is not guessed). Then a year
    token exactly one year before the current period (the latest validated period-end)
    is validated as the comparative, with the same month and day, unless the current
    period ends on 28 or 29 February. ``known_current`` is a current period-end already
    validated by a full date elsewhere (on another page); it counts as validated here.
    """
    texts = list(dict.fromkeys(anchor_texts))
    page_dates = find_header_dates(page_text)  # v0.4.20: not a date elsewhere on the page
    results: dict[str, PeriodResolution] = {}
    pending: dict[str, int] = {}

    for text in texts:
        form = classify(text)
        if form is Form.FULL_DATE:
            day = parse_full_date(text)
            assert day is not None
            results[text] = PeriodResolution(PeriodEvidence(text, day, Method.FULL_DATE))
        elif form is Form.YEAR_TOKEN:
            year = parse_year_token(text)
            assert year is not None
            same_year = sorted(d for d in page_dates if d.year == year)
            if len(same_year) == 1:
                evidence = PeriodEvidence(text, same_year[0], Method.YEAR_WITH_PAGE_DATE)
                results[text] = PeriodResolution(evidence)
            elif len(same_year) > 1:
                results[text] = PeriodResolution(None, Reason.AMBIGUOUS_PAGE_DATE)
            else:
                pending[text] = year
        else:
            results[text] = PeriodResolution(None, _REASONS_BY_FORM[form])

    validated = [r.evidence.period_end for r in results.values() if r.evidence is not None]
    current = max([*validated, *([known_current] if known_current else [])], default=None)
    for text, year in pending.items():
        if current is None:
            results[text] = PeriodResolution(None, Reason.NO_VALIDATED_CURRENT)
        elif year != current.year - 1:
            results[text] = PeriodResolution(None, Reason.NOT_ONE_YEAR_EARLIER)
        elif _is_february_end(current):
            results[text] = PeriodResolution(None, Reason.CURRENT_ENDS_IN_FEBRUARY)
        else:
            derived = date(year, current.month, current.day)
            evidence = PeriodEvidence(text, derived, Method.DERIVED_COMPARATIVE, derived_from=current)
            results[text] = PeriodResolution(evidence)
    return {text: results[text] for text in texts}


def page_period_resolver(
    page: PageWords,
    page_text: str,
    settings: ColumnSettings | None = None,
    locator_settings: LocatorSettings | None = None,
    known_current: date | None = None,
) -> Callable[[PeriodAnchor], date | None]:
    """The ``resolve_period`` argument of ``analyse_structure`` for one page.

    The anchors are found the same way ``analyse_structure`` finds them (the header
    block of the page's word-lines), so the two always agree. A rotated page has none.
    ``known_current`` is a current period-end validated on another page.
    """
    if page.rotation != 0:
        return lambda anchor: None
    settings = settings or ColumnSettings()
    lines = group_lines(page.words, settings.line_tolerance_pt)
    first, last = header_block(lines, locator_settings)
    resolutions = resolve_anchor_texts(
        (anchor.text for anchor in find_anchors(lines[first:last])), page_text, known_current
    )

    def resolve(anchor: PeriodAnchor) -> date | None:
        found = resolutions.get(anchor.text)
        return found.evidence.period_end if found and found.evidence else None

    return resolve
