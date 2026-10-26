"""An offline OCR engine for tests (PRD FR-001A.11). It reads nothing: it returns the pages it was built with.

Like the fake LLM provider, it lets the whole OCR path be tested without an engine, a scan or a network. It follows the
``OcrExtractor`` contract, including the page-number rules and the two OCR errors.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import OcrPage


class FakeOcrExtractor:
    """Returns ``pages`` (by page number) for the pages asked for.

    ``unavailable`` makes every call raise ``OCR_UNAVAILABLE``; ``fail`` makes it raise ``OCR_FAILED``;
    ``seconds_per_page`` models a slow engine so the time limit can be tested without waiting. ``calls`` records each
    request as ``(page_numbers, dpi, timeout_seconds)``.
    """

    name = "fake-ocr"
    version = "0"

    def __init__(
        self,
        pages: Mapping[int, OcrPage],
        *,
        page_count: int | None = None,
        unavailable: bool = False,
        fail: bool = False,
        seconds_per_page: float = 0.0,
    ) -> None:
        self._pages = dict(pages)
        self._page_count = page_count if page_count is not None else max(self._pages, default=0)
        self._unavailable = unavailable
        self._fail = fail
        self._seconds_per_page = seconds_per_page
        self.calls: list[tuple[tuple[int, ...], dict[int, int], float]] = []

    def ocr_pages(self, path: Path, page_numbers: Sequence[int], *, dpi: Mapping[int, int], timeout_seconds: float) -> list[OcrPage]:
        requested = list(page_numbers)
        self.calls.append((tuple(requested), dict(dpi), timeout_seconds))
        if self._unavailable:
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE)
        if not requested or len(set(requested)) != len(requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        if any(number < 1 or number > self._page_count for number in requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        if self._fail or self._seconds_per_page * len(requested) > timeout_seconds:
            raise IngestionError(ErrorCode.OCR_FAILED)
        if any(number not in dpi for number in requested):
            raise IngestionError(ErrorCode.PAGE_RANGE)
        return [replace(self._pages.get(number, OcrPage(number, 612.0, 792.0, "", ())), dpi=dpi[number]) for number in sorted(requested)]
