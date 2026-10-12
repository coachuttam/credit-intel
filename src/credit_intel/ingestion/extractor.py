"""The PDF library boundary (PRD decision D-01).

Code outside ``pdfplumber_extractor.py`` depends only on this interface, so
the PDF library can be replaced without changing callers.
"""

from pathlib import Path
from typing import Protocol

from credit_intel.ingestion.models import PdfInspection


class TextExtractor(Protocol):
    def inspect(self, path: Path) -> PdfInspection:
        """Open the PDF and report its page count and encryption status.

        Must raise ``IngestionError`` with ``ErrorCode.CORRUPT`` or
        ``ErrorCode.ENCRYPTED`` instead of library-specific exceptions.
        """
        ...
