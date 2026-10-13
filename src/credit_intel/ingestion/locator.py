"""Statement page location and the statement-basis check (PRD FR-013, H.4.6).

Works only on extracted ``PageText`` entries; it never parses the PDF again.
Page text is normalised for matching only (NFKC, case-folded, whitespace
runs collapsed); the stored text is never changed. Line breaks are kept as
a separator so that a statement title's line can be found for the basis
check, but a phrase still matches across a line break, exactly as if the
break were a single space (FR-013 rule 1).
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from functools import lru_cache

from credit_intel.config import STATEMENT_BASES, LocatorSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import CandidatePage, LocatorResult, PageText

KEYWORDS = "keywords"
PAGE_RANGE = "page_range"
UNKNOWN_BASIS = "unknown"

_WHITESPACE = re.compile(r"\s+")
_LINE_BREAKS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85  ")
_RANGE_ITEM = re.compile(r"\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?")


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE.sub(
        lambda m: "\n" if _LINE_BREAKS.intersection(m.group()) else " ", text
    ).strip()


@lru_cache(maxsize=None)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Present only with no letter or digit immediately before or after
    # (FR-013 rule 2); a line break counts as the space between words.
    words = _normalise(phrase).split()
    body = r"[ \n]".join(re.escape(word) for word in words)
    return re.compile(rf"(?<![^\W_]){body}(?![^\W_])")


def _present(phrases: Iterable[str], text: str) -> list[str]:
    """Distinct phrases present in ``text``, in configuration order."""
    return [p for p in dict.fromkeys(phrases) if _phrase_pattern(p).search(text)]


def _score_page(page: PageText, settings: LocatorSettings) -> CandidatePage | None:
    text = _normalise(page.text)
    statement_types: list[str] = []
    matched: list[str] = []
    score = 0
    for statement_type in sorted(set(settings.title_phrases) | set(settings.line_item_phrases)):
        titles = _present(settings.title_phrases.get(statement_type, ()), text)
        items = _present(settings.line_item_phrases.get(statement_type, ()), text)
        qualifies = (titles and len(items) >= settings.min_line_items_with_title) or (
            len(items) >= settings.min_line_items_without_title
        )
        if qualifies:
            statement_types.append(statement_type)
            score += settings.title_weight * len(titles) + len(items)
            matched.extend(titles + items)
    if not statement_types:
        return None
    return CandidatePage(
        page_number=page.page_number,
        statement_types=tuple(statement_types),
        score=score,
        matched_phrases=tuple(dict.fromkeys(matched)),
    )


def parse_page_range(spec: str, page_count: int, max_pages: int) -> tuple[int, ...]:
    """Parse ``"110-115,120"`` into sorted, de-duplicated physical page numbers.

    Whitespace is allowed around numbers, hyphens, and commas, but not inside
    a number ("1 0" is malformed rather than read as 10).
    """
    if not spec.strip():
        raise IngestionError(ErrorCode.PAGE_RANGE, detail="the range is empty")
    selected: set[int] = set()
    for item in spec.split(","):
        match = _RANGE_ITEM.fullmatch(item)
        if match is None:
            raise IngestionError(ErrorCode.PAGE_RANGE, detail=f"malformed item {item.strip()[:20]!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start > end:
            raise IngestionError(ErrorCode.PAGE_RANGE, detail=f"reversed range {start}-{end}")
        if start < 1 or end > page_count:
            raise IngestionError(
                ErrorCode.PAGE_RANGE,
                detail=f"pages {start}-{end} are outside the document (1-{page_count})",
            )
        selected.update(range(start, end + 1))
    if len(selected) > max_pages:
        raise IngestionError(
            ErrorCode.PAGE_RANGE, detail=f"the range covers {len(selected)} pages; limit {max_pages}"
        )
    return tuple(sorted(selected))


def locate_statements(
    pages: Sequence[PageText],
    settings: LocatorSettings | None = None,
    page_range: str | None = None,
) -> LocatorResult:
    """Select candidate statement pages (FR-013).

    ``pages`` must be the 1..N physical pages from ingestion. An empty keyword
    result is not an error here (FR-013 failure behaviour).
    """
    settings = settings or LocatorSettings()

    if page_range is not None:
        numbers = parse_page_range(page_range, len(pages), settings.max_candidates)
        by_number = {page.page_number: page for page in pages}
        without_text = tuple(n for n in numbers if not by_number[n].has_text)
        if len(without_text) == len(numbers):
            raise IngestionError(
                ErrorCode.NO_TEXT_LAYER, detail="no page in the requested range has text"
            )
        candidates = tuple(CandidatePage(n, (), None, ()) for n in numbers)
        return LocatorResult(PAGE_RANGE, candidates, without_text)

    scored = [c for page in pages if (c := _score_page(page, settings)) is not None]
    kept = sorted(scored, key=lambda c: (-c.score, c.page_number))[: settings.max_candidates]
    return LocatorResult(KEYWORDS, tuple(sorted(kept, key=lambda c: c.page_number)))


def statement_runs(result: LocatorResult) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Consecutive selected pages sharing a statement type (FR-013 rule 6).

    Returns ``(statement_type, page_numbers)`` pairs ordered by type, then by
    first page. The first page of each run is "the first page of the
    statement" for FR-005.7 and FR-005.8. A page range has no runs.
    """
    runs: list[tuple[str, tuple[int, ...]]] = []
    statement_types = sorted({t for c in result.candidates for t in c.statement_types})
    for statement_type in statement_types:
        current: list[int] = []
        for candidate in result.candidates:
            if statement_type not in candidate.statement_types:
                continue
            if current and candidate.page_number != current[-1] + 1:
                runs.append((statement_type, tuple(current)))
                current = []
            current.append(candidate.page_number)
        if current:
            runs.append((statement_type, tuple(current)))
    return tuple(runs)


