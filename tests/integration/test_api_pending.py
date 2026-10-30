"""Marker files, the record of an interrupted run, the start-up clean-up and ``prune`` through the service and the launcher (PRD FR-016 criterion 10, SEC-14, SEC-18, OD-32,
OD-40; Phase 7 step 3). The pieces are tested alone in ``test_pending.py`` and ``test_retention.py``."""

import io
import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api import __main__ as launcher
from credit_intel.api import app as app_module
from credit_intel.api.jobs import Closing, JobManager, QueueFull
from credit_intel.api.pending import PENDING, marker_path, pending_dir, write_marker
from credit_intel.api.retention import UPLOAD_PREFIX
from credit_intel.config import LLMSettings
from credit_intel.export.manifest import run_id as make_run_id
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.models import StatementBasis

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def markers(settings):
    folder = settings.output_dir / PENDING
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def run_folders(settings):
    return sorted(p.name for p in settings.output_dir.iterdir() if p.name != PENDING) if settings.output_dir.is_dir() else []


# --- the marker through the life of a run ----------------------------------------------------------------------------------------------------


def test_the_marker_is_there_while_the_run_is_waiting_and_going_and_gone_when_it_has_ended(pdf, tmp_path):
    gate = base.Gate(pdf)
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=1, factory=gate)
    with TestClient(app) as client:
        first = base.post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        assert gate.entered.acquire(timeout=30)
        second = base.post(client, pdf.read_bytes() + b"\n%2", no_report=True).json()["run_id"]
        assert markers(settings) == sorted([f"{first}.json", f"{second}.json"])  # one running, one waiting
        gate.release.set()
        base.wait(client, first)
        base.wait(client, second)
        end = time.monotonic() + 10
        while markers(settings) and time.monotonic() < end:
            time.sleep(0.02)
    assert markers(settings) == [] and sorted(run_folders(settings)) == sorted([first, second])


def test_a_failed_run_also_ends_with_its_marker_removed(tmp_path):
    bad = b"%PDF-1.4\nnot a real pdf\n"
    app, settings = base.build(tmp_path, fx.balance_sheet_pdf(tmp_path / "x.pdf"))
    with TestClient(app) as client:
        run_id = base.post(client, bad).json()["run_id"]
        assert base.wait(client, run_id)["state"] == "failed"
        end = time.monotonic() + 10
        while markers(settings) and time.monotonic() < end:
            time.sleep(0.02)
    assert markers(settings) == []


def test_the_marker_is_written_before_the_run_is_handed_to_the_pool_and_so_before_the_202(pdf, tmp_path, monkeypatch):
    app, settings = base.build(tmp_path, pdf)
    seen = []
    real = JobManager.submit

    def checking(self, job, **kwargs):
        seen.append(marker_path(settings.output_dir, job.run_id).is_file())
        return real(self, job, **kwargs)

    monkeypatch.setattr(JobManager, "submit", checking)
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == 202
    assert seen == [True]


def test_what_is_in_the_marker_is_what_a_failure_record_needs_and_nothing_of_the_document(pdf, tmp_path):
    gate = base.Gate(pdf)
    app, settings = base.build(tmp_path, pdf, factory=gate)
    profile = json.dumps({"borrower_name": "SECRET BORROWER"})
    with TestClient(app) as client:
        run_id = base.post(client, pdf.read_bytes(), name="my report.pdf", no_report=True, profile=profile, pages="1", assert_basis="consolidated").json()["run_id"]
        assert gate.entered.acquire(timeout=30)
        text = marker_path(settings.output_dir, run_id).read_text(encoding="utf-8")
        gate.release.set()
        base.wait(client, run_id)
    body = json.loads(text)
    assert body["input_file_name"] == "my report.pdf" and body["profile_file_name"] == "profile.json" and body["asserted_basis"] == "consolidated"
    assert body["requested_basis"] == "consolidated" and body["run_id"] == run_id and body["llm"]["provider"] == "fake"
    assert "SECRET" not in text and "Acme" not in text


