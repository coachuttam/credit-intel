"""The Tesseract adapter, against a stub ``tesseract`` command (PRD v0.4.44, FR-001A, D-15; B-322).

Step 3 of the OCR build. The stub is a small script that answers ``--version`` and ``--list-langs`` like Tesseract, records how it was
called, and prints a canned TSV (or fails, or is slow, as the test asks). What these tests establish is the adapter's behaviour: the call
it makes, how it reads the TSV, and its errors. They say nothing about how well Tesseract reads a page; that needs the real engine, in
the one opt-in test at the end.
"""

import json
import os
import shutil
import stat
import sys

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.ocr_engine import default_ocr_extractor
from credit_intel.ingestion.tesseract_ocr import TesseractExtractor, _page_from_tsv

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
SAMPLE = "\n".join(
    [
        HEADER,
        "1\t1\t0\t0\t0\t0\t0\t0\t1700\t2200\t-1\t",
        "4\t1\t1\t1\t1\t0\t200\t400\t900\t50\t-1\t",
        "5\t1\t1\t1\t1\t1\t200\t400\t100\t50\t95.5\tTotal",
        "5\t1\t1\t1\t1\t2\t320\t400\t140\t50\t91.25\tassets",
        "5\t1\t1\t1\t1\t3\t480\t400\t10\t50\t-1\t",
        "5\t1\t1\t1\t1\t5\t700\t400\t80\t50\t-1\tghost",
        "5\t1\t1\t1\t1\t6\t800\t400\t80\t50\t77\t",
        "3\t1\t1\t1\t0\t0\t0\t0\t900\t900\t80\tnotaword",
        "5\t1\t1\t1\t1\t4\t500\t400\t150\t50\t42\t1,482.30",
        "4\t1\t1\t1\t2\t0\t200\t500\t900\t50\t-1\t",
        "5\t1\t1\t1\t2\t1\t200\t500\t100\t50\t88\tEquity",
        "5\t1\t1\t1\t2\t2\t320\t500\t60\t50\t0\t600.00",
        "5\t1\t1\t1\t2\t3\t100\t500\t60\t50\t70\tAcme",
    ]
)

STUB = """#!{python}
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("STUB_LOG")
if os.environ.get("STUB_META") and args in (["--version"], ["--list-langs"]):
    with open(os.environ["STUB_META"], "a") as handle:
        handle.write(json.dumps(args) + "\\n")
if args == ["--version"]:
    print("tesseract 5.9.9\\n leptonica-1.85.0", file=sys.stderr if os.environ.get("STUB_VERSION_ON_STDERR") else sys.stdout)
    sys.exit(0)
if args == ["--list-langs"]:
    print('List of available languages in "/stub" (2):')
    for lang in os.environ.get("STUB_LANGS", "eng osd").split():
        print(lang)
    sys.exit(0)
data = sys.stdin.buffer.read()
if log:
    from io import BytesIO
    from PIL import Image
    size = Image.open(BytesIO(data)).size if data.startswith(b"\\x89PNG") else None
    with open(log, "a") as handle:
        handle.write(json.dumps({{"args": args, "png_size": size, "omp": os.environ.get("OMP_THREAD_LIMIT")}}) + "\\n")
import time
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
mode = os.environ.get("STUB_MODE", "ok")
if mode == "fail":
    print("SECRET DOCUMENT WORDS", file=sys.stderr)
    sys.exit(1)
if mode == "garbage":
    print({header!r})
    print("5\\t1\\t1\\t1\\t1\\t1\\tleft\\t0\\t0\\t0\\t90\\tx")
    sys.exit(0)
print(os.environ["STUB_TSV"] if "STUB_TSV" in os.environ else {sample!r})
"""


