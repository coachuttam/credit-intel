"""Validate a PDF and extract its page text (PRD FR-001, FR-002).

Extracted text is returned as data. Nothing in this package executes,
evaluates, or follows instructions found in document text (FR-002.5).
"""

from collections.abc import Callable
from pathlib import Path

from credit_intel.config import IngestionSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import TextExtractor
from credit_intel.ingestion.models import FileInfo, IngestedDocument
from credit_intel.ingestion.validation import validate_pdf


def ingest(
    path: Path,
    settings: IngestionSettings | None = None,
    extractor: TextExtractor | None = None,
    on_validated: Callable[[FileInfo], None] | None = None,
    *,
    ocr_enabled: bool = False,
) -> IngestedDocument:
    """Validate ``path`` and return its pages, or raise ``IngestionError``.

    ``on_validated`` is called with the file information once validation has passed and before the
    text is read, so a caller can tell which of the two a later failure belongs to. A document with no text layer is
    refused with ``E-INPUT-NO-TEXT-LAYER`` unless ``ocr_enabled``; then the caller decides what to do with it (FR-001A).
    """
    if extractor is None:
        from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor

        extractor = PdfplumberExtractor()

    file_info = validate_pdf(path, settings=settings, extractor=extractor)
    if on_validated is not None:
        on_validated(file_info)
    pages = tuple(extractor.extract_pages(file_info.path))

    # Every downstream page reference relies on this numbering (FR-002.1).
    expected = list(range(1, file_info.page_count + 1))
    if [page.page_number for page in pages] != expected:
        raise RuntimeError(
            f"extractor returned page numbers that are not 1..{file_info.page_count} in order"
        )

    if not ocr_enabled and not any(page.has_text for page in pages):
        raise IngestionError(ErrorCode.NO_TEXT_LAYER)

    return IngestedDocument(file_info=file_info, pages=pages)
