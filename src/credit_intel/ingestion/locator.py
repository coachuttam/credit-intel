"""Statement page location and the statement-basis check (PRD FR-013, G.0, H.4.6).

Works only on extracted ``PageText`` entries; it never parses the PDF again.
The stored text is never changed. For matching it is turned into *lines*
(NFKC; line separators as in FR-013 rule 1(a)), from which two views are
derived: the figure view (the lines as they are) and the matching view (each
line case-folded, typographic apostrophes and dashes folded; rule 1(c)).

Qualification follows rules 3a, 3b and 3c over all pages, then the cap and the
continuation-chain order of P1-2 (Stage A, DEC-E).
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from credit_intel.config import STATEMENT_BASES, LocatorSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import (
    CandidatePage,
    ExcludedCandidate,
    LocatorResult,
    PageText,
)

KEYWORDS = "keywords"
PAGE_RANGE = "page_range"
UNKNOWN_BASIS = "unknown"

CAP = "cap"
CHAIN_CUT = "chain_cut"

_WHITESPACE = re.compile(r"\s+")
# FR-013 rule 1(a). U+001F is whitespace but not a line separator.
_LINE_SEPARATORS = frozenset("\n\x0b\x0c\r\x1c\x1d\x1e\x85\u2028\u2029")
_FOLD_TABLE = str.maketrans(
    {0x2018: "'", 0x2019: "'", 0x02BC: "'", 0x2212: "-"}
    | {code: "-" for code in range(0x2010, 0x2016)}
)
_RANGE_ITEM = re.compile(r"\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?")

# G.0 numeric token; a lone ")" is also a numeric token.
_NUMERIC_TOKEN = re.compile(r"[(]?[-\u2212\u2013]?[0-9][0-9,]*([.][0-9]+)?[)]?")
_NIL_TOKENS = frozenset({"-", "\u2013", "\u2014"})


def lines_of(text: str) -> tuple[str, ...]:
    """FR-013 rule 1(a): the lines of ``text`` (also the figure view, rule 1(b))."""
    text = unicodedata.normalize("NFKC", text)
    marked = _WHITESPACE.sub(
        lambda m: "\n" if _LINE_SEPARATORS.intersection(m.group()) else " ", text
    )
    return tuple(line for raw in marked.split("\n") if (line := raw.strip(" ")))


def _fold(text: str) -> str:
    """FR-013 rule 1(c) folding of one line or phrase."""
    return text.casefold().translate(_FOLD_TABLE)


def _fold_phrase(phrase: str) -> str:
    """A configured phrase after rules 1(a) to 1(c): one line, single spaces."""
    return " ".join(_fold(" ".join(unicodedata.normalize("NFKC", phrase).split())).split())


def is_numeric_token(word: str) -> bool:
    return word == ")" or _NUMERIC_TOKEN.fullmatch(word) is not None


def is_nil_token(word: str) -> bool:
    return word in _NIL_TOKENS or word.casefold() == "nil"


def is_figure_word(word: str) -> bool:
    """A numeric token with a thousands separator followed by digits, a decimal
    point, or enclosing brackets (G.0). Years, ``31,`` and plain integers are not."""
    match = _NUMERIC_TOKEN.fullmatch(word)
    if match is None:
        return False
    return bool(
        re.search(r",[0-9]", word)
        or match.group(1)
        or (word.startswith("(") and word.endswith(")"))
    )


def _first_figure_line(lines: Sequence[str]) -> int | None:
    for index, line in enumerate(lines):
        if any(is_figure_word(word) for word in line.split(" ")):
            return index
    return None


@lru_cache(maxsize=None)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Present only with no letter or digit immediately before or after
    # (FR-013 rule 2); a line separator counts as the space between words.
    body = r"[ \n]".join(re.escape(word) for word in _fold_phrase(phrase).split())
    return re.compile(rf"(?<![^\W_]){body}(?![^\W_])")


def _present(phrases: Iterable[str], text: str) -> list[str]:
    """Distinct phrases present in ``text`` (matching view), in configuration order."""
    return [p for p in dict.fromkeys(phrases) if _phrase_pattern(p).search(text)]


@dataclass(frozen=True)
class TitleLine:
    """A title line (G.0): ``line_index`` is the first line; ``line_count`` is 1,
    or 2 for a split title line (LOC-3)."""

    statement_type: str | None  # None for an other-statement title line (rule 3c)
    line_index: int
    line_count: int = 1


class _Matcher:
    """Compiled title-line patterns for one phrase list (G.0, LOC-3, LOC-4)."""

    def __init__(self, phrases: Iterable[str], settings: LocatorSettings) -> None:
        word = "|".join(
            re.escape(w) for w in sorted({_fold_phrase(w) for w in settings.title_prefix_words}, key=len, reverse=True)
        )
        connector = "|".join(
            re.escape(c) for c in sorted({_fold_phrase(c) for c in settings.prefix_connectors}, key=len, reverse=True)
        )
        if word:
            joined = f"(?: (?:{connector}))? " if connector else " "
            prefix = rf"(?:(?:{word})(?:{joined}(?:{word}))* )?"
        else:
            prefix = ""
        folded = sorted({_fold_phrase(p) for p in phrases if _fold_phrase(p)}, key=len, reverse=True)
        self._single = (
            re.compile(prefix + "(?:" + "|".join(re.escape(p) for p in folded) + r")(?![^\W_])")
            if folded
            else None
        )
        self._splits: list[tuple[re.Pattern[str], re.Pattern[str]]] = []
        for phrase in folded:
            words = phrase.split(" ")
            for k in range(1, len(words)):
                self._splits.append(
                    (
                        re.compile(prefix + re.escape(" ".join(words[:k]))),
                        re.compile(re.escape(" ".join(words[k:])) + r"(?![^\W_])"),
                    )
                )

    def find(self, matching: Sequence[str], limit: int) -> list[tuple[int, int]]:
        """(line index, line count) of each title line above line ``limit``."""
        found = []
        for i in range(limit):
            if self._single is not None and self._single.match(matching[i]):
                found.append((i, 1))
            elif i + 1 < limit and any(
                first.fullmatch(matching[i]) and second.match(matching[i + 1])
                for first, second in self._splits
            ):
                found.append((i, 2))
        return found


class _Matchers:
    def __init__(self, settings: LocatorSettings) -> None:
        self.settings = settings
        self.types = sorted(set(settings.title_phrases) | set(settings.line_item_phrases))
        self.title = {
            t: _Matcher(settings.title_phrases.get(t, ()), settings) for t in self.types
        }
        self.other = _Matcher(settings.other_statement_title_phrases, settings)


@dataclass(frozen=True)
class _PageFacts:
    matching: tuple[str, ...]
    text: str  # the matching view joined by line separators (rules 2 and 4)
    titles: tuple[TitleLine, ...]  # located types
    other_titles: tuple[TitleLine, ...]  # rule 3c


def _page_facts(text: str, matchers: _Matchers) -> _PageFacts:
    figure_view = lines_of(text)
    matching = tuple(_fold(line) for line in figure_view)
    limit = _first_figure_line(figure_view)
    titles: list[TitleLine] = []
    other: list[TitleLine] = []
    if limit is not None:  # P1-4: a page with no figure line has no title lines
        for statement_type in matchers.types:
            titles += [
                TitleLine(statement_type, i, n)
                for i, n in matchers.title[statement_type].find(matching, limit)
            ]
        other = [TitleLine(None, i, n) for i, n in matchers.other.find(matching, limit)]
    return _PageFacts(matching, "\n".join(matching), tuple(titles), tuple(other))


def title_lines(text: str, settings: LocatorSettings | None = None) -> tuple[TitleLine, ...]:
    """The title lines (G.0) of one page's text, for the located statement types."""
    return _page_facts(text, _Matchers(settings or LocatorSettings())).titles