@pytest.fixture
def stub(tmp_path, monkeypatch):
    path = tmp_path / "bin" / "tesseract-stub"
    path.parent.mkdir()
    path.write_text(STUB.format(python=sys.executable, header=HEADER, sample=SAMPLE), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("STUB_META", str(tmp_path / "meta.jsonl"))
    return TesseractExtractor(command=str(path))


def calls(tmp_path):
    log = tmp_path / "calls.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def scan(tmp_path, pages=1):
    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    for _ in range(pages):
        pdf.drawImage(ImageReader(Image.new("RGB", (20, 20), "white")), 0, 0, 612, 792)
        pdf.showPage()
    pdf.save()
    return path


def read(engine, path, numbers=(1,), dpi=200, timeout=30.0):
    return engine.ocr_pages(path, list(numbers), dpi=dpi, timeout_seconds=timeout)


# --- availability ---------------------------------------------------------------------------------------------


def test_the_version_is_read_from_the_engine_once(stub, tmp_path):
    assert stub.name == "tesseract" and stub.version == "5.9.9" and stub.version == "5.9.9"


def test_the_version_is_found_whether_the_engine_prints_it_on_standard_output_or_error(stub, monkeypatch):
    monkeypatch.setenv("STUB_VERSION_ON_STDERR", "1")

    assert stub.version == "5.9.9"


def test_a_missing_command_is_ocr_unavailable(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        TesseractExtractor(command="no-such-ocr-engine-installed").version

    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_a_command_that_cannot_be_run_is_ocr_unavailable(tmp_path):
    path = tmp_path / "not-executable"
    path.write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(IngestionError) as excinfo:
        read(TesseractExtractor(command=str(path)), scan(tmp_path))

    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_missing_english_data_is_ocr_unavailable(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_LANGS", "osd fra")

    with pytest.raises(IngestionError) as excinfo:
        read(stub, scan(tmp_path))

    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_unavailable_is_reported_before_a_bad_page_range(tmp_path):
    with pytest.raises(IngestionError) as excinfo:
        read(TesseractExtractor(command="no-such-ocr-engine-installed"), scan(tmp_path), numbers=())

    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_the_default_engine_is_tesseract():
    engine = default_ocr_extractor()

    assert isinstance(engine, TesseractExtractor) and engine.name == "tesseract"


# --- the call it makes ---------------------------------------------------------------------------------------


def test_the_page_is_rendered_in_memory_at_the_dpi_and_passed_on_standard_input(stub, tmp_path):
    read(stub, scan(tmp_path), dpi=200)
    (call,) = calls(tmp_path)

    assert call["args"] == ["stdin", "stdout", "-l", "eng", "--dpi", "200", "--psm", "6", "tsv"]
    assert call["png_size"] == [1700, 2200]  # 612 x 792 points at 200 dpi


def test_the_dpi_changes_the_rendered_size_and_the_argument(stub, tmp_path):
    read(stub, scan(tmp_path), dpi=100)
    (call,) = calls(tmp_path)

    assert call["args"][5] == "100" and call["png_size"] == [850, 1100]


def test_the_engine_is_run_with_one_thread(stub, tmp_path):
    read(stub, scan(tmp_path))

    assert calls(tmp_path)[0]["omp"] == "1"


def test_no_file_is_written_by_a_read(stub, tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    pdf = scan(tmp_path)
    before = sorted(p.name for p in tmp_path.rglob("*"))

    read(stub, pdf)

    after = sorted(p.name for p in tmp_path.rglob("*"))
    assert after == sorted([*before, "calls.jsonl", "meta.jsonl"]) and list(work.iterdir()) == []  # only the stub's own log; no page image anywhere


def test_there_is_one_call_per_page_in_ascending_order_whatever_order_was_asked(stub, tmp_path):
    pages = read(stub, scan(tmp_path, pages=3), numbers=(3, 1))

    assert [p.page_number for p in pages] == [1, 3] and len(calls(tmp_path)) == 2


def test_the_page_size_is_the_pdf_page_size_in_points(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path))

    assert (page.width, page.height) == (612.0, 792.0)


# --- the TSV --------------------------------------------------------------------------------------------------


def test_words_become_boxes_in_points_with_the_engine_confidence(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path), dpi=200)
    total = page.words[0]

    assert (total.text, total.confidence) == ("Total", 95.5)
    assert (total.x0, total.x1, total.top, total.bottom) == pytest.approx((72.0, 108.0, 144.0, 162.0))  # pixels x 72 / 200


def test_rows_that_are_not_words_and_boxes_without_text_or_confidence_are_left_out(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path))

    assert [w.text for w in page.words] == ["Total", "assets", "1,482.30", "Acme", "Equity", "600.00"]


def test_a_word_with_confidence_zero_is_kept_and_one_with_minus_one_is_not(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path))

    assert [w.confidence for w in page.words] == [95.5, 91.25, 42.0, 70.0, 88.0, 0.0]


