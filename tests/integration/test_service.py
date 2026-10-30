"""The service layer (PRD FR-016, v0.4.59; Phase 6 step 1): ``execute_run`` is what the command line calls, and nothing else changed.

The command line's own behaviour is pinned by ``test_cli.py``. These tests pin what the service guarantees to a second caller (the API, step 2):
it works from explicit folders instead of the current directory, it prints nothing, and a failure can still be recorded after it raised.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis
from credit_intel.service import RunProgress, RunRequest, RunServices, execute_run, record_failure
from credit_intel.states import Recorder

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
SETTINGS = '[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'


def ticks():
    it = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(it)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def config(tmp_path, provider="fake"):
    path = tmp_path / "settings.toml"
    path.write_text(SETTINGS.format(provider=provider), encoding="utf-8")
    return path


def services(pdf, replies=None):
    return RunServices(provider_factory=lambda s, e: FakeProvider(script=list(replies) if replies is not None else [fx.good_response(pdf)]),
                       assignments=pdf.parent / "none.jsonl")  # fmt: skip


def files(folder):
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_the_service_writes_to_the_folders_it_is_given_and_not_to_the_current_directory(pdf, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    out, cache = tmp_path / "out", tmp_path / "cache"
    request = RunRequest(pdf, output_dir=out, cache_dir=cache, config=config(tmp_path), no_report=True)
    folder = execute_run(request, RunProgress(Recorder(ticks())), services(pdf), {}, lambda line: None)
    assert folder.parent == out and (folder / "memo.md").is_file() and any(cache.iterdir())
    assert list(elsewhere.iterdir()) == []  # no `runs` and no `.cache` beside the caller


def test_the_service_gives_the_same_files_as_the_command_line(pdf, tmp_path, monkeypatch):
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")  # the command line's response cache is relative to here: a fresh one, as the service's own is
    cfg = config(tmp_path)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    folder_a = execute_run(RunRequest(pdf, output_dir=out_a, cache_dir=tmp_path / "ca", config=cfg, no_report=True),
                           RunProgress(Recorder(ticks())), services(pdf), {}, lambda line: None)  # fmt: skip
    import io

    out = io.StringIO()
    code = main([str(pdf), "--config", str(cfg), "--output-dir", str(out_b), "--no-report"], provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(pdf)]),
                clock=ticks(), stdout=out, stderr=io.StringIO(), assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    assert code == 0
    assert files(folder_a) == files(Path(out.getvalue().strip()))


def test_the_service_prints_nothing_and_tells_the_caller_about_the_send_notice_through_notify(pdf, tmp_path, capsys):
    notes = []
    execute_run(RunRequest(pdf, output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=config(tmp_path), no_report=True),
                RunProgress(Recorder(ticks())), services(pdf), {}, notes.append)  # fmt: skip
    seen = capsys.readouterr()
    assert seen.out == "" and seen.err == "" and notes == []  # the fake provider sends nothing off the machine


def test_a_provider_that_sends_off_the_machine_needs_the_confirmation_and_the_notice_goes_to_notify(pdf, tmp_path):
    cfg = config(tmp_path, provider="openai")
    base = dict(output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=cfg, no_report=True)
    progress = RunProgress(Recorder(ticks()))
    with pytest.raises(IngestionError) as refused:
        execute_run(RunRequest(pdf, **base), progress, services(pdf), {}, lambda line: None)
    assert refused.value.code is ErrorCode.SEND_REFUSED and not (tmp_path / "o").exists()
    notes = []
    execute_run(RunRequest(pdf, confirm_public_document=True, **base), RunProgress(Recorder(ticks())), services(pdf), {}, notes.append)
    assert len(notes) == 1 and "sent" in notes[0].lower()


def test_a_run_with_the_report_switched_on_writes_report_pdf_and_no_report_does_not(pdf, tmp_path, real_report):
    cfg = config(tmp_path)
    for flag, expected in ((False, True), (True, False)):
        folder = execute_run(RunRequest(pdf, output_dir=tmp_path / f"o{flag}", cache_dir=tmp_path / f"c{flag}", config=cfg, no_report=flag),
                             RunProgress(Recorder(ticks())), services(pdf), {}, lambda line: None)  # fmt: skip
        assert (folder / "report.pdf").exists() is expected


def test_the_request_options_reach_the_run(pdf, tmp_path):
    request = RunRequest(pdf, basis=StatementBasis.CONSOLIDATED, output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=config(tmp_path), no_report=True)
    folder = execute_run(request, RunProgress(Recorder(ticks())), services(pdf), {}, lambda line: None)
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["requested_basis"] == "consolidated"


def test_a_missing_input_raises_not_found_before_anything_is_recorded(tmp_path):
    progress = RunProgress(Recorder(ticks()))
    request = RunRequest(tmp_path / "absent.pdf", output_dir=tmp_path / "o", config=config(tmp_path))
    with pytest.raises(IngestionError) as error:
        execute_run(request, progress, RunServices(assignments=tmp_path / "none.jsonl"), {}, lambda line: None)
    assert error.value.code is ErrorCode.NOT_FOUND and progress.sha256 is None
    assert record_failure(request, progress, error.value) is None and not (tmp_path / "o").exists()


def test_a_failure_after_the_run_was_recorded_leaves_a_manifest_only_folder_and_returns_it(pdf, tmp_path):
    progress = RunProgress(Recorder(ticks()))
    request = RunRequest(pdf, output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=config(tmp_path), no_report=True)
    with pytest.raises(Exception) as error:
        execute_run(request, progress, services(pdf, replies=[]), {}, lambda line: None)  # the fake provider has no reply to give
    folder = record_failure(request, progress, error.value)
    assert folder is not None and sorted(p.name for p in folder.iterdir()) == ["manifest.json"]
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["final_state"] == "failed"
    assert os.listdir(tmp_path / "o") == [folder.name]


def test_a_failure_of_the_export_itself_is_not_recorded(pdf, tmp_path):
    progress = RunProgress(Recorder(ticks()))
    request = RunRequest(pdf, output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=config(tmp_path), no_report=True)
    with pytest.raises(Exception):
        execute_run(request, progress, services(pdf, replies=[]), {}, lambda line: None)  # recorded far enough to have a failure record
    assert record_failure(request, progress, IngestionError(ErrorCode.EXPORT_FAILED)) is None and not (tmp_path / "o").exists()


def test_a_requested_standalone_basis_reaches_the_run_and_its_manifest(tmp_path):
    two = fx.two_basis_pdf(tmp_path / "two.pdf")
    reply = fx.reply(fx.good_attributes(two), fx.standalone_fields(two))
    request = RunRequest(two, basis=StatementBasis.STANDALONE, output_dir=tmp_path / "o", cache_dir=tmp_path / "c", config=config(tmp_path), no_report=True)
    folder = execute_run(request, RunProgress(Recorder(ticks())), services(two, replies=[reply]), {}, lambda line: None)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requested_basis"] == "standalone" and manifest["final_state"] == "exported"
