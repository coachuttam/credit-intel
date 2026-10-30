"""The PDF report in a run (PRD FR-015 criteria 2, 7, 8 and 9, v0.4.56; step 5 of its build; B-330).

The real report maker is put back (``real_report``); the suite otherwise skips the report so that tests that are not about it do not wait.
A report that cannot be built must never fail the run: the folder is then written without it, the manifest says why and a warning is logged.
"""

import functools
import io
import json
import logging
import re
import sys
from pathlib import Path

import pdfplumber
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "unit"))

import pipeline_fixture as fx  # noqa: E402
from test_cli import call, manifest_of  # noqa: E402
from test_export_run import export  # noqa: E402

import credit_intel.export.run_export as run_export  # noqa: E402
from credit_intel.ingestion.errors import ErrorCode, IngestionError  # noqa: E402
from credit_intel.report import build, charts, check  # noqa: E402

FOUR = ["manifest.json", "memo.md", "report.pdf", "results.json"]
THREE = ["manifest.json", "memo.md", "results.json"]


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the response cache and the default output directory are relative to it


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def names(folder):
    return sorted(p.name for p in Path(folder).iterdir())


def with_stub(monkeypatch, tmp_path, code, time_limit=60.0):
    script = tmp_path / "report_worker_stub.py"
    script.write_text("import sys, time\nsys.stdin.buffer.read()\n" + code, encoding="utf-8")
    monkeypatch.setattr(run_export, "make_report", functools.partial(build.make_report, command=(sys.executable, str(script)), time_limit=time_limit))


# --- the report is written with the other files --------------------------------------------------------------------------------------------


def test_a_run_writes_report_pdf_beside_the_three_files_and_does_not_change_them(real_report, pdf, tmp_path):
    with_report, *_ = export(tmp_path / "a", pdf)
    without, *_ = export(tmp_path / "b", pdf, report=False)

    assert names(with_report) == FOUR and names(without) == THREE
    for name in ("memo.md", "results.json"):
        assert (with_report / name).read_bytes() == (without / name).read_bytes()  # a presentation layer: nothing else changes


def test_the_report_is_the_checked_report_of_that_memo_and_its_charts(real_report, pdf, tmp_path):
    folder, *_ = export(tmp_path, pdf)
    memo = (folder / "memo.md").read_text(encoding="utf-8")
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    report = (folder / "report.pdf").read_bytes()

    assert report.startswith(b"%PDF-") and check.problems(report, memo, charts.build_charts(results), results) == []
    with pdfplumber.open(io.BytesIO(report)) as doc:
        text = re.sub(r"\s+", " ", " ".join(page.extract_text() or "" for page in doc.pages))
    assert "Charts" in text and "[SOURCE: p.1]" in text


def test_the_manifest_records_the_written_report_and_the_stage_count(real_report, pdf, tmp_path):
    import hashlib

    folder, *_ = export(tmp_path, pdf)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    report = (folder / "report.pdf").read_bytes()

    assert manifest["report"] == {
        "status": "written", "file": "report.pdf", "size": len(report), "sha256": hashlib.sha256(report).hexdigest(),
        "packages": manifest["report"]["packages"],
    }  # fmt: skip
    assert set(manifest["report"]["packages"]) == {"reportlab", "markdown-it-py"} and all(manifest["report"]["packages"].values())
    exported = next(e for e in manifest["stage_events"] if e["state"] == "exported")
    assert exported["counts"] == {"files": 4} and manifest["final_state"] == "exported"


def test_the_same_run_gives_a_byte_identical_report(real_report, pdf, tmp_path):
    one, *_ = export(tmp_path / "a", pdf)
    two, *_ = export(tmp_path / "b", pdf)
    assert (one / "report.pdf").read_bytes() == (two / "report.pdf").read_bytes()


def test_the_exported_log_line_counts_the_files_written(real_report, caplog, pdf, tmp_path):
    with caplog.at_level(logging.INFO, logger="credit_intel.export"):
        export(tmp_path / "a", pdf)
        export(tmp_path / "b", pdf, report=False)
    lines = [r.getMessage() for r in caplog.records if "stage=exported" in r.getMessage()]
    assert [line.rsplit(" ", 1)[1] for line in lines] == ["files=4", "files=3"]


def test_no_report_skips_it_and_the_manifest_says_so(real_report, pdf, tmp_path):
    folder, *_ = export(tmp_path, pdf, report=False)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert names(folder) == THREE and manifest["report"] == {"status": "skipped"}
    assert next(e for e in manifest["stage_events"] if e["state"] == "exported")["counts"] == {"files": 3}


def test_a_failure_record_has_no_report_entry(tmp_path):
    from credit_intel.export.run_export import export_failure
    from credit_intel.states import Recorder
    from test_export_run import BASIS, PACKAGES, VERSION, clock

    recorder = Recorder(clock())
    recorder.enter("received")
    recorder.fail(None)
    folder = export_failure(tmp_path / "runs", recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES, input_file_name="x.pdf", input_sha256="a" * 64)
    assert "report" not in json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


