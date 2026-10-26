"""OCR end to end through the command line, with the offline fake engine (PRD v0.4.44, FR-001A, FR-005 criterion 11; B-321).

Step 2 of the OCR build. The input is a synthetic scanned PDF (pages that are only an image); the fake engine returns the text and
word boxes of a generated balance sheet, with invented confidences. What is tested is the wiring: which pages are read, what a field
read by OCR becomes, what the files say, and which failures stop a run with which code. No engine, no real scan.
"""

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "unit"))

import pipeline_fixture as fx  # noqa: E402
from memo_trace import problems  # noqa: E402

from credit_intel.cli import main  # noqa: E402
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode  # noqa: E402
from credit_intel.ingestion.fake_ocr import FakeOcrExtractor  # noqa: E402
from credit_intel.ingestion.models import OcrPage, OcrWord  # noqa: E402
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
LLM = '[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'


def ocr_table(**changes):
    values = dict(enabled="true", dpi=200, min_image_area_share=0.5, max_pages=5, timeout_seconds=60, column_margin_pt=3, split_figure_gap_pt=2.0)
    values.update(changes)
    return "[ocr]\n" + "".join(f"{k} = {v}\n" for k, v in values.items())


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def clock():
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(ticks)


PICTURE = ImageReader(Image.new("RGB", (1700, 2200), "white"))  # 200 pixels per inch across a 612 pt page


def scan_pdf(path, pages=1, pixels=(1700, 2200)):
    """A scanned document: every page is one full-page image and has no text. The default image is 200 pixels per inch."""
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    for _ in range(pages):
        pdf.drawImage(PICTURE if pixels == (1700, 2200) else ImageReader(Image.new("RGB", pixels, "white")), 0, 0, 612, 792)
        pdf.showPage()
    pdf.save()
    return path


def shapes_pdf(path):
    """A page with neither text nor an image: only a drawn shape."""
    pdf = canvas.Canvas(str(path), invariant=1)
    pdf.rect(72, 72, 200, 200, fill=1)
    pdf.showPage()
    pdf.save()
    return path


def mixed_pdf(path):
    """Page 1: a text balance sheet. Page 2: a scanned page."""
    pdf = canvas.Canvas(str(path), invariant=1)
    fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    pdf.drawImage(PICTURE, 0, 0, 612, 792)
    pdf.showPage()
    pdf.save()
    return path


def ocr_reading_of_balance_sheet(tmp_path, as_page=1, confidence=88.0):
    """What an engine would return for a scan of the generated balance sheet: its text and boxes, with invented confidences."""
    source = fx.balance_sheet_pdf(tmp_path / "text_source.pdf")
    extractor = PdfplumberExtractor()
    text = extractor.extract_pages(source)[0].text
    words = extractor.extract_words(source, [1])[0]
    return OcrPage(
        page_number=as_page, width=words.width, height=words.height, text=text,
        words=tuple(OcrWord(w.text, w.x0, w.x1, w.top, w.bottom, confidence) for w in words.words),
    ), source  # fmt: skip


