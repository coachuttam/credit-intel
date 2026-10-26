"""The PDF library boundary (PRD decision D-01).

Code outside ``pdfplumber_extractor.py`` depends only on this interface, so
the PDF library can be replaced without changing callers.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from credit_intel.ingestion.models import OcrPage, PageText, PageWords, PdfInspection


class TextExtractor(Protocol):
    def inspect(self, path: Path) -> PdfInspection:
        """Open the PDF and report its page count and encryption status.

        Must raise ``IngestionError`` with ``ErrorCode.CORRUPT`` or
        ``ErrorCode.ENCRYPTED`` instead of library-specific exceptions.
        """
        ...

    def extract_pages(self, path: Path) -> list[PageText]:
        """Return one ``PageText`` per physical page, numbered from 1.

        Pages without text are included with empty text. Must be
        deterministic for the same file, and must raise ``IngestionError``
        instead of library-specific exceptions.
        """
        ...


class WordExtractor(Protocol):
    """Word positions, kept apart from ``TextExtractor`` so existing implementations
    and fakes need no change (OD-1)."""

    def extract_words(self, path: Path, page_numbers: Sequence[int]) -> list[PageWords]:
        """Return one ``PageWords`` per requested page, ascending by page number.

        ``page_numbers`` must be non-empty, without duplicates, and within the
        document; otherwise ``IngestionError`` with ``ErrorCode.PAGE_RANGE``.
        Must be deterministic for the same file, and must raise
        ``IngestionError`` instead of library-specific exceptions.
        """
        ...


class OcrExtractor(Protocol):
    """The OCR engine boundary (PRD D-15, FR-001A). Nothing outside the engine's own module imports the engine.

    An engine reads the pages it is asked for from the PDF and returns text, word boxes and a confidence for each word.
    It does not decide which pages to read: the caller names them (OD-13) and enforces the page cap (OD-18).
    """

    name: str  # the engine's name, recorded in the manifest
    version: str  # the engine's version, recorded in the manifest

    def ocr_pages(self, path: Path, page_numbers: Sequence[int], *, dpi: int, timeout_seconds: float) -> list[OcrPage]:
        """Return one ``OcrPage`` per requested page, ascending by page number.

        ``page_numbers`` must be non-empty, without duplicates and within the document; otherwise ``IngestionError``
        with ``ErrorCode.PAGE_RANGE``. The pages are rendered in memory at ``dpi`` and discarded. An engine that is not
        installed or configured raises ``ErrorCode.OCR_UNAVAILABLE``; an engine error or a read that takes longer than
        ``timeout_seconds`` raises ``ErrorCode.OCR_FAILED``. No error carries document text.
        """
        ...