def test_the_text_is_the_words_of_each_line_joined_by_spaces_and_the_lines_by_newlines(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path))

    assert page.text == "Total assets 1,482.30\nAcme Equity 600.00"  # Acme is listed after 600.00 in the TSV and printed first: x order within a line


def test_words_are_ordered_by_position_and_the_page_converts_to_the_forms_the_checks_read(stub, tmp_path):
    (page,) = read(stub, scan(tmp_path))
    keys = [(w.top, w.x0, w.text) for w in page.words]

    assert keys == sorted(keys)
    assert page.page_text().text == page.text and page.page_words().rotation == 0 and len(page.page_words().words) == 6


def test_lines_are_ordered_by_block_paragraph_and_line_numbers_not_by_row_order():
    rows = [HEADER, "5\t1\t1\t1\t2\t1\t10\t200\t50\t20\t90\tsecond", "5\t1\t1\t1\t1\t1\t10\t100\t50\t20\t90\tfirst"]

    assert _page_from_tsv(1, "\n".join(rows), 612.0, 792.0, 72).text == "first\nsecond"


def test_a_line_numbered_ten_comes_after_nine_not_before_two():
    rows = [HEADER] + [f"5\t1\t1\t1\t{n}\t1\t10\t{n * 30}\t50\t20\t90\tw{n}" for n in (10, 9, 2)]

    assert _page_from_tsv(1, "\n".join(rows), 612.0, 792.0, 72).text == "w2\nw9\nw10"


