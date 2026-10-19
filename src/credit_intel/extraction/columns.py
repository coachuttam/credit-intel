"""Page structure for the period-column check (PRD FR-005.7, OD-1 step 6b).

From the words of one page this finds the lines (3.2), the header block, the
period anchors (3.3), the column regions and the note span, the label limit
(3.4), and whether the structure is valid (S). It assigns no values: that is 6c.

Which period an anchor stands for is decided by FR-005.9, which is built later,
so the caller passes ``resolve_period``. It is called once for each anchor in
the header block and returns the anchor's validated period-end, or ``None``.
Geometry on a rotated page is unusable, so a rotated page is never analysed.
"""

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from credit_intel.config import ColumnSettings, LocatorSettings
from credit_intel.ingestion.locator import is_figure_word, title_lines
from credit_intel.ingestion.models import PageWords, Word

NOTE_HEADER_WORDS = frozenset({"note", "notes"})

_MONTHS = (
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec"
).split()
_MONTH = re.compile(rf"(?:{'|'.join(_MONTHS)})\.?", re.IGNORECASE)
_DAY = re.compile(r"[0-9]{1,2}(?:st|nd|rd|th)?,?", re.IGNORECASE)
_YEAR = re.compile(r"[0-9]{4}")
_FINANCIAL_YEAR = re.compile(r"(?:FY[0-9]{4}(?:-[0-9]{2})?|[0-9]{4}-[0-9]{2})", re.IGNORECASE)
_FY_PREFIXED = re.compile(r"[0-9]{4}(?:-[0-9]{2})?")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NUMERIC_DATE = re.compile(r"[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4}")

KIND_DATE = "date"
KIND_YEAR = "year"
KIND_FINANCIAL_YEAR = "financial_year"


class StructureProblem(StrEnum):
    """Why a page's structure is not valid (S) or has no usable anchor (3.3)."""

    ROTATED = "rotated"
    NO_USABLE_ANCHOR = "no_usable_anchor"
    UNVALIDATED_ANCHOR = "unvalidated_anchor"
    OVERLAPPING_REGIONS = "overlapping_regions"
    DUPLICATE_PERIOD_COLUMN = "duplicate_period_column"


@dataclass(frozen=True)
class Line:
    """One word-line: words in ``(x0, text)`` order, text NFKC-normalised."""

    index: int
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


@dataclass(frozen=True)
class PeriodAnchor:
    """Words that carry a period in an FR-005.9 accepted form, in the header block."""

    text: str
    kind: str  # KIND_DATE, KIND_YEAR or KIND_FINANCIAL_YEAR
    x0: float
    x1: float
    top: float
    bottom: float
    line_index: int
    period_end: date | None = None  # the validated period-end, once resolved


@dataclass(frozen=True)
class Column:
    """A period column: its validated period-end and its region in points."""

    period_end: date
    x0: float
    x1: float
    anchors: tuple[PeriodAnchor, ...]


@dataclass(frozen=True)
class NoteSpan:
    x0: float
    x1: float


@dataclass(frozen=True)
class PageStructure:
    page_number: int
    lines: tuple[Line, ...]
    header_first: int  # header block: lines[header_first:header_last]
    header_last: int
    anchors: tuple[PeriodAnchor, ...]
    columns: tuple[Column, ...]
    note_span: NoteSpan | None
    label_limit: float | None
    problems: tuple[StructureProblem, ...]

    @property
    def valid(self) -> bool:
        return not self.problems


PeriodResolver = Callable[[PeriodAnchor], date | None]


def clean_text(text: str) -> str:
    # NFKC, then single spaces, so a word never carries a line separator.
    return " ".join(unicodedata.normalize("NFKC", text).split())