# --- a report that cannot be built never fails the run ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, reason, limit",
    [
        ("sys.stdout.buffer.write(b'FAIL check_failed\\n')", "check_failed", 60.0),
        ("sys.stdout.buffer.write(b'FAIL glyph_missing\\n')", "glyph_missing", 60.0),
        ("sys.exit(1)", "render_error", 60.0),
        ("time.sleep(600)", "timeout", 1.0),
    ],
)
def test_a_failed_report_leaves_a_complete_run_without_it(monkeypatch, caplog, pdf, tmp_path, code, reason, limit):
    with_stub(monkeypatch, tmp_path, code, limit)
    plain, *_ = export(tmp_path / "plain", pdf, report=False)
    with caplog.at_level(logging.WARNING, logger="credit_intel.report"):
        folder, *_ = export(tmp_path / "run", pdf)

    assert names(folder) == THREE  # no partial and no unchecked report
    for name in ("memo.md", "results.json"):
        assert (folder / name).read_bytes() == (plain / name).read_bytes()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["report"] == {"status": "failed", "reason": reason} and manifest["final_state"] == "exported" and manifest["error_code"] is None
    assert next(e for e in manifest["stage_events"] if e["state"] == "exported")["counts"] == {"files": 3}
    assert [r.getMessage() for r in caplog.records if r.name == "credit_intel.report"] == [f"report not written ({reason}); memo.md is complete"]


def test_a_defect_in_the_report_code_itself_does_not_fail_the_run(monkeypatch, caplog, pdf, tmp_path):
    def broken(memo, results=None, **kwargs):
        raise RuntimeError("a defect in the report code")

    monkeypatch.setattr(run_export, "make_report", broken)
    with caplog.at_level(logging.WARNING):
        folder, *_ = export(tmp_path, pdf)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert names(folder) == THREE and manifest["report"] == {"status": "failed", "reason": "render_error"}
    assert "report not written (render_error); memo.md is complete" in caplog.text and "defect in the report code" not in caplog.text


def test_a_failure_to_write_the_report_file_fails_the_export_and_leaves_nothing(real_report, monkeypatch, pdf, tmp_path):
    from credit_intel.export import writer

    real = writer._write_file

    def fail_on_the_pdf(directory, name, content):
        if name == "report.pdf":
            raise OSError("disk full")
        real(directory, name, content)

    monkeypatch.setattr(writer, "_write_file", fail_on_the_pdf)
    with pytest.raises(IngestionError) as error:
        export(tmp_path, pdf)
    assert error.value.code is ErrorCode.EXPORT_FAILED
    assert list((tmp_path / "runs").iterdir()) == []  # no run folder and no staging folder


# --- the command line ----------------------------------------------------------------------------------------------------------------------------------------


def test_the_command_line_writes_the_report_by_default_and_prints_only_the_run_folder(real_report, pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])
    folder = Path(out.strip())
    assert code == 0 and out.count("\n") == 1 and names(folder) == FOUR
    assert "WARNING" not in err and manifest_of(folder)["report"]["status"] == "written"


def test_no_report_on_the_command_line_skips_it(real_report, pdf, tmp_path):
    code, out, err = call(tmp_path, str(pdf), "--no-report", replies=[fx.good_response(pdf)])
    folder = Path(out.strip())
    assert code == 0 and names(folder) == THREE and manifest_of(folder)["report"] == {"status": "skipped"}


def test_a_report_that_cannot_be_built_is_a_warning_on_standard_error_and_exit_0(monkeypatch, pdf, tmp_path):
    with_stub(monkeypatch, tmp_path, "sys.stdout.buffer.write(b'FAIL check_failed\\n')")
    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])
    folder = Path(out.strip())
    assert code == 0 and names(folder) == THREE and out.count("\n") == 1
    assert "WARNING credit_intel.report report not written (check_failed); memo.md is complete" in err
    assert manifest_of(folder)["report"] == {"status": "failed", "reason": "check_failed"}


def test_markup_in_a_profile_is_printed_as_text_in_the_report_and_nothing_is_loaded(real_report, pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": '<img src="file:///etc/hosts"/>', "notes": "<a href='http://example.invalid/x'>link</a> &amp; <b>bold</b>"}), encoding="utf-8")
    code, out, err = call(tmp_path, str(pdf), "--profile", str(profile), replies=[fx.good_response(pdf)])
    folder = Path(out.strip())
    report = (folder / "report.pdf").read_bytes()
    with pdfplumber.open(io.BytesIO(report)) as doc:
        text = " ".join(page.extract_text() or "" for page in doc.pages)

    assert code == 0 and names(folder) == FOUR
    assert '<img src="file:///etc/hosts"/>' in text and "<b>bold</b>" in text
    assert b"/Subtype /Image" not in report and b"/URI" not in report and b"/Annots" not in report


def test_a_run_whose_fields_were_read_by_ocr_has_a_report_with_the_ocr_labels_and_no_ocr_value_plotted(real_report, tmp_path):
    from test_ocr_end_to_end import scan_run

    code, out, err, _ = scan_run(tmp_path)
    folder = Path(out.strip())
    memo = (folder / "memo.md").read_text(encoding="utf-8")
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    report = (folder / "report.pdf").read_bytes()

    assert code == 0 and names(folder) == FOUR and "[OCR p.1" in memo
    assert check.problems(report, memo, charts.build_charts(results), results) == []
    assert all(not slot.plotted for chart in charts.build_charts(results) for panel in chart.panels for slot in panel.slots if slot.record_id.startswith(("revenue", "net_profit")))
    with pdfplumber.open(io.BytesIO(report)) as doc:
        text = re.sub(r"\s+", " ", " ".join(page.extract_text() or "" for page in doc.pages))
    assert "[OCR p.1" in text and "ocr unconfirmed" in text.lower().replace("_", " ")
