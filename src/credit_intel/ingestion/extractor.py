"""The PDF library boundary (PRD decision D-01).

Code outside ``pdfplumber_extractor.py`` depends only on this interface, so
the PDF library can be replaced without changing callers.
"""

from pathlib import Path
from typing import Protocol

from credit_intel.ingestion.models import PageText, PdfInspection


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