def other_statement_title_lines(
    text: str, settings: LocatorSettings | None = None
) -> tuple[TitleLine, ...]:
    """The other-statement title lines (rule 3c) of one page's text."""
    return _page_facts(text, _Matchers(settings or LocatorSettings())).other_titles


def _score_pages(
    pages: Sequence[PageText], matchers: _Matchers
) -> tuple[dict[int, CandidatePage], dict[tuple[int, str], int], dict[tuple[int, str], bool]]:
    """Rules 3a, 3b, 3c and 4 over all pages in ascending page order.

    Returns the qualifying pages (with every qualifying type), the chain start
    page of each (page, type), and whether each (page, type) qualified as a 3b
    continuation (such a page belongs to the preceding chain, P1-2).
    """
    settings = matchers.settings
    qualified: dict[tuple[int, str], bool] = {}  # (page, type) -> is a 3b continuation
    chain_start: dict[tuple[int, str], int] = {}
    scored: dict[int, CandidatePage] = {}
    for page in sorted(pages, key=lambda p: p.page_number):
        n = page.page_number
        facts = _page_facts(page.text, matchers)
        title_types = {t.statement_type for t in facts.titles}
        statement_types: list[str] = []
        matched: list[str] = []
        score = 0
        for statement_type in matchers.types:
            titles = _present(settings.title_phrases.get(statement_type, ()), facts.text)
            items = _present(settings.line_item_phrases.get(statement_type, ()), facts.text)
            has_title = statement_type in title_types
            continuation = (
                qualified.get((n - 1, statement_type)) is not None
                and not (title_types - {statement_type})
                and not facts.other_titles
                and (has_title or len(items) >= settings.min_line_items_without_title)
            )
            if continuation:
                qualified[(n, statement_type)] = True
                chain_start[(n, statement_type)] = chain_start[(n - 1, statement_type)]
            elif has_title and len(items) >= settings.min_line_items_with_title:
                qualified[(n, statement_type)] = False
                chain_start[(n, statement_type)] = n
            else:
                continue
            statement_types.append(statement_type)
            score += settings.title_weight * len(titles) + len(items)
            matched.extend(titles + items)
        if statement_types:
            scored[n] = CandidatePage(
                page_number=n,
                statement_types=tuple(statement_types),
                score=score,
                matched_phrases=tuple(dict.fromkeys(matched)),
            )
    return scored, chain_start, qualified