def _is_basis_only_line(line: str, settings: LocatorSettings) -> bool:
    """True if ``line`` holds nothing but one basis phrase, e.g. "(Consolidated)"."""
    words = " ".join(re.findall(r"[^\W_]+", line))
    return any(
        words == _normalise(phrase)
        for phrases in settings.basis_phrases.values()
        for phrase in phrases
    )


def _title_blocks(text: str, settings: LocatorSettings) -> list[str]:
    """The title block around each statement-title phrase in ``text``.

    A block is the line(s) containing the phrase, plus the line directly
    above or below it only when that line holds nothing but a basis phrase
    (a title such as "STANDALONE" / "BALANCE SHEET" set on two lines). Any
    other line, such as a company name containing "Consolidated", is not part
    of the block.
    """
    blocks = []
    for phrases in settings.title_phrases.values():
        for phrase in dict.fromkeys(phrases):
            for match in _phrase_pattern(phrase).finditer(text):
                start = text.rfind("\n", 0, match.start()) + 1
                end = text.find("\n", match.end())
                end = len(text) if end == -1 else end
                block = [text[start:end]]
                if start > 0:
                    above = text[text.rfind("\n", 0, start - 1) + 1 : start - 1]
                    if _is_basis_only_line(above, settings):
                        block.insert(0, above)
                if end < len(text):
                    below_end = text.find("\n", end + 1)
                    below = text[end + 1 : below_end if below_end != -1 else len(text)]
                    if _is_basis_only_line(below, settings):
                        block.append(below)
                blocks.append("\n".join(block))
    return blocks


def check_statement_basis(
    pages: Sequence[PageText],
    result: LocatorResult,
    basis: str,
    settings: LocatorSettings | None = None,
) -> tuple[str, ...]:
    """Stop unless a candidate page has a statement title of ``basis`` (H.4.6).

    A statement's basis comes from its title block (``_title_blocks``):
    exactly one basis named gives that basis; none or both gives ``unknown``.
    Basis words elsewhere on the page are ignored. The basis is never
    switched automatically, and an untitled-basis statement is never assumed
    to be standalone (OD-10). Returns the sorted bases found.
    """
    if basis not in STATEMENT_BASES:
        raise ValueError(f"unknown statement basis {basis!r}")
    settings = settings or LocatorSettings()
    by_number = {page.page_number: page for page in pages}

    found: set[str] = set()
    for candidate in result.candidates:
        for block in _title_blocks(_normalise(by_number[candidate.page_number].text), settings):
            named = {
                name for name, words in settings.basis_phrases.items() if _present(words, block)
            }
            found.add(named.pop() if len(named) == 1 else UNKNOWN_BASIS)

    if basis not in found:
        listed = ", ".join(sorted(found)) or "none"
        raise IngestionError(
            ErrorCode.BASIS_UNAVAILABLE, detail=f"configured basis: {basis}; bases found: {listed}"
        )
    return tuple(sorted(found))