def test_a_page_with_no_words_is_empty_not_an_error(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_TSV", HEADER)

    (page,) = read(stub, scan(tmp_path))

    assert page.text == "" and page.words == () and page.mean_confidence is None


def test_a_tab_inside_the_text_field_is_kept_in_the_word():
    rows = [HEADER, "5\t1\t1\t1\t1\t1\t10\t100\t50\t20\t90\ta\tb"]

    assert _page_from_tsv(1, "\n".join(rows), 612.0, 792.0, 72).words[0].text == "a\tb"


def test_the_reading_is_the_same_each_time(stub, tmp_path):
    assert read(stub, scan(tmp_path)) == read(stub, scan(tmp_path))


def test_the_engine_is_asked_for_its_version_and_languages_once_however_many_reads(stub, tmp_path):
    pdf = scan(tmp_path)
    read(stub, pdf)
    read(stub, pdf)
    stub.version

    meta = [json.loads(line) for line in (tmp_path / "meta.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(meta) == [["--list-langs"], ["--version"]]


def test_each_page_gets_its_own_size_when_asked_for_out_of_order(stub, tmp_path):
    path = tmp_path / "sizes.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    for size in ((612, 792), (500, 500), (300, 400)):
        pdf.setPageSize(size)
        pdf.drawImage(ImageReader(Image.new("RGB", (20, 20), "white")), 0, 0, *size)
        pdf.showPage()
    pdf.save()

    pages = read(stub, path, numbers=(3, 1))

    assert [(p.page_number, p.width, p.height) for p in pages] == [(1, 612.0, 792.0), (3, 300.0, 400.0)]
    assert [c["png_size"] for c in calls(tmp_path)] == [[1700, 2200], [834, 1112]]  # in page order; the renderer rounds a fraction of a pixel up


# --- page numbers and failures -------------------------------------------------------------------------------


@pytest.mark.parametrize("numbers", [(), (1, 1), (0,), (2,), (1, 2), (-1,)])
def test_the_page_numbers_must_be_non_empty_unique_and_in_the_document(stub, tmp_path, numbers):
    with pytest.raises(IngestionError) as excinfo:
        read(stub, scan(tmp_path), numbers=numbers)

    assert excinfo.value.code is ErrorCode.PAGE_RANGE


def test_the_engine_is_not_called_for_a_bad_page_range(stub, tmp_path):
    with pytest.raises(IngestionError):
        read(stub, scan(tmp_path), numbers=(1, 5))

    assert calls(tmp_path) == []


def test_a_failing_engine_is_ocr_failed_and_its_output_is_not_in_the_error(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "fail")

    with pytest.raises(IngestionError) as excinfo:
        read(stub, scan(tmp_path))

    assert excinfo.value.code is ErrorCode.OCR_FAILED and "SECRET" not in str(excinfo.value) and "SECRET" not in repr(excinfo.value.__cause__)


def test_output_the_adapter_cannot_read_is_ocr_failed(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "garbage")

    with pytest.raises(IngestionError) as excinfo:
        read(stub, scan(tmp_path))

    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_a_read_that_outlasts_the_time_limit_is_ocr_failed(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_SLEEP", "5")

    with pytest.raises(IngestionError) as excinfo:
        read(stub, scan(tmp_path), timeout=0.5)

    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_the_time_limit_covers_the_whole_call_not_each_page(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_SLEEP", "0.6")
    pdf = scan(tmp_path, pages=3)

    assert len(read(stub, pdf, numbers=(1,), timeout=5.0)) == 1  # one page is within the limit ...
    with pytest.raises(IngestionError) as excinfo:
        read(stub, pdf, numbers=(1, 2, 3), timeout=1.5)  # ... three such pages (1.8 s) are not, though each is

    assert excinfo.value.code is ErrorCode.OCR_FAILED


def test_a_file_that_is_not_a_pdf_is_ocr_failed(stub, tmp_path):
    path = tmp_path / "note.pdf"
    path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(IngestionError) as excinfo:
        read(stub, path)

    assert excinfo.value.code is ErrorCode.OCR_FAILED


# --- the real engine, opt in ---------------------------------------------------------------------------------


def real_engine_available():
    return os.environ.get("CREDIT_INTEL_REAL_OCR") == "1" and shutil.which("tesseract") is not None


@pytest.mark.real_ocr
@pytest.mark.skipif(not real_engine_available(), reason="needs Tesseract installed and CREDIT_INTEL_REAL_OCR=1")
def test_the_real_engine_reads_a_rendered_line_of_text(tmp_path):
    from PIL import ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 400), "white")
    ImageDraw.Draw(image).text((100, 100), "Total current assets 1,482.30", fill="black", font=ImageFont.load_default(size=60))
    path = tmp_path / "line.pdf"
    image.save(path, "PDF", resolution=200.0)

    (page,) = TesseractExtractor().ocr_pages(path, [1], dpi=300, timeout_seconds=120.0)

    assert "assets" in page.text.lower() and page.words and page.mean_confidence is not None


@pytest.mark.real_ocr
@pytest.mark.skipif(not real_engine_available(), reason="needs Tesseract installed and CREDIT_INTEL_REAL_OCR=1")
def test_the_real_engine_keeps_the_label_and_figures_of_each_table_row_on_one_line(tmp_path):
    import random

    labels = ["Total current assets", "Total current liabilities", "Total equity", "Revenue from operations", "Other income", "Finance costs",
              "Depreciation and amortisation", "Profit before tax", "Tax expense", "Profit for the year", "Trade receivables", "Inventories"]
    rnd = random.Random(3)
    rows = [(labels[n % len(labels)], f"{rnd.randint(10, 99999):,}.{rnd.randint(0, 99):02d}", f"{rnd.randint(10, 99999):,}.{rnd.randint(0, 99):02d}") for n in range(24)]
    source = tmp_path / "table.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(612, 792), invariant=1)
    pdf.setFont("Times-Roman", 9)
    pdf.drawString(72, 760, "Acme Industries Limited")
    pdf.drawString(72, 746, "Consolidated Balance Sheet")
    pdf.drawCentredString(400, 720, "31 March 2025")
    pdf.drawCentredString(480, 720, "31 March 2024")
    for index, (label, current, comparative) in enumerate(rows):
        pdf.drawString(72, 700 - index * 13, label)
        pdf.drawRightString(430, 700 - index * 13, current)
        pdf.drawRightString(510, 700 - index * 13, comparative)
    pdf.showPage()
    pdf.save()
    import pypdfium2 as pdfium

    scan = tmp_path / "scan.pdf"
    pdfium.PdfDocument(str(source))[0].render(scale=300 / 72).to_pil().convert("RGB").save(scan, "PDF", resolution=300.0)

    (page,) = TesseractExtractor().ocr_pages(scan, [1], dpi=300, timeout_seconds=120.0)

    whole = [line for line in page.text.split("\n") if sum(ch.isdigit() for ch in line) >= 8 and any(label in line for label in labels)]
    assert len(whole) == len(rows)  # with Tesseract's default mode the labels come out apart from their figures