def group_lines(words: Iterable[Word], line_tolerance_pt: float = 3) -> tuple[Line, ...]:
    """Lines of words (3.2).

    Words are sorted by ``(cy, x0, text)``; a new line starts when a word's vertical
    centre exceeds the previous word's by more than the tolerance. Within a line
    the order is ``(x0, text)``. Words that are empty after NFKC are dropped.
    """
    cleaned = [replace(w, text=clean_text(w.text)) for w in words]
    cleaned = [w for w in cleaned if w.text]
    ordered = sorted(cleaned, key=lambda w: ((w.top + w.bottom) / 2, w.x0, w.text))
    groups: list[list[Word]] = []
    previous_cy: float | None = None
    for word in ordered:
        cy = (word.top + word.bottom) / 2
        if previous_cy is None or cy - previous_cy > line_tolerance_pt:
            groups.append([])
        groups[-1].append(word)
        previous_cy = cy
    return tuple(
        Line(index, tuple(sorted(group, key=lambda w: (w.x0, w.text))))
        for index, group in enumerate(groups)
    )


# --- header block ---------------------------------------------------------------


def header_block(
    lines: Sequence[Line], locator_settings: LocatorSettings | None = None
) -> tuple[int, int]:
    """``(first, last)`` line indexes, the block being ``lines[first:last]``.

    It lies below the page's last title line (G.0, evaluated on the lines' text)
    and above its first figure line (a line holding a figure word, G.0).
    """
    text = "\n".join(line.text for line in lines)
    titles = title_lines(text, locator_settings)
    first = max((t.line_index + t.line_count for t in titles), default=0)
    last = next(
        (
            line.index
            for line in lines
            if any(is_figure_word(word.text) for word in line.words)
        ),
        len(lines),
    )
    return first, max(first, last)


# --- anchors --------------------------------------------------------------------


def _adjacent(left: Word, right: Word) -> bool:
    """Provisional adjacency test (P-3): the gap is at most the mean of the two
    words' average character widths. Not validated against real reports."""

    def char_width(word: Word) -> float:
        return (word.x1 - word.x0) / len(word.text)

    return right.x0 - left.x1 <= (char_width(left) + char_width(right)) / 2


def _run_adjacent(words: Sequence[Word]) -> bool:
    return all(_adjacent(a, b) for a, b in zip(words, words[1:]))


def _written_date(texts: Sequence[str]) -> bool:
    day_month_year = (
        _DAY.fullmatch(texts[0]) and _MONTH.fullmatch(texts[1]) and _YEAR.fullmatch(texts[2])
    )
    month_day_year = (
        _MONTH.fullmatch(texts[0]) and _DAY.fullmatch(texts[1]) and _YEAR.fullmatch(texts[2])
    )
    return bool(day_month_year or month_day_year)


def _anchor_at(words: Sequence[Word], i: int) -> tuple[int, str] | None:
    """The number of words and kind of the anchor starting at ``words[i]``, if any."""
    three = words[i : i + 3]
    if len(three) == 3 and _written_date([w.text for w in three]) and _run_adjacent(three):
        return 3, KIND_DATE
    text = words[i].text
    if _ISO_DATE.fullmatch(text) or _NUMERIC_DATE.fullmatch(text):
        return 1, KIND_DATE
    if text.casefold() == "fy" and i + 1 < len(words):
        follower = words[i + 1]
        if _FY_PREFIXED.fullmatch(follower.text) and _adjacent(words[i], follower):
            return 2, KIND_FINANCIAL_YEAR
    if _FINANCIAL_YEAR.fullmatch(text):
        return 1, KIND_FINANCIAL_YEAR
    if _YEAR.fullmatch(text):
        return 1, KIND_YEAR
    return None


def find_anchors(lines: Sequence[Line]) -> tuple[PeriodAnchor, ...]:
    """Period anchors in ``lines``, left to right within each line."""
    anchors: list[PeriodAnchor] = []
    for line in lines:
        i = 0
        while i < len(line.words):
            found = _anchor_at(line.words, i)
            if found is None:
                i += 1
                continue
            count, kind = found
            span = line.words[i : i + count]
            anchors.append(
                PeriodAnchor(
                    text=" ".join(w.text for w in span),
                    kind=kind,
                    x0=min(w.x0 for w in span),
                    x1=max(w.x1 for w in span),
                    top=min(w.top for w in span),
                    bottom=max(w.bottom for w in span),
                    line_index=line.index,
                )
            )
            i += count
    return tuple(anchors)


