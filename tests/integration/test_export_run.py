"""Exporting a run: the three files, the last two states, and failure (PRD FR-009 to FR-012; Phase 5 step 5j; B-268)."""

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unit"))  # the memo checker lives with the unit tests

import pipeline_fixture as fx  # noqa: E402
from credit_intel.export.manifest import CodeVersion, run_id  # noqa: E402
from credit_intel.export.run_export import export_failure, export_run  # noqa: E402
from credit_intel.ingestion.errors import ErrorCode, IngestionError  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from credit_intel.models import StatementBasis  # noqa: E402
from credit_intel.run import run_pipeline  # noqa: E402
from credit_intel.states import STATES, Recorder  # noqa: E402
from memo_trace import problems  # noqa: E402

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
VERSION = CodeVersion("a" * 40, False)
PACKAGES = {"openai": "1.0", "pdfplumber": "2.0", "pydantic": "3.0", "python": "3.12.0"}
BASIS = StatementBasis.CONSOLIDATED
GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "results_golden.json"


def clock(start=START):
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(1000))
    return lambda: next(ticks)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def run(pdf, cache, recorder, **kw):
    return run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, recorder=recorder, cache_dir=cache, **kw)


def export(tmp_path, pdf, out=None, start=START, **kw):
    recorder = Recorder(clock(start))
    result = run(pdf, tmp_path / "cache", recorder)
    path = export_run(out or tmp_path / "runs", result, recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES, **kw)
    return path, result, recorder


def test_a_run_folder_with_the_three_files_is_written_and_named_by_the_run_id(pdf, tmp_path):
    path, result, recorder = export(tmp_path, pdf)

    assert path.name == run_id(START, result.extraction.source_document.sha256) == "20261024T101530.123456Z-" + result.extraction.source_document.sha256[:8]
    assert sorted(p.name for p in path.iterdir()) == ["manifest.json", "memo.md", "results.json"]
    assert [p.name for p in (tmp_path / "runs").iterdir()] == [path.name]


def test_results_json_is_the_reviewed_golden_file(pdf, tmp_path):
    path, *_ = export(tmp_path, pdf)

    assert (path / "results.json").read_bytes() == GOLDEN.read_bytes()


def test_the_memo_is_traceable_to_the_written_results_and_names_the_run(pdf, tmp_path):
    path, *_ = export(tmp_path, pdf)
    results = json.loads((path / "results.json").read_text(encoding="utf-8"))
    memo = (path / "memo.md").read_text(encoding="utf-8")

    assert problems(memo, results) == [] and f"`{path.name}`" in memo
    assert re.search(r"\*\*Generated:\*\* `20261024T101530\.\d{6}Z` \(UTC\)", memo)


def test_the_manifest_records_all_ten_states_and_exported_as_the_final_state(pdf, tmp_path):
    path, result, recorder = export(tmp_path, pdf, profile_file_name=None)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))

    assert [e["state"] for e in manifest["stage_events"]] == list(STATES) and manifest["final_state"] == "exported"
    assert manifest["error_code"] is None and manifest["failed_stage"] is None and manifest["run_id"] == path.name
    assert manifest["finished_at"] == manifest["stage_events"][-1]["at"] and recorder.final_state == "exported"


def test_the_profile_file_name_is_in_the_manifest_and_its_values_only_in_results_and_the_memo(pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "Zebra Ltd"}), encoding="utf-8")
    recorder = Recorder(clock())
    result = run(pdf, tmp_path / "cache", recorder, profile_path=profile)
    path = export_run(tmp_path / "runs", result, recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES, profile_file_name=profile.name)

    assert "profile.json" in (path / "manifest.json").read_text(encoding="utf-8") and "Zebra" not in (path / "manifest.json").read_text(encoding="utf-8")
    assert "Zebra Ltd" in (path / "results.json").read_text(encoding="utf-8") and "Zebra Ltd [ANALYST-PROVIDED]" in (path / "memo.md").read_text(encoding="utf-8")


