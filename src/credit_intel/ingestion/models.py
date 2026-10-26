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
class PageImageCoverage:
    """How much of one physical page its images cover (FR-001A.2).

    ``area_share`` is the area of the union of the page's images, clipped to the page, divided by the page area: from 0
    (no image) to 1. Overlapping images are counted once.
    """

    page_number: int  # 1-based physical page number
    area_share: float
    # Pixels per inch of the page's largest image across its displayed width, or None if it has no image or none can be read.
    native_dpi: int | None = None


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
class ExcludedCandidate:
    """A (page, statement type) pair removed by the cap, a chain cut or an unknown basis (FR-013, P1-2).

    Member order is the PRD's LOC-2 schema. ``score`` is the page's rule-4
    score exactly as used for ranking; ``chain_start_page`` is the original
    rule-3a page that began the chain for this type, even if that page was
    itself removed.
    """

    page_number: int  # 1-based physical page number
    statement_type: str  # an existing statement-type identifier, e.g. "balance_sheet"
    reason: str  # "cap", "chain_cut" or "basis_unknown" (H.4.6, v0.4.21)
    score: int
    chain_start_page: int


@dataclass(frozen=True)
class LocatorResult:
    """Candidate pages in ascending page order (FR-013).

    ``range_pages_without_text`` lists, in ascending order, the pages inside a
    supplied page range that have no extractable text (FR-013 rule 8); it is
    empty for keyword location. ``excluded_candidates`` (P1-2, LOC-2) records
    every excluded (page, statement type) pair in ascending page, then
    statement-type order; it is empty when nothing is excluded and for a page
    range.
    """

    method: str  # "keywords" or "page_range"
    candidates: tuple[CandidatePage, ...]
    range_pages_without_text: tuple[int, ...] = ()
    excluded_candidates: tuple[ExcludedCandidate, ...] = ()


@dataclass(frozen=True)
class Word:
    """One word as the PDF library reports it, in PDF points, top-left origin."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass(frozen=True)
class PageWords:
    """The words of one physical page, for the period-column check (OD-1).

    ``width`` and ``height`` are the page's unrotated size (pdfplumber does not
    swap them for a rotated page); ``rotation`` is the page's ``/Rotate`` in
    degrees. Geometry on a rotated page is not usable. ``words`` are ordered by
    ``(top, x0, text)``.
    """

    page_number: int  # 1-based physical page number
    width: float
    height: float
    rotation: int
    words: tuple[Word, ...]


@dataclass(frozen=True)
class OcrWord:
    """One word read by an OCR engine, in PDF points, top-left origin (FR-001A).

    ``confidence`` is the engine's own figure for the word, from 0 to 100. It is recorded and shown as the engine's
    number; it is not a probability that the word is right.
    """

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    confidence: float


@dataclass(frozen=True)
class OcrPage:
    """What an OCR engine read from one physical page (FR-001A, FR-005 criterion 11).

    ``text`` and ``words`` come from the same reading. Nothing here is a text layer: a field that rests on it is OCR
    evidence. ``width`` and ``height`` are the page's size in points. ``words`` are ordered by ``(top, x0, text)``.
    """

    page_number: int  # 1-based physical page number
    width: float
    height: float
    text: str
    words: tuple[OcrWord, ...]
    dpi: int | None = None  # the resolution the engine rendered the page at (FR-001A.6); None for a page not made by an engine

    @property
    def mean_confidence(self) -> float | None:
        """The mean of the word confidences, or ``None`` for a page with no words."""
        if not self.words:
            return None
        return sum(word.confidence for word in self.words) / len(self.words)

    def page_text(self) -> PageText:
        """The page as a ``PageText``, so the text checks read it as they read a text layer."""
        return PageText(page_number=self.page_number, text=self.text)

    def page_words(self) -> PageWords:
        """The page as a ``PageWords`` (never rotated), so the period-column check reads its word boxes."""
        return PageWords(
            page_number=self.page_number,
            width=self.width,
            height=self.height,
            rotation=0,
            words=tuple(Word(w.text, w.x0, w.x1, w.top, w.bottom) for w in self.words),
        )