# --- columns and structure --------------------------------------------------------


def _overlap(a_x0: float, a_x1: float, b_x0: float, b_x1: float) -> bool:
    return a_x0 < b_x1 and b_x0 < a_x1


def _columns_for_period(
    period_end: date, anchors: Sequence[PeriodAnchor], margin: float
) -> list[Column]:
    """Anchors of one period whose regions overlap (stacked headers) form one column."""
    columns: list[Column] = []
    for anchor in sorted(anchors, key=lambda a: (a.x0, a.x1)):
        x0, x1 = anchor.x0 - margin, anchor.x1 + margin
        if columns and _overlap(columns[-1].x0, columns[-1].x1, x0, x1):
            last = columns[-1]
            columns[-1] = Column(
                period_end, last.x0, max(last.x1, x1), last.anchors + (anchor,)
            )
        else:
            columns.append(Column(period_end, x0, x1, (anchor,)))
    return columns


def analyse_structure(
    page: PageWords,
    resolve_period: PeriodResolver,
    settings: ColumnSettings | None = None,
    locator_settings: LocatorSettings | None = None,
) -> PageStructure:
    """Find the columns, note span and label limit of one page, and check structure S."""
    settings = settings or ColumnSettings()
    if page.rotation != 0:
        return PageStructure(page.page_number, (), 0, 0, (), (), None, None, (StructureProblem.ROTATED,))

    lines = group_lines(page.words, settings.line_tolerance_pt)
    first, last = header_block(lines, locator_settings)
    block = lines[first:last]
    anchors = tuple(
        replace(anchor, period_end=resolve_period(anchor)) for anchor in find_anchors(block)
    )
    usable = [a for a in anchors if a.period_end is not None]

    problems: set[StructureProblem] = set()
    if not usable:
        problems.add(StructureProblem.NO_USABLE_ANCHOR)
    if len(usable) != len(anchors):
        problems.add(StructureProblem.UNVALIDATED_ANCHOR)

    columns: list[Column] = []
    for period_end in sorted({a.period_end for a in usable if a.period_end is not None}):
        own = [a for a in usable if a.period_end == period_end]
        found = _columns_for_period(period_end, own, settings.column_margin_pt)
        if len(found) > 1:
            problems.add(StructureProblem.DUPLICATE_PERIOD_COLUMN)
        columns += found
    columns.sort(key=lambda c: (c.x0, c.x1, c.period_end))
    # Columns of one period never overlap (overlapping ones were merged), so any
    # overlap here is between different periods.
    if any(
        _overlap(a.x0, a.x1, b.x0, b.x1)
        for index, a in enumerate(columns)
        for b in columns[index + 1 :]
    ):
        problems.add(StructureProblem.OVERLAPPING_REGIONS)

    note_span = _note_span(block, columns, settings.column_margin_pt)
    edges = [c.x0 for c in columns] + ([note_span.x0] if note_span else [])
    return PageStructure(
        page_number=page.page_number,
        lines=lines,
        header_first=first,
        header_last=last,
        anchors=anchors,
        columns=tuple(columns),
        note_span=note_span,
        label_limit=min(edges) if edges else None,
        problems=tuple(p for p in StructureProblem if p in problems),
    )


def _note_span(block: Sequence[Line], columns: Sequence[Column], margin: float) -> NoteSpan | None:
    """From the leftmost "Note" header word's left edge minus the margin to the first
    period region's left edge (exclusive); none if there is no such word or no room."""
    if not columns:
        return None
    notes = [w for line in block for w in line.words if w.text.casefold() in NOTE_HEADER_WORDS]
    if not notes:
        return None
    start = min(w.x0 for w in notes) - margin
    end = min(c.x0 for c in columns)
    return NoteSpan(start, end) if start < end else None