@pytest.mark.parametrize("raised, status", [(QueueFull(), 429), (Closing(), 503)])
def test_a_run_the_pool_refuses_after_the_marker_was_written_leaves_no_marker_and_no_upload(pdf, tmp_path, monkeypatch, private_temp, raised, status):
    app, settings = base.build(tmp_path, pdf)

    def refuse(self, job, **kwargs):
        with self._lock:  # as the real `submit(reserved=True)`: the place is used up whether the run is queued or refused
            self._uploading -= 1
        raise raised

    monkeypatch.setattr(JobManager, "submit", refuse)
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == status
    assert markers(settings) == [] and base.upload_leftovers(private_temp) == [] and app.state.jobs.uploading == 0


def test_a_second_submission_of_the_same_document_at_the_same_instant_is_refused_and_does_not_take_the_first_runs_marker(pdf, tmp_path, monkeypatch):
    gate = base.Gate(pdf)
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=2, factory=gate, clock=lambda: datetime(2026, 10, 30, tzinfo=UTC))
    written = []
    real = app_module.write_marker
    monkeypatch.setattr(app_module, "write_marker", lambda *a, **k: written.append(k["run_id"]) or real(*a, **k))
    with TestClient(app) as client:
        first = base.post(client, pdf.read_bytes(), no_report=True)
        assert gate.entered.acquire(timeout=30)
        again = base.post(client, pdf.read_bytes(), no_report=True)
        assert again.status_code == 422 and again.json()["code"] == "E-API-REQUEST"
        assert markers(settings) == [f"{first.json()['run_id']}.json"]  # the first run's marker is still there
        assert written == [first.json()["run_id"]]  # and the refused one never wrote one at all
        gate.release.set()
        base.wait(client, first.json()["run_id"])


def test_a_marker_that_cannot_be_written_means_the_run_is_not_accepted_and_nothing_is_left(pdf, tmp_path, monkeypatch, private_temp):
    app, settings = base.build(tmp_path, pdf)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(app_module, "write_marker", broken)
    with TestClient(app, raise_server_exceptions=False) as client:
        answer = base.post(client, pdf.read_bytes(), no_report=True)
        assert answer.status_code == 500 and "disk full" not in answer.text
        assert client.get("/health").json() == {"status": "ok", "queued": 0, "running": 0}
    assert app.state.jobs.uploading == 0 and base.upload_leftovers(private_temp) == [] and run_folders(settings) == []


# --- the restart ---------------------------------------------------------------------------------------------------------------------------------


def interrupted_service(tmp_path, pdf):
    """A service that stops with one run going and one waiting. Returns both run IDs and the settings; the running one finishes after the stop."""
    gate = base.Gate(pdf)
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=2, factory=gate)
    with TestClient(app) as client:
        running = base.post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        assert gate.entered.acquire(timeout=30)
        waiting = base.post(client, pdf.read_bytes() + b"\n%2", no_report=True).json()["run_id"]
    gate.release.set()  # the stop did not wait for the run that was going
    end = time.monotonic() + 30
    while app.state.jobs.counts["running"] and time.monotonic() < end:
        time.sleep(0.02)
    return running, waiting, settings


def test_a_run_that_was_waiting_when_the_service_stopped_is_reported_failed_and_interrupted_after_the_restart(pdf, tmp_path):
    running, waiting, settings = interrupted_service(tmp_path, pdf)
    assert markers(settings) == [f"{waiting}.json"]  # the one that was going ended and removed its marker; the waiting one never started
    again, _ = base.build(tmp_path, pdf)
    with TestClient(again) as client:
        status = client.get(f"/runs/{waiting}").json()
        assert status["state"] == "failed" and status["error"] == {"code": "E-RUN-INTERRUPTED", "message": "The service stopped while the run was queued or running. Submit the document again."}
        assert status["files"] == ["manifest.json"] and client.get(f"/runs/{waiting}/memo").status_code == 404 and client.get(f"/runs/{waiting}/manifest").status_code == 200
        assert {r["run_id"]: r["state"] for r in client.get("/runs").json()["runs"]} == {waiting: "failed", running: "exported"}
        assert client.get(f"/runs/{running}").json()["state"] == "exported"
    assert markers(settings) == []


