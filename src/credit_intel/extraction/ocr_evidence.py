"""The OCR evidence of a field: which engine read the page and how sure it said it was (PRD FR-005 criterion 11, v0.4.44).

The confidences are the engine's own numbers, kept as ``Decimal`` to one decimal place so they can be written to
``results.json`` exactly. Nothing here decides whether a field is right: a field read by OCR is never ``extracted``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from credit_intel.ingestion.models import OcrPage, OcrWord, Word
from credit_intel.models import OcrEvidence

_ONE_PLACE = Decimal("0.1")


@dataclass(frozen=True)
class OcrReading:
    """The OCR reading a run used: the engine, the DPI and the pages it read, by physical page number."""

    engine: str
    engine_version: str
    dpi: int
    pages: Mapping[int, OcrPage]


def confidence(value: float) -> Decimal:
    """An engine confidence as a ``Decimal`` to one decimal place (half to even, from the float's shortest text)."""
    return Decimal(repr(value)).quantize(_ONE_PLACE)


def mean_confidence(values: Sequence[float]) -> Decimal | None:
    """The mean of the confidences to one decimal place, or ``None`` for no values. The sum is exact."""
    if not values:
        return None
    return (sum((Decimal(repr(v)) for v in values), Decimal(0)) / len(values)).quantize(_ONE_PLACE)


def _quote_words(page: OcrPage, quote: str, line_words: Sequence[Word] | None) -> list[OcrWord]:
    """The OCR words of the field's quote: those of its figure line when it was found, else those whose text is in the quote."""
    if line_words:
        wanted = {(w.text, w.x0, w.x1, w.top, w.bottom) for w in line_words}
        return [w for w in page.words if (w.text, w.x0, w.x1, w.top, w.bottom) in wanted]
    tokens = set(quote.split())
    return [w for w in page.words if w.text in tokens]


def ocr_evidence_for(
    reading: OcrReading, page_number: int, quote: str, line_words: Sequence[Word] | None = None
) -> OcrEvidence:
    page = reading.pages[page_number]
    words = [w.confidence for w in _quote_words(page, quote, line_words)]
    return OcrEvidence(
        engine=reading.engine,
        engine_version=reading.engine_version,
        dpi=reading.dpi,
        min_word_confidence=confidence(min(words)) if words else None,
        mean_word_confidence=mean_confidence(words),
        page_mean_confidence=mean_confidence([w.confidence for w in page.words]),
    )


@dataclass(frozen=True)
class OcrRunRecord:
    """What the manifest records of a run that used OCR (FR-001A.8): the engine, DPI and language, and for each used page
    whether its text came from the text layer or from OCR, with each OCR page's mean word confidence."""

    engine: str
    engine_version: str
    dpi: int
    language: str
    ocr_pages: Mapping[int, Decimal | None]  # page number -> the page's mean word confidence, or None for no words
    text_layer_pages: tuple[int, ...]

    def to_manifest(self) -> dict:
        return {
            "engine": self.engine,
            "engine_version": self.engine_version,
            "dpi": self.dpi,
            "language": self.language,
            "pages_ocr": [
                {"page": page, "mean_word_confidence": None if value is None else format(value, "f")}
                for page, value in sorted(self.ocr_pages.items())
            ],
            "pages_text_layer": sorted(self.text_layer_pages),
        }