def test_a_second_export_of_the_same_run_id_is_refused_and_the_first_is_untouched(pdf, tmp_path):
    first, *_ = export(tmp_path, pdf)
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    recorder = Recorder(clock())
    result = run(pdf, tmp_path / "cache", recorder)

    with pytest.raises(IngestionError) as caught:
        export_run(tmp_path / "runs", result, recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES)

    assert caught.value.code is ErrorCode.EXPORT_FAILED
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before and [p.name for p in (tmp_path / "runs").iterdir()] == [first.name]
    assert (recorder.final_state, recorder.failed_stage, recorder.error_code) == ("failed", "exported", "E-EXPORT-FAILED")


def test_a_later_run_of_the_same_document_gets_its_own_folder_with_the_same_results(pdf, tmp_path):
    first, *_ = export(tmp_path, pdf)
    second, *_ = export(tmp_path, pdf, start=START + timedelta(seconds=5))

    assert first != second and first.name[-8:] == second.name[-8:]
    assert (first / "results.json").read_bytes() == (second / "results.json").read_bytes()
    assert (first / "manifest.json").read_bytes() != (second / "manifest.json").read_bytes()
    strip = lambda p: re.sub(r"20\d{6}T\d{6}\.\d{6}Z", "T", (p / "memo.md").read_text(encoding="utf-8"))  # noqa: E731
    assert strip(first) == strip(second)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_an_output_directory_that_cannot_be_written_fails_with_the_export_code_and_leaves_nothing(pdf, tmp_path):
    out = tmp_path / "locked"
    out.mkdir()
    out.chmod(0o500)
    try:
        recorder = Recorder(clock())
        result = run(pdf, tmp_path / "cache", recorder)
        with pytest.raises(IngestionError) as caught:
            export_run(out, result, recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES)
    finally:
        out.chmod(0o700)

    assert caught.value.code is ErrorCode.EXPORT_FAILED and list(out.iterdir()) == []
    assert (recorder.final_state, recorder.failed_stage, recorder.error_code) == ("failed", "exported", "E-EXPORT-FAILED")


def test_an_internal_error_while_making_the_memo_is_recorded_as_a_failure_without_a_code(pdf, tmp_path, monkeypatch):
    monkeypatch.setattr("credit_intel.export.run_export.render_memo", lambda *a, **k: 1 / 0)
    recorder = Recorder(clock())
    result = run(pdf, tmp_path / "cache", recorder)

    with pytest.raises(ZeroDivisionError):
        export_run(tmp_path / "runs", result, recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES)

    assert (recorder.final_state, recorder.failed_stage, recorder.error_code) == ("failed", "memo_generated", None)
    assert not (tmp_path / "runs").exists() or list((tmp_path / "runs").iterdir()) == []


def test_the_export_is_logged_with_the_run_id_and_no_document_text(pdf, tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="credit_intel"):
        path, *_ = export(tmp_path, pdf)

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert f"stage=exported run={path.name} files=3" in text
    for forbidden in ("Total current assets", "1,482.30", "Acme", "statement.pdf", str(tmp_path)):
        assert forbidden not in text


# --- a failed run -----------------------------------------------------------------------------------------------------------------------------


def test_a_failed_run_can_leave_a_folder_with_only_a_manifest_that_says_it_failed(tmp_path):
    blank = fx.blank_text_pdf(tmp_path / "blank.pdf")
    recorder = Recorder(clock())
    with pytest.raises(IngestionError):
        run_pipeline(blank, FakeProvider(script=[]), fx.LLM, recorder=recorder, cache_dir=tmp_path / "cache")

    path = export_failure(tmp_path / "runs", recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES,
                          input_file_name="blank.pdf", input_sha256="b" * 64)  # fmt: skip
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))

    assert [p.name for p in path.iterdir()] == ["manifest.json"] and path.name.endswith("-bbbbbbbb")
    assert (manifest["final_state"], manifest["error_code"], manifest["failed_stage"]) == ("failed", "E-EXTRACT-NO-STATEMENT-PAGES", "fields_extracted")


def test_a_manifest_only_folder_is_refused_for_a_run_that_did_not_fail(pdf, tmp_path):
    recorder = Recorder(clock())
    run(pdf, tmp_path / "cache", recorder)

    with pytest.raises(ValueError):
        export_failure(tmp_path / "runs", recorder, fx.LLM, requested_basis=BASIS, version=VERSION, packages=PACKAGES, input_file_name="x.pdf", input_sha256="c" * 64)
