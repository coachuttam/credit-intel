"""The OCR engine a run uses when none is supplied (PRD v0.4.44, FR-001A.5, D-15): Tesseract.

The engine is a system install. When it, or its English data, is missing, the first page read fails with
``E-INPUT-OCR-UNAVAILABLE``; a run that does not use OCR never builds it.
"""

from credit_intel.ingestion.extractor import OcrExtractor
from credit_intel.ingestion.tesseract_ocr import TesseractExtractor


def default_ocr_extractor() -> OcrExtractor:
    return TesseractExtractor()