def run(tmp_path, pdf, *extra, reply=None, engine=None, settings=None, ocr_factory=None):
    config = tmp_path / "settings.toml"
    config.write_text(LLM + (settings if settings is not None else ocr_table()), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    kwargs = {} if ocr_factory is None and engine is None else {"ocr_factory": ocr_factory or (lambda: engine)}
    code = main(
        [str(pdf), *extra, "--config", str(config), "--output-dir", str(tmp_path / "runs")],
        provider_factory=lambda s, e: FakeProvider(script=[reply] if reply else []),
        clock=clock(), stdout=out, stderr=err, assignments=tmp_path / "none.jsonl", env={}, **kwargs,
    )  # fmt: skip
    return code, out.getvalue(), err.getvalue()


def load(folder_text, name):
    return json.loads((Path(folder_text.strip()) / name).read_text(encoding="utf-8"))


def scan_run(tmp_path, pixels=(1700, 2200), **kw):
    page, source = ocr_reading_of_balance_sheet(tmp_path)
    scan = scan_pdf(tmp_path / "scan.pdf", pixels=pixels)
    engine = FakeOcrExtractor({1: page}, page_count=1)
    code, out, err = run(tmp_path, scan, "--ocr", "--pages", "1", reply=fx.good_response(source), engine=engine, **kw)
    return code, out, err, engine


# --- a scanned document, read by OCR ----------------------------------------------------------------------


def test_a_scan_with_ocr_and_pages_gives_a_run_whose_fields_all_await_review(tmp_path):
    code, out, err, engine = scan_run(tmp_path)
    results = load(out, "results.json")
    read = [f for f in results["fields"] if f["evidence_source"] == "ocr"]

    assert code == 0, err
    assert len(read) == 6 and {f["status"] for f in read} == {"requires_review"} and {f["status_reason"] for f in read} == {"ocr_unconfirmed"}
    assert all(f["value"] is None and f["currency"] is None for f in read)
    assert {f["ocr_evidence"]["engine"] for f in read} == {"fake-ocr"} and {f["ocr_evidence"]["dpi"] for f in read} == {200}
    assert all(f["validation"]["period_column_verified"] and f["validation"]["scale_verified"] for f in read)  # every other check still passed
    assert {f["evidence_source"] for f in results["fields"] if f["status"] == "not_found"} == {"text_layer"}


def test_the_engine_is_asked_for_the_image_only_pages_with_the_dpi_and_time_limit_of_the_settings(tmp_path):
    _, _, _, engine = scan_run(tmp_path)

    assert engine.calls == [((1,), {1: 200}, 60.0)]


def test_a_page_is_rendered_at_its_image_resolution_and_the_cap_only_limits_it(tmp_path):
    low, high = tmp_path / "low", tmp_path / "high"
    low.mkdir()
    high.mkdir()
    _, out, _, engine = scan_run(low, pixels=(850, 1100))  # 100 pixels per inch, under the cap of 200
    assert engine.calls == [((1,), {1: 100}, 60.0)]
    results, manifest = load(out, "results.json"), load(out, "manifest.json")
    assert {f["ocr_evidence"]["dpi"] for f in results["fields"] if f["evidence_source"] == "ocr"} == {100}
    assert manifest["ocr"]["dpi_cap"] == 200 and manifest["ocr"]["pages_ocr"][0]["dpi"] == 100

    _, out, _, engine = scan_run(high, pixels=(3400, 4400))  # 400 pixels per inch, over the cap
    assert engine.calls == [((1,), {1: 200}, 60.0)]
    assert load(out, "manifest.json")["ocr"]["pages_ocr"][0]["dpi"] == 200


def test_no_metric_or_indicator_uses_an_ocr_value(tmp_path):
    _, out, _, _ = scan_run(tmp_path)
    results = load(out, "results.json")

    assert results["metrics"] and all(m["value"] is None for m in results["metrics"])
    assert results["derived_fields"] and all(d["status"] != "extracted" and d["value"] is None for d in results["derived_fields"])
    outcomes = {i["id"]: i["outcome"] for i in results["indicators"]}
    assert {i for i, o in outcomes.items() if o == "triggered"} == {"RI-006", "RI-007"}  # only the missing and unverified-value indicators
    assert {outcomes[f"RI-00{n}"] for n in range(1, 6)} == {"not_evaluable"}  # no value-based rule ran on an OCR value


def test_the_manifest_records_the_ocr_block_and_a_text_stage_count(tmp_path):
    _, out, _, _ = scan_run(tmp_path)
    manifest = load(out, "manifest.json")

    assert manifest["ocr"] == {
        "engine": "fake-ocr", "engine_version": "0", "dpi_cap": 200, "language": "eng",
        "pages_ocr": [{"page": 1, "dpi": 200, "mean_word_confidence": "88.0"}], "pages_text_layer": [],
    }  # fmt: skip
    assert next(e for e in manifest["stage_events"] if e["state"] == "text_extracted")["counts"]["ocr_pages"] == 1
    assert "Total" not in json.dumps(manifest["ocr"])


def test_the_memo_labels_the_fields_as_ocr_asks_the_page_image_question_and_passes_the_check(tmp_path):
    _, out, _, _ = scan_run(tmp_path)
    memo = (Path(out.strip()) / "memo.md").read_text(encoding="utf-8")
    results = load(out, "results.json")

    assert problems(memo, results) == []
    assert "[OCR p.1, confidence 88.0]" in memo and "- **Text read by OCR:** page 1" in memo
    assert memo.count("Check this value against the page image.") == 6
    assert "[SOURCE: p.1]" not in memo.split("## 7.")[1]
    assert "OCR of scanned pages is available but was not used" not in memo and "never accepted as extracted" in memo


def test_results_and_memo_are_the_same_on_a_second_run(tmp_path):
    first = scan_run(tmp_path / "a" if (tmp_path / "a").mkdir() is None else tmp_path)
    second = scan_run(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)

    assert (Path(first[1].strip()) / "results.json").read_bytes() == (Path(second[1].strip()) / "results.json").read_bytes()
    assert (Path(first[1].strip()) / "memo.md").read_bytes() == (Path(second[1].strip()) / "memo.md").read_bytes()


def test_the_ocr_column_settings_apply_to_ocr_pages_and_not_the_text_layer(tmp_path):
    wide = scan_run(tmp_path / "w" if (tmp_path / "w").mkdir() is None else tmp_path, settings=ocr_table(column_margin_pt=400))
    results = load(wide[1], "results.json")
    read = [f for f in results["fields"] if f["evidence_source"] == "ocr"]

    assert wide[0] == 0 and read
    assert {f["status_reason"] for f in read} != {"ocr_unconfirmed"}  # an earlier check now fails: the margin of 400 pt merges the columns


def test_a_text_layer_document_with_ocr_on_is_read_exactly_as_without_it(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "text.pdf")
    reply = fx.good_response(pdf)
    engine = FakeOcrExtractor({}, page_count=1)

    on = run(tmp_path / "on" if (tmp_path / "on").mkdir() is None else tmp_path, pdf, "--ocr", "--pages", "1", reply=reply, engine=engine)
    off = run(tmp_path / "off" if (tmp_path / "off").mkdir() is None else tmp_path, pdf, "--pages", "1", reply=reply, settings="")

    assert on[0] == off[0] == 0 and engine.calls == []
    assert (Path(on[1].strip()) / "results.json").read_bytes() == (Path(off[1].strip()) / "results.json").read_bytes()
    assert "ocr" not in load(on[1], "manifest.json")


def test_a_text_layer_document_with_ocr_on_and_no_pages_is_located_by_keywords_as_before(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "text.pdf")
    reply = fx.good_response(pdf)
    engine = FakeOcrExtractor({}, page_count=1)
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()

    on = run(tmp_path / "on", pdf, "--ocr", reply=reply, engine=engine)
    off = run(tmp_path / "off", pdf, reply=reply, settings="")

    assert on[0] == off[0] == 0 and engine.calls == []
    assert load(on[1], "results.json")["extraction"]["locator_method"] == "keywords"
    assert (Path(on[1].strip()) / "results.json").read_bytes() == (Path(off[1].strip()) / "results.json").read_bytes()


# --- a mixed document -------------------------------------------------------------------------------------


def test_in_a_mixed_document_only_the_scanned_page_is_read_by_ocr_and_the_text_layer_value_wins(tmp_path):
    page, source = ocr_reading_of_balance_sheet(tmp_path, as_page=2)
    reply = json.loads(fx.good_response(source))
    again = dict(fx.field(source, "total_equity", "current", "600.00", "Total equity"), page_number=2)
    reply["fields"].append(again)  # the same figure, cited on the scanned page too
    engine = FakeOcrExtractor({2: page}, page_count=2)

    code, out, err = run(tmp_path, mixed_pdf(tmp_path / "mixed.pdf"), "--ocr", "--pages", "1-2", reply=json.dumps(reply), engine=engine)
    results, manifest = load(out, "results.json"), load(out, "manifest.json")
    equity = next(f for f in results["fields"] if f["field_id"] == "total_equity.2025-03-31.consolidated")

    assert code == 0, err
    assert engine.calls == [((2,), {2: 200}, 60.0)]
    assert manifest["ocr"]["pages_ocr"] == [{"page": 2, "dpi": 200, "mean_word_confidence": "88.0"}] and manifest["ocr"]["pages_text_layer"] == [1]
    assert equity["status"] == "extracted" and equity["evidence_source"] == "text_layer" and equity["page_number"] == 1
    assert "ocr_evidence" not in equity and equity["corroborating_evidence"] == []  # an OCR reading never corroborates
    other = equity["validation"]["details"]["unverified_occurrences"]
    assert [(o["page_number"], o["status"], o["status_reason"]) for o in other] == [(2, "requires_review", "ocr_unconfirmed")]
    memo = (Path(out.strip()) / "memo.md").read_text(encoding="utf-8")
    assert problems(memo, results) == []


def test_an_ocr_field_alone_on_a_mixed_document_stays_a_review_beside_extracted_text_layer_fields(tmp_path):
    page, source = ocr_reading_of_balance_sheet(tmp_path, as_page=2)
    reply = json.loads(fx.good_response(source))
    reply["fields"] = [f for f in reply["fields"] if f["field_name"] != "total_equity" or f["period_role"] != "current"]
    reply["fields"].append(dict(fx.field(source, "total_equity", "current", "600.00", "Total equity"), page_number=2))
    engine = FakeOcrExtractor({2: page}, page_count=2)

    _, out, _ = run(tmp_path, mixed_pdf(tmp_path / "mixed.pdf"), "--ocr", "--pages", "1-2", reply=json.dumps(reply), engine=engine)
    results = load(out, "results.json")
    by_id = {f["field_id"]: f for f in results["fields"]}

    assert by_id["total_equity.2025-03-31.consolidated"]["evidence_source"] == "ocr"
    assert by_id["total_equity.2025-03-31.consolidated"]["status"] == "requires_review"
    assert by_id["current_assets.2025-03-31.consolidated"]["status"] == "extracted"
    assert next(m for m in results["metrics"] if m["id"] == "MET-03.2025-03-31")["value"] is not None  # current ratio does not need equity


# --- the failures -----------------------------------------------------------------------------------------


def failed(result, code):
    exit_, out, err = result[:3]
    lines = [line for line in err.splitlines() if line.startswith("E-")]
    assert exit_ == CATALOGUE[code].exit_code != 0 and out == ""
    assert len(lines) == 1 and lines[0].startswith(f"{code.value}: ")
    return err


def test_a_scan_with_ocr_on_and_no_pages_is_page_range_naming_the_option_and_the_engine_is_not_called(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1)
    result = run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", engine=engine)

    assert "--pages" in failed(result, ErrorCode.PAGE_RANGE) and engine.calls == []


def test_a_scan_without_ocr_is_refused_and_the_message_names_ocr_and_pages(tmp_path):
    result = run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--pages", "1", settings="")

    assert "--ocr" in failed(result, ErrorCode.NO_TEXT_LAYER) and "--pages" in result[2]


def test_the_page_cap_stops_the_run_before_the_engine_is_called(tmp_path):
    engine = FakeOcrExtractor({}, page_count=3)
    result = run(tmp_path, scan_pdf(tmp_path / "scan.pdf", pages=3), "--ocr", "--pages", "1-3", engine=engine, settings=ocr_table(max_pages=2))

    failed(result, ErrorCode.OCR_FAILED)
    assert engine.calls == [] and load_failure(tmp_path)["failed_stage"] == "text_extracted"


def test_an_engine_failure_is_ocr_failed_in_the_text_stage_with_a_failure_record_only(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1, fail=True)
    result = run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", engine=engine)

    failed(result, ErrorCode.OCR_FAILED)
    record = load_failure(tmp_path)
    assert record["failed_stage"] == "text_extracted" and record["error_code"] == "E-INPUT-OCR-FAILED" and "ocr" not in record


def test_a_read_longer_than_the_time_limit_is_ocr_failed(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1, seconds_per_page=100.0)

    failed(run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", engine=engine, settings=ocr_table(timeout_seconds=30)), ErrorCode.OCR_FAILED)


def test_with_no_engine_installed_the_engine_gives_ocr_unavailable(tmp_path):
    from credit_intel.ingestion.tesseract_ocr import TesseractExtractor

    absent = TesseractExtractor(command="no-such-ocr-engine-installed")  # whatever is installed on this machine
    failed(run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", engine=absent), ErrorCode.OCR_UNAVAILABLE)


def test_an_engine_that_reads_nothing_is_no_text_layer(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1)  # an unseen page comes back empty

    failed(run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", engine=engine), ErrorCode.NO_TEXT_LAYER)


def test_pages_with_no_text_and_no_image_are_no_text_layer_and_the_engine_is_not_called(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1)

    failed(run(tmp_path, shapes_pdf(tmp_path / "shapes.pdf"), "--ocr", "--pages", "1", engine=engine), ErrorCode.NO_TEXT_LAYER)
    assert engine.calls == []


def test_a_page_range_outside_the_document_is_page_range_with_ocr_on(tmp_path):
    failed(run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "9", engine=FakeOcrExtractor({}, page_count=1)), ErrorCode.PAGE_RANGE)


def test_no_failure_message_carries_document_text(tmp_path):
    engine = FakeOcrExtractor({}, page_count=1, fail=True)
    err = run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", engine=engine)[2]
    error_line = next(line for line in err.splitlines() if line.startswith("E-"))

    assert str(tmp_path) not in error_line and "Traceback" not in err


def load_failure(tmp_path):
    folders = list((tmp_path / "runs").glob("*"))
    assert len(folders) == 1 and sorted(p.name for p in folders[0].iterdir()) == ["manifest.json"]
    record = json.loads((folders[0] / "manifest.json").read_text(encoding="utf-8"))
    assert record["final_state"] == "failed"
    return record


# --- the settings and the pages they apply to ------------------------------------------------------------------------


def split_reply(pdf):
    attributes = [
        fx.attribute(pdf, "entity_name", "Acme Industries Limited", "Acme Industries Limited", "Acme Industries Limited"),
        fx.attribute(pdf, "period_end", "March 31, 2025", "2025-03-31", "Year ended March 31,\n2025 2024", "current"),
        fx.attribute(pdf, "reporting_currency", "Rs.", "INR", "(Rs. in crore)"),
        fx.attribute(pdf, "scale", "in crore", "crore", "(Rs. in crore)"),
    ]
    return fx.reply(attributes, [fx.field(pdf, "revenue", "current", "8, 136", "Revenue")])


def split_figure_run(tmp_path, gap):
    """A scan of a statement whose figure the engine reports in two pieces 3.6 pt apart, with the OCR join gap ``gap``."""
    source = fx.split_figure_pdf(tmp_path / "split.pdf", [("Revenue", ["8,", "136"], ["7,", "361"])], heading="Statement of profit and loss")
    extractor = PdfplumberExtractor()
    words = extractor.extract_words(source, [1])[0]
    page = OcrPage(1, words.width, words.height, extractor.extract_pages(source)[0].text,
                   tuple(OcrWord(w.text, w.x0, w.x1, w.top, w.bottom, 90.0) for w in words.words))  # fmt: skip
    _, out, err = run(tmp_path, scan_pdf(tmp_path / "scan.pdf"), "--ocr", "--pages", "1", "--assert-basis", "consolidated",
                      reply=split_reply(source), engine=FakeOcrExtractor({1: page}, page_count=1), settings=ocr_table(split_figure_gap_pt=gap))  # fmt: skip
    return next(f for f in load(out, "results.json")["fields"] if f["field_id"].startswith("revenue.2025"))


def test_the_ocr_join_gap_setting_not_the_text_layer_one_decides_whether_pieces_are_joined(tmp_path):
    (tmp_path / "wide").mkdir()
    (tmp_path / "narrow").mkdir()
    joined = split_figure_run(tmp_path / "wide", gap=5.0)  # the text-layer setting (2.0 pt) would not join pieces 3.6 pt apart
    apart = split_figure_run(tmp_path / "narrow", gap=1.0)

    assert joined["validation"]["period_column_verified"] is True and joined["status_reason"] == "ocr_unconfirmed"
    assert apart["validation"]["period_column_verified"] is False and apart["status_reason"] == "period_not_verified"


def test_only_the_pages_of_the_range_are_read_by_ocr_though_other_pages_are_scans_too(tmp_path):
    engine = FakeOcrExtractor({}, page_count=3)

    run(tmp_path, scan_pdf(tmp_path / "scan.pdf", pages=3), "--ocr", "--pages", "2", engine=engine)

    assert engine.calls == [((2,), {2: 200}, 60.0)]


def test_without_ocr_the_engine_is_never_built(tmp_path):
    built = []
    pdf = fx.balance_sheet_pdf(tmp_path / "text.pdf")

    code, _, _ = run(tmp_path, pdf, "--pages", "1", reply=fx.good_response(pdf), settings="", ocr_factory=lambda: built.append(1))

    assert code == 0 and built == []


def test_a_run_started_with_ocr_on_and_no_engine_given_is_ocr_unavailable(tmp_path):
    from credit_intel.config import OcrSettings
    from credit_intel.ingestion.errors import IngestionError
    from credit_intel.run import run_pipeline

    settings = OcrSettings(enabled=True, min_image_area_share=0.5, max_pages=5, timeout_seconds=60.0, column_margin_pt=3.0, split_figure_gap_pt=2.0)
    with pytest.raises(IngestionError) as excinfo:
        run_pipeline(scan_pdf(tmp_path / "scan.pdf"), FakeProvider(script=[]), fx.LLM, page_range="1", cache_dir=tmp_path / "cache", ocr_settings=settings)

    assert excinfo.value.code is ErrorCode.OCR_UNAVAILABLE


def test_a_scan_without_pages_fails_in_the_locating_stage_and_an_engine_failure_in_the_text_stage(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    run(tmp_path / "a", scan_pdf(tmp_path / "a" / "scan.pdf"), "--ocr", engine=FakeOcrExtractor({}, page_count=1))
    run(tmp_path / "b", scan_pdf(tmp_path / "b" / "scan.pdf"), "--ocr", "--pages", "1", engine=FakeOcrExtractor({}, page_count=1, fail=True))

    assert load_failure(tmp_path / "a")["failed_stage"] == "statements_located"
    assert load_failure(tmp_path / "b")["failed_stage"] == "text_extracted"