def test_a_third_start_changes_nothing(pdf, tmp_path):
    _, waiting, settings = interrupted_service(tmp_path, pdf)
    for _ in range(2):
        again, _ = base.build(tmp_path, pdf)
        with TestClient(again):
            pass
    record = json.loads((settings.output_dir / waiting / "manifest.json").read_text(encoding="utf-8"))
    assert record["error_code"] == "E-RUN-INTERRUPTED" and run_folders(settings).count(waiting) == 1


def test_the_records_are_made_before_the_first_request_is_answered(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    started = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    sha = "ef" * 32
    run_id = make_run_id(started, sha)
    write_marker(settings.output_dir, run_id=run_id, started=started, input_file_name="a.pdf", input_sha256=sha, requested_basis=StatementBasis.CONSOLIDATED,
                 asserted_basis=None, profile_file_name=None, llm=LLMSettings("fake", "m", 1000, 2000))  # fmt: skip
    with TestClient(app) as client:
        assert client.get(f"/runs/{run_id}").json()["error"]["code"] == "E-RUN-INTERRUPTED"


def test_a_clean_up_step_that_fails_does_not_stop_the_service_from_starting(pdf, tmp_path, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(app_module, "recover_interrupted", broken)
    monkeypatch.setattr(app_module, "sweep_stale_uploads", broken)
    app, _ = base.build(tmp_path, pdf)
    with caplog.at_level("WARNING", logger="credit_intel.api"):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
    assert caplog.text.count("a start-up clean-up step failed") == 2 and "secret detail" not in caplog.text


def test_starting_removes_the_uploads_of_processes_that_are_gone_and_keeps_those_of_a_living_one(pdf, tmp_path, private_temp):
    gone = private_temp / f"{UPLOAD_PREFIX}4000001-aaaaaa"
    living = private_temp / f"{UPLOAD_PREFIX}{os.getppid()}-bbbbbb"  # the parent of this test process is running and is not this process
    for folder in (gone, living):
        folder.mkdir()
        (folder / "x.pdf").write_bytes(b"%PDF-")
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app):
        pass
    assert not gone.exists() and living.exists()


def test_uploads_are_made_in_a_directory_named_for_this_process(pdf, tmp_path, private_temp):
    gate = base.Gate(pdf)
    app, _ = base.build(tmp_path, pdf, factory=gate)
    with TestClient(app) as client:
        base.post(client, pdf.read_bytes(), no_report=True)
        assert gate.entered.acquire(timeout=30)
        assert [p.name.startswith(f"{UPLOAD_PREFIX}{os.getpid()}-") for p in private_temp.iterdir()] == [True]
        gate.release.set()


# --- prune, through the launcher ---------------------------------------------------------------------------------------------------------------


def settings_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(base.LLM.format(provider="fake") + "[ingestion]\nparse_timeout_seconds = 700\nparse_memory_mb = 1024\n"
                    "[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\n", encoding="utf-8")
    return path


def folders_env(tmp_path):
    return {"CREDIT_INTEL_API_OUTPUT_DIR": str(tmp_path / "out"), "CREDIT_INTEL_API_CACHE_DIR": str(tmp_path / "cache")}


def old_run(tmp_path, name="20200101T000000.000000Z-abcdef12"):
    folder = tmp_path / "out" / name
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    return folder


def prune_cli(tmp_path, *args, env=...):
    out, err = io.StringIO(), io.StringIO()
    never = lambda *a, **k: (_ for _ in ()).throw(AssertionError("prune must not start the service or measure memory"))  # noqa: E731
    code = launcher.main(["prune", "--config", str(settings_file(tmp_path)), *args], env=folders_env(tmp_path) if env is ... else env, stdout=out, stderr=err, serve=never, check_memory=never, container_limit=never)
    return code, out.getvalue(), err.getvalue()


def test_prune_dry_run_lists_and_removes_nothing(tmp_path):
    run = old_run(tmp_path)
    code, out, err = prune_cli(tmp_path, "--older-than", "30", "--dry-run")
    assert code == 0 and err == "" and run.exists()
    assert "would remove run 20200101T000000.000000Z-abcdef12" in out and out.rstrip().endswith("dry run: nothing was removed")


def test_prune_lists_and_removes_an_old_staging_folder_too(tmp_path):
    staging = tmp_path / "out" / ".20200101T000000.000000Z-abcdef12.Ab_9x.partial"
    staging.mkdir(parents=True)
    code, out, _ = prune_cli(tmp_path, "--older-than", "30", "--dry-run")
    assert code == 0 and staging.exists() and "would remove staging folder .20200101T000000.000000Z-abcdef12.Ab_9x.partial" in out and "0 run folders, 1 staging folders" in out
    code, out, _ = prune_cli(tmp_path, "--older-than", "30")
    assert code == 0 and not staging.exists() and "removed staging folder" in out


def test_prune_removes_the_old_run_folder_and_keeps_a_young_one(tmp_path):
    old = old_run(tmp_path)
    young = old_run(tmp_path, datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ") + "-abcdef12")
    code, out, _ = prune_cli(tmp_path, "--older-than", "30")
    assert code == 0 and not old.exists() and young.exists() and "removed run 20200101T000000.000000Z-abcdef12" in out and "removed 1 run folders" in out


@pytest.mark.parametrize("args", [[], ["--dry-run"], ["--older-than"], ["--older-than", "0"], ["--older-than", "-5"], ["--older-than", "x"], ["--older-than", "1.5"], ["--older-than", "30", "--bogus"]])
def test_prune_needs_a_whole_number_of_days_of_at_least_one_and_has_no_default(tmp_path, args, capsys):
    run = old_run(tmp_path)
    with pytest.raises(SystemExit) as stop:
        prune_cli(tmp_path, *args)
    assert stop.value.code == 2 and run.exists()
    assert "--older-than" in capsys.readouterr().err


def test_prune_with_a_bad_settings_file_is_the_catalogued_config_error_and_removes_nothing(tmp_path):
    run = old_run(tmp_path)
    code, out, err = prune_cli(tmp_path, "--older-than", "30", env={})  # the two folders are not set
    assert code == 6 and out == "" and err.startswith("E-CONFIG-INVALID: ") and "api.output_dir" in err and run.exists()


def test_prune_is_a_command_of_the_launcher_and_the_server_is_still_the_default(tmp_path):
    served = []
    code = launcher.main(["--config", str(settings_file(tmp_path))], env=folders_env(tmp_path), stderr=io.StringIO(), serve=lambda *a: served.append(a), container_limit=lambda: None)
    assert code == 0 and len(served) == 1


def test_prune_as_a_separate_process_with_the_environment_only(tmp_path):
    run = old_run(tmp_path)
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), **folders_env(tmp_path)}
    done = subprocess.run([sys.executable, "-m", "credit_intel.api", "prune", "--config", str(settings_file(tmp_path)), "--older-than", "30", "--dry-run"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0 and "would remove run" in done.stdout and run.exists()
    done = subprocess.run([sys.executable, "-m", "credit_intel.api", "prune", "--config", str(settings_file(tmp_path)), "--older-than", "30"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)  # fmt: skip
    assert done.returncode == 0 and not run.exists()
    done = subprocess.run([sys.executable, "-m", "credit_intel.api", "prune", "--config", str(settings_file(tmp_path))], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 2 and "--older-than" in done.stderr
