"""Which pages OCR would read (PRD FR-001A, OD-13, OD-18).

Pure decisions on page text and image coverage; no engine is called here. A page is image-only when it has no text and an
image covers enough of it; a page with a text layer is never read by OCR, and a blank page is not image-only.
"""

from collections.abc import Mapping, Sequence

from credit_intel.config import OcrSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.models import PageImageCoverage, PageText


def is_image_only(page: PageText, coverage: PageImageCoverage, min_image_area_share: float) -> bool:
    """True if ``page`` has no text and its images cover at least ``min_image_area_share`` of it."""
    return not page.has_text and coverage.area_share >= min_image_area_share


def require_page_range_for_scan(pages: Sequence[PageText], page_range: str | None) -> None:
    """A document with no text layer needs ``--pages`` when OCR is on; the locator cannot run on it (FR-001A.3)."""
    if page_range is None and not any(page.has_text for page in pages):
        raise IngestionError(ErrorCode.PAGE_RANGE, detail="the document has no text layer; name the pages to read with --pages")


def plan_ocr_pages(
    pages: Sequence[PageText],
    coverage: Sequence[PageImageCoverage],
    used_pages: Sequence[int],
    settings: OcrSettings,
) -> tuple[int, ...]:
    """The pages among ``used_pages`` that OCR would read, ascending.

    Raises ``E-INPUT-OCR-FAILED`` when there are more than ``ocr.max_pages`` of them, and ``E-INPUT-NO-TEXT-LAYER`` when
    no used page has text and none is image-only, so there is nothing to read.
    """
    if settings.min_image_area_share is None or settings.max_pages is None:
        raise ValueError("OCR settings are not complete; load them with load_ocr_settings")
    text_of = {page.page_number: page for page in pages}
    cover_of = {item.page_number: item for item in coverage}
    chosen = sorted(set(used_pages))
    image_only = tuple(
        n for n in chosen if is_image_only(text_of[n], cover_of[n], settings.min_image_area_share)
    )
    if len(image_only) > settings.max_pages:
        raise IngestionError(
            ErrorCode.OCR_FAILED, detail=f"{len(image_only)} pages need OCR; the page cap is {settings.max_pages}"
        )
    if not image_only and not any(text_of[n].has_text for n in chosen):
        raise IngestionError(ErrorCode.NO_TEXT_LAYER, detail="no used page has text or an image to read")
    return image_only


def render_dpis(pages: Sequence[int], coverage: Sequence[PageImageCoverage], cap: int) -> Mapping[int, int]:
    """The resolution to render each page at (FR-001A.6): its largest image's own pixels per inch, never above ``cap``.

    A page whose image resolution is unknown is rendered at ``cap``. A page is never rendered above its image's resolution
    and there is no lower bound.
    """
    native = {item.page_number: item.native_dpi for item in coverage}
    return {n: cap if native.get(n) is None else min(native[n], cap) for n in pages}  # type: ignore[type-var]

