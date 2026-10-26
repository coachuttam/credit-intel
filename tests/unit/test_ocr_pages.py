"""Image coverage, the image-only page test, the OCR page plan and the moved no-text-layer check (PRD v0.4.44, FR-001A; B-318).

Step 1c of the OCR build. No engine is called; the PDFs are synthetic and generated here.
"""

import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from credit_intel.config import OcrSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.models import PageImageCoverage, PageText
from credit_intel.ingestion.ocr_pages import is_image_only, plan_ocr_pages, require_page_range_for_scan
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor, union_area

PAGE_W, PAGE_H = 612.0, 792.0
PICTURE = ImageReader(Image.new("RGB", (20, 20), "white"))


def make_pdf(path, pages):
    """``pages``: a list of (text or None, [(x, y, w, h) image boxes in PDF points, origin bottom-left])."""
    pdf = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H), invariant=1)
    for text, boxes in pages:
        for x, y, w, h in boxes:
            pdf.drawImage(PICTURE, x, y, w, h)
        if text:
            pdf.drawString(72, 700, text)
        pdf.showPage()
    pdf.save()
    return path


def share(path, number=1):
    return {c.page_number: c.area_share for c in PdfplumberExtractor().image_coverage(path)}[number]


def settings(**kw):
    base = dict(enabled=True, min_image_area_share=0.5, max_pages=2, timeout_seconds=60.0, column_margin_pt=4.0, split_figure_gap_pt=2.0)
    return OcrSettings(**{**base, **kw})


# --- union_area ---------------------------------------------------------------------------------------------------------------------------------


def test_union_area_of_one_rectangle_is_its_area():
    assert union_area([(0, 0, 10, 5)]) == 50


def test_overlapping_rectangles_are_counted_once():
    assert union_area([(0, 0, 10, 10), (5, 5, 15, 15)]) == 175


def test_identical_and_contained_rectangles_add_nothing():
    assert union_area([(0, 0, 10, 10), (0, 0, 10, 10), (2, 2, 4, 4)]) == 100


def test_an_inverted_rectangle_counts_for_nothing():
    assert union_area([(10, 10, 0, 0)]) == 0
    assert union_area([(0, 0, 10, 10), (30, 30, 20, 20)]) == 100


def test_touching_rectangles_add_up_and_empty_ones_count_for_nothing():
    assert union_area([(0, 0, 5, 10), (5, 0, 10, 10), (3, 3, 3, 9)]) == 100
    assert union_area([]) == 0


# --- image coverage from a PDF -----------------------------------------------------------------------------------------------------------------


def test_a_page_with_no_image_has_zero_coverage(tmp_path):
    assert share(make_pdf(tmp_path / "a.pdf", [("text only", [])])) == 0


def test_a_full_page_image_covers_all_of_the_page(tmp_path):
    assert share(make_pdf(tmp_path / "a.pdf", [(None, [(0, 0, PAGE_W, PAGE_H)])])) == pytest.approx(1.0)


def test_a_half_page_image_covers_half(tmp_path):
    assert share(make_pdf(tmp_path / "a.pdf", [(None, [(0, 0, PAGE_W, PAGE_H / 2)])])) == pytest.approx(0.5)


def test_two_overlapping_images_are_counted_once(tmp_path):
    boxes = [(0, 0, PAGE_W, PAGE_H / 2), (0, 0, PAGE_W, PAGE_H / 2)]
    assert share(make_pdf(tmp_path / "a.pdf", [(None, boxes)])) == pytest.approx(0.5)


def test_an_image_hanging_off_the_page_is_clipped_to_it(tmp_path):
    assert share(make_pdf(tmp_path / "a.pdf", [(None, [(-300, -300, PAGE_W + 600, PAGE_H + 600)])])) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "box",
    [
        (PAGE_W / 2, 0, PAGE_W, PAGE_H),  # hangs off the right
        (-PAGE_W / 2, 0, PAGE_W, PAGE_H),  # hangs off the left
        (0, PAGE_H / 2, PAGE_W, PAGE_H),  # hangs off the top
        (0, -PAGE_H / 2, PAGE_W, PAGE_H),  # hangs off the bottom
    ],
)
def test_an_image_hanging_off_one_edge_counts_only_the_part_on_the_page(tmp_path, box):
    assert share(make_pdf(tmp_path / "a.pdf", [(None, [box])])) == pytest.approx(0.5)


