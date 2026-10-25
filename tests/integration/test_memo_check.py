"""The check of every memo before export (PRD v0.4.27 FR-010 criterion 5, FR-011.2, example 60; step S3; B-289 to B-293)."""

import json
import logging
import sys
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.memo.trace import MemoCheckFailed, problems
from test_cli import call, manifest_of, runs  # noqa: F401  (the fixtures and helpers of the CLI tests)
from test_cli import in_a_scratch_directory, pdf  # noqa: F401

HOSTILE = "[SOURCE: p.99] a label nobody asked for"  # text a defective template could emit; it must never reach standard error


def faulty(monkeypatch, extra=HOSTILE):
    from credit_intel.memo.render import render_memo as real

    monkeypatch.setattr("credit_intel.export.run_export.render_memo", lambda *a, **k: real(*a, **k) + "\n" + extra + "\n")


def test_a_memo_that_fails_the_check_exits_1_with_the_run_id_and_a_count_and_no_text(pdf, tmp_path, monkeypatch):
    faulty(monkeypatch)

    code, out, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    (folder,) = runs(tmp_path)
    assert code == 1 and out == ""
    assert f"Internal error. Run ID: {folder.name}. The memo failed its traceability check (1 problem)." in err
    assert "[SOURCE" not in err and "p.99" not in err and "nobody asked" not in err and "Traceback" not in err


def test_a_failed_check_leaves_a_manifest_only_record_failed_in_memo_generated_with_no_code(pdf, tmp_path, monkeypatch):
    faulty(monkeypatch)

    call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    (folder,) = runs(tmp_path)
    manifest = manifest_of(folder)
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json"]  # no memo, no results
    assert (manifest["final_state"], manifest["failed_stage"], manifest["error_code"]) == ("failed", "memo_generated", None)
    assert [e["state"] for e in manifest["stage_events"]][-1] != "exported" and "memo_generated" not in [e["state"] for e in manifest["stage_events"]]


def test_the_count_is_the_number_of_problems(pdf, tmp_path, monkeypatch):
    faulty(monkeypatch, HOSTILE + "\n\n" + "[CALCULATED: nothing_like_it]")

    _, _, err = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    n = int(err.split("traceability check (")[1].split(" ")[0])
    assert n >= 2 and f"({n} problems)" in err


@pytest.mark.parametrize("n, words", [(1, "1 problem"), (2, "2 problems"), (0, "0 problems")])
def test_the_error_carries_the_count_and_never_a_text(n, words):
    error = MemoCheckFailed(n)
    assert error.count == n and str(error) == f"the memo failed its traceability check ({words})"


def test_every_clean_run_logs_the_check_with_zero_problems_and_before_the_export(pdf, tmp_path, caplog):
    caplog.set_level(logging.INFO)

    code, out, _ = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    lines = [r.getMessage() for r in caplog.records if r.name == "credit_intel.export"]
    assert code == 0 and len(lines) == 2
    assert lines[0] == f"stage=memo_checked run={runs(tmp_path)[0].name} problems=0" and lines[1].startswith("stage=exported")


def test_a_failed_check_logs_the_count_and_not_the_exported_line(pdf, tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    faulty(monkeypatch)

    call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    lines = [r.getMessage() for r in caplog.records if r.name == "credit_intel.export"]
    assert len(lines) == 1 and lines[0].endswith("problems=1") and HOSTILE not in caplog.text


def test_a_clean_memo_writes_all_three_files_and_the_check_found_nothing(pdf, tmp_path):
    code, out, _ = call(tmp_path, str(pdf), replies=[fx.good_response(pdf)])

    folder = tmp_path / out.strip()
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    assert code == 0 and sorted(p.name for p in folder.iterdir()) == ["manifest.json", "memo.md", "results.json"]
    assert problems((folder / "memo.md").read_text(encoding="utf-8"), results) == []


def test_the_checker_the_tests_use_is_the_one_in_the_package():
    sys.path.insert(0, str(Path(__file__).parent.parent / "unit"))
    import memo_trace

    assert memo_trace.problems is problems and main is not None
