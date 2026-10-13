"""Data passed between ingestion steps."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfInspection:
    """Structural facts about a PDF, reported by a TextExtractor."""

    page_count: int
    is_encrypted: bool


@dataclass(frozen=True)
class FileInfo:
    """A validated input file (FR-001)."""

    path: Path
    file_name: str
    size_bytes: int
    sha256: str
    page_count: int


@dataclass(frozen=True)
class PageText:
    """Text of one physical page (FR-002).

    ``text`` is exactly what the extractor returned and is treated as data
    only. ``page_label`` is the PDF's page-label metadata (e.g. "iv", "45")
    when the document defines one; it is not read from printed footers.
    """

    page_number: int  # 1-based physical page number
    text: str
    page_label: str | None = None

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass(frozen=True)
class IngestedDocument:
    """A validated PDF and its page texts, one entry per physical page."""

    file_info: FileInfo
    pages: tuple[PageText, ...]


@dataclass(frozen=True)
class CandidatePage:
    """A page selected for field extraction (FR-013)."""

    page_number: int  # 1-based physical page number
    statement_types: tuple[str, ...]  # sorted; empty for a page range
    score: int | None  # None for a page range
    matched_phrases: tuple[str, ...]  # empty for a page range


@dataclass(frozen=True)
class LocatorResult:
    """Candidate pages in ascending page order (FR-013).

    ``range_pages_without_text`` lists, in ascending order, the pages inside a
    supplied page range that have no extractable text (FR-013 rule 8); it is
    empty for keyword location.
    """

    method: str  # "keywords" or "page_range"
    candidates: tuple[CandidatePage, ...]
    range_pages_without_text: tuple[int, ...] = ()
