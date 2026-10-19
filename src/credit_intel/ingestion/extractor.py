"""The PDF library boundary (PRD decision D-01).

Code outside ``pdfplumber_extractor.py`` depends only on this interface, so
the PDF library can be replaced without changing callers.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from credit_intel.ingestion.models import PageText, PageWords, PdfInspection


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