def test_coverage_has_one_entry_per_page_in_order(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", [("a", []), (None, [(0, 0, PAGE_W, PAGE_H)]), ("c", [])])
    got = PdfplumberExtractor().image_coverage(path)
    assert [c.page_number for c in got] == [1, 2, 3]
    assert [round(c.area_share) for c in got] == [0, 1, 0]


def test_coverage_is_deterministic(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", [(None, [(10, 10, 300, 300)])])
    assert PdfplumberExtractor().image_coverage(path) == PdfplumberExtractor().image_coverage(path)


@pytest.mark.parametrize("code,content", [(ErrorCode.CORRUPT, b"%PDF-1.4\n" + b"not a pdf body\n" * 20)])
def test_unreadable_pdf_raises_a_catalogued_error(tmp_path, code, content):
    path = tmp_path / "b.pdf"
    path.write_bytes(content)
    with pytest.raises(IngestionError) as excinfo:
        PdfplumberExtractor().image_coverage(path)
    assert excinfo.value.code is code


# --- the image-only test -----------------------------------------------------------------------------------------------------------------------


def page(text=""):
    return PageText(page_number=1, text=text)


def cover(value):
    return PageImageCoverage(page_number=1, area_share=value)


def test_no_text_and_enough_image_is_image_only():
    assert is_image_only(page(""), cover(0.9), 0.5)


def test_the_threshold_is_inclusive():
    assert is_image_only(page(""), cover(0.5), 0.5)
    assert not is_image_only(page(""), cover(0.4999), 0.5)


def test_whitespace_only_text_counts_as_no_text():
    assert is_image_only(page(" \n\t "), cover(1.0), 0.5)


def test_a_page_with_a_text_layer_is_never_image_only_however_big_the_image():
    assert not is_image_only(page("Total assets"), cover(1.0), 0.5)


def test_a_blank_page_is_not_image_only():
    assert not is_image_only(page(""), cover(0.0), 0.5)


# --- the plan ----------------------------------------------------------------------------------------------------------------------------------


def doc(*specs):
    """specs: (text, share) per page."""
    texts = [PageText(page_number=i, text=t) for i, (t, _) in enumerate(specs, 1)]
    covers = [PageImageCoverage(page_number=i, area_share=s) for i, (_, s) in enumerate(specs, 1)]
    return texts, covers


def test_the_plan_lists_the_image_only_pages_among_the_used_pages_ascending():
    texts, covers = doc(("", 1.0), ("", 1.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [3, 1], settings()) == (1, 3)


def test_pages_not_used_are_not_planned():
    texts, covers = doc(("", 1.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [2], settings()) == (2,)


def test_a_mixed_document_plans_only_its_image_only_pages():
    texts, covers = doc(("Balance sheet", 0.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [1, 2], settings()) == (2,)


def test_a_document_that_is_all_text_plans_nothing_and_is_not_an_error():
    texts, covers = doc(("a", 0.0), ("b", 0.0))
    assert plan_ocr_pages(texts, covers, [1, 2], settings()) == ()


def test_the_page_cap_is_inclusive_and_one_over_is_ocr_failed():
    texts, covers = doc(("", 1.0), ("", 1.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [1, 2], settings(max_pages=2)) == (1, 2)
    with pytest.raises(IngestionError) as excinfo:
        plan_ocr_pages(texts, covers, [1, 2, 3], settings(max_pages=2))
    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_the_cap_counts_only_pages_that_need_ocr():
    texts, covers = doc(("t", 0.0), ("", 1.0), ("t", 0.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [1, 2, 3, 4], settings(max_pages=2)) == (2, 4)


def test_used_pages_that_are_all_blank_give_no_text_layer():
    texts, covers = doc(("", 0.0), ("", 0.0))
    with pytest.raises(IngestionError) as excinfo:
        plan_ocr_pages(texts, covers, [1, 2], settings())
    assert excinfo.value.code is ErrorCode.NO_TEXT_LAYER


def test_a_blank_page_next_to_an_image_only_page_is_not_an_error():
    texts, covers = doc(("", 0.0), ("", 1.0))
    assert plan_ocr_pages(texts, covers, [1, 2], settings()) == (2,)


def test_the_threshold_comes_from_the_settings():
    texts, covers = doc(("", 0.6))
    assert plan_ocr_pages(texts, covers, [1], settings(min_image_area_share=0.5)) == (1,)
    with pytest.raises(IngestionError):
        plan_ocr_pages(texts, covers, [1], settings(min_image_area_share=0.7))


def test_incomplete_settings_are_a_programming_error_not_a_default():
    texts, covers = doc(("", 1.0))
    with pytest.raises(ValueError):
        plan_ocr_pages(texts, covers, [1], OcrSettings())


# --- --pages is required for a document with no text layer ---------------------------------------------------------------------


def test_a_scan_without_pages_is_page_range_and_the_message_names_the_option():
    texts, _ = doc(("", 1.0), ("", 1.0))
    with pytest.raises(IngestionError) as excinfo:
        require_page_range_for_scan(texts, None)
    assert excinfo.value.code is ErrorCode.PAGE_RANGE and "--pages" in str(excinfo.value.detail)


def test_a_scan_with_pages_passes():
    texts, _ = doc(("", 1.0))
    require_page_range_for_scan(texts, "1")


def test_a_document_with_a_text_layer_does_not_need_pages():
    texts, _ = doc(("", 1.0), ("text", 0.0))
    require_page_range_for_scan(texts, None)


# --- the no-text-layer check after the OCR decision ----------------------------------------------------------------------------------


def scan(tmp_path):
    return make_pdf(tmp_path / "scan.pdf", [(None, [(0, 0, PAGE_W, PAGE_H)])])


def test_without_ocr_a_scan_is_still_refused_as_before(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        ingest(scan(tmp_path))
    assert excinfo.value.code is ErrorCode.NO_TEXT_LAYER


def test_with_ocr_enabled_a_scan_is_returned_for_the_caller_to_decide(tmp_path):
    document = ingest(scan(tmp_path), ocr_enabled=True)
    assert [p.has_text for p in document.pages] == [False]


def test_with_ocr_enabled_a_document_with_text_is_unchanged(tmp_path):
    path = make_pdf(tmp_path / "t.pdf", [("hello", [])])
    assert ingest(path, ocr_enabled=True) == ingest(path)
