"""The OCR engine a run uses when none is supplied (PRD v0.4.44, FR-001A.7, D-15).

No real engine is built in yet: the Tesseract adapter is the next step of the OCR build. Until then the default engine reports
itself unavailable, so ``--ocr`` on a scanned page fails with ``E-INPUT-OCR-UNAVAILABLE`` instead of reading nothing.
"""

from collections.abc import Sequence
from pathlib import Path

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.extractor import OcrExtractor
from credit_intel.ingestion.models import OcrPage


class UnavailableOcrExtractor:
    """An engine that is not installed or not configured."""

    name = "none"
    version = "none"

    def ocr_pages(self, path: Path, page_numbers: Sequence[int], *, dpi: int, timeout_seconds: float) -> list[OcrPage]:
        raise IngestionError(ErrorCode.OCR_UNAVAILABLE)


def default_ocr_extractor() -> OcrExtractor:
    return UnavailableOcrExtractor()