def apply_cap_and_chains(
    scored: dict[int, CandidatePage],
    chain_start: dict[tuple[int, str], int],
    max_candidates: int,
) -> tuple[tuple[CandidatePage, ...], tuple[ExcludedCandidate, ...]]:
    """Rule 5 and P1-2: the cap first, then the chain cut; no refill.

    ``scored`` holds the qualifying pages, ``chain_start`` the chain start page
    of every qualifying (page, type). Pure function of its inputs.
    """
    ranked = sorted(scored.values(), key=lambda c: (-c.score, c.page_number))
    kept = {c.page_number for c in ranked[:max_candidates]}

    excluded: dict[tuple[int, str], ExcludedCandidate] = {}
    chains: dict[tuple[str, int], list[int]] = defaultdict(list)
    for (page, statement_type), start in chain_start.items():
        chains[(statement_type, start)].append(page)
    for (statement_type, start), members in chains.items():
        removed = False
        for page in sorted(members):
            reason = None
            if page not in kept:
                reason, removed = CAP, True
            elif removed:
                reason = CHAIN_CUT
            if reason is not None:
                excluded[(page, statement_type)] = ExcludedCandidate(
                    page, statement_type, reason, scored[page].score, start
                )

    candidates = []
    for page in sorted(kept):
        candidate = scored[page]
        types = tuple(t for t in candidate.statement_types if (page, t) not in excluded)
        if types:  # a page excluded for every type is not a candidate
            candidates.append(
                CandidatePage(page, types, candidate.score, candidate.matched_phrases)
            )
    return tuple(candidates), tuple(excluded[key] for key in sorted(excluded))


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
    result is not an error here (FR-013 failure behaviour). A page range skips
    rules 3a to 5 and records no excluded candidates.
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

    scored, chain_start, _ = _score_pages(pages, _Matchers(settings))
    candidates, excluded = apply_cap_and_chains(scored, chain_start, settings.max_candidates)
    return LocatorResult(KEYWORDS, candidates, (), excluded)


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
    """True if matching-view ``line`` holds nothing but one basis phrase, e.g. "(Consolidated)"."""
    words = " ".join(re.findall(r"[^\W_]+", line))
    return any(
        words == _fold_phrase(phrase)
        for phrases in settings.basis_phrases.values()
        for phrase in phrases
    )


def _title_blocks(text: str, matchers: _Matchers) -> list[str]:
    """The title block of each title line (G.0, H.4.6) on a page.

    A block is the title line (both lines of a split title line) plus the line
    directly above or below only when that line holds nothing but one basis
    phrase. Any other line, such as a company name containing "Consolidated",
    is not part of the block.
    """
    settings = matchers.settings
    facts = _page_facts(text, matchers)
    blocks = []
    for title in dict.fromkeys((t.line_index, t.line_count) for t in facts.titles):
        index, count = title
        block = list(facts.matching[index : index + count])
        if index > 0 and _is_basis_only_line(facts.matching[index - 1], settings):
            block.insert(0, facts.matching[index - 1])
        end = index + count
        if end < len(facts.matching) and _is_basis_only_line(facts.matching[end], settings):
            block.append(facts.matching[end])
        blocks.append("\n".join(block))
    return blocks


def check_statement_basis(
    pages: Sequence[PageText],
    result: LocatorResult,
    basis: str,
    settings: LocatorSettings | None = None,
) -> tuple[str, ...]:
    """Stop unless a candidate page has a title line of ``basis`` (H.4.6, P1-3).

    A statement's basis comes from the title block of a title line
    (``_title_blocks``): exactly one basis named gives that basis; none or
    both gives ``unknown``. Basis words elsewhere on the page, and phrases that
    are not title lines, are ignored; a page with no title line contributes
    nothing. The basis is never switched automatically, and an untitled-basis
    statement is never assumed to be standalone (OD-10). Returns the sorted
    bases found.
    """
    if basis not in STATEMENT_BASES:
        raise ValueError(f"unknown statement basis {basis!r}")
    settings = settings or LocatorSettings()
    matchers = _Matchers(settings)
    by_number = {page.page_number: page for page in pages}

    found: set[str] = set()
    for candidate in result.candidates:
        for block in _title_blocks(by_number[candidate.page_number].text, matchers):
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
