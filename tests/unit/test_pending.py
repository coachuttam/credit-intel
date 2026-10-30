"""Marker files and the record of an interrupted run (PRD FR-016 criterion 10, OD-32 (b), E-RUN-INTERRUPTED; Phase 7 step 3)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from credit_intel.api import pending
from credit_intel.api.pending import PENDING, marker_path, pending_dir, recover_interrupted, remove_marker, write_marker
from credit_intel.config import LLMSettings
from credit_intel.export.manifest import run_id as make_run_id
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.models import StatementBasis

STARTED = datetime(2026, 10, 30, 10, 15, 30, 123456, tzinfo=UTC)
SHA = "ab" * 32
RUN = make_run_id(STARTED, SHA)
LLM = LLMSettings("openai", "gpt-4o-mini", 30000, 4096)


def marker(tmp_path, **overrides):
    arguments = dict(run_id=RUN, started=STARTED, input_file_name="report.pdf", input_sha256=SHA, requested_basis=StatementBasis.CONSOLIDATED, asserted_basis=None,
                     profile_file_name=None, llm=LLM)  # fmt: skip
    arguments.update(overrides)
    return write_marker(tmp_path, **arguments)


def manifest_of(tmp_path, run=RUN):
    return json.loads((tmp_path / run / "manifest.json").read_text(encoding="utf-8"))


# --- writing -----------------------------------------------------------------------------------------------------------------------------------


def test_a_marker_is_a_small_json_file_in_a_hidden_folder_named_for_the_run(tmp_path):
    path = marker(tmp_path)
    assert path == tmp_path / PENDING / f"{RUN}.json" == marker_path(tmp_path, RUN) and pending_dir(tmp_path) == tmp_path / ".pending"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body == {
        "marker_version": 1, "run_id": RUN, "started": STARTED.isoformat(), "input_file_name": "report.pdf", "input_sha256": SHA, "requested_basis": "consolidated",
        "asserted_basis": None, "profile_file_name": None, "llm": {"provider": "openai", "model_id": "gpt-4o-mini", "token_ceiling": 30000, "max_output_tokens": 4096},
    }  # fmt: skip


def test_a_marker_holds_names_and_options_and_no_document_or_profile_text(tmp_path):
    path = marker(tmp_path, asserted_basis=StatementBasis.STANDALONE, profile_file_name="profile.json")
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["asserted_basis"] == "standalone" and body["profile_file_name"] == "profile.json"
    assert set(body) == {"marker_version", "run_id", "started", "input_file_name", "input_sha256", "requested_basis", "asserted_basis", "profile_file_name", "llm"}


def test_writing_is_atomic_and_leaves_no_temporary_file_and_replaces_an_older_marker(tmp_path):
    marker(tmp_path)
    marker(tmp_path, input_file_name="other.pdf")
    assert sorted(p.name for p in pending_dir(tmp_path).iterdir()) == [f"{RUN}.json"]
    assert json.loads(marker_path(tmp_path, RUN).read_text(encoding="utf-8"))["input_file_name"] == "other.pdf"


def test_a_marker_is_named_only_for_a_run_id_of_the_fixed_form(tmp_path):
    for bad in ("../x", "x", "", RUN + "/..", "20261030T101530.123456Z-ABCDEF12"):
        with pytest.raises(ValueError):
            marker_path(tmp_path, bad)


def test_a_marker_that_cannot_be_written_raises_os_error_so_that_the_run_is_not_accepted(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the output folder should be", encoding="utf-8")
    with pytest.raises(OSError):
        marker(blocker)


def test_removing_a_marker_that_is_there_or_is_not_is_quiet_and_a_failure_to_remove_is_logged_not_raised(tmp_path, caplog, monkeypatch):
    marker(tmp_path)
    remove_marker(tmp_path, RUN)
    remove_marker(tmp_path, RUN)
    assert not marker_path(tmp_path, RUN).exists()
    marker(tmp_path)
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError("no")))
    with caplog.at_level("WARNING", logger="credit_intel.api"):
        remove_marker(tmp_path, RUN)
    assert "marker could not be removed" in caplog.text and RUN in caplog.text and "report.pdf" not in caplog.text


# --- recovering ------------------------------------------------------------------------------------------------------------------------------------


def test_a_leftover_marker_becomes_a_manifest_only_failure_with_the_interrupted_code_and_the_marker_is_removed(tmp_path):
    marker(tmp_path, asserted_basis=StatementBasis.STANDALONE, profile_file_name="profile.json")
    assert recover_interrupted(tmp_path) == [RUN]
    folder = tmp_path / RUN
    assert sorted(p.name for p in folder.iterdir()) == ["manifest.json"]
    record = manifest_of(tmp_path)
    assert record["final_state"] == "failed" and record["error_code"] == "E-RUN-INTERRUPTED" and record["run_id"] == RUN
    assert record["failed_stage"] == "validated"  # the first stage after `received`: the stage reached is not recorded
    assert record["started_at"] == "20261030T101530.123456Z" and record["finished_at"] == record["started_at"]
    assert record["profile_file_name"] == "profile.json" and record["requested_basis"] == "consolidated"
    assert record["basis_assertion"] == {"basis": "standalone", "pages": None, "applied_pages": None}
    assert not marker_path(tmp_path, RUN).exists()


def test_the_failure_record_names_the_input_and_the_model_settings_of_the_marker(tmp_path):
    marker(tmp_path, llm=LLMSettings("openai", "some-model", 12345, 777))
    recover_interrupted(tmp_path)
    text = json.dumps(manifest_of(tmp_path))
    assert "some-model" in text and "report.pdf" in text and SHA in text


def test_recovering_twice_records_once(tmp_path):
    marker(tmp_path)
    assert recover_interrupted(tmp_path) == [RUN]
    assert recover_interrupted(tmp_path) == []
    assert json.loads((tmp_path / RUN / "manifest.json").read_text(encoding="utf-8"))["error_code"] == "E-RUN-INTERRUPTED"


def test_a_marker_whose_run_folder_exists_is_only_removed_and_the_folder_is_left_exactly_as_it_was(tmp_path):
    (tmp_path / RUN).mkdir()
    (tmp_path / RUN / "memo.md").write_text("a finished run", encoding="utf-8")
    marker(tmp_path)
    assert recover_interrupted(tmp_path) == []
    assert not marker_path(tmp_path, RUN).exists() and [p.name for p in (tmp_path / RUN).iterdir()] == ["memo.md"]


def test_no_pending_folder_means_nothing_to_do(tmp_path):
    assert recover_interrupted(tmp_path) == [] and recover_interrupted(tmp_path / "absent") == []
    assert not (tmp_path / PENDING).exists()  # recovering does not create the folder


@pytest.mark.parametrize("damage", [
    lambda b: b.pop("llm"), lambda b: b.update(extra=1), lambda b: b.update(marker_version=2), lambda b: b.update(run_id="20261030T101530.123456Z-00000000"),
    lambda b: b.update(input_sha256="short"), lambda b: b.update(input_sha256="AB" * 32), lambda b: b.update(requested_basis="neither"),
    lambda b: b.update(asserted_basis="neither"), lambda b: b.update(started="not a time"), lambda b: b.update(started="2026-10-30T10:15:30.123456"),
    lambda b: b.update(started="2026-10-30T10:15:31.123456+00:00"), lambda b: b.update(input_file_name=5), lambda b: b.update(llm={"provider": "x"}),
    lambda b: b.update(llm=[1, 2, 3, 4])])  # fmt: skip
def test_a_marker_that_is_not_valid_is_set_aside_not_trusted_and_not_retried(tmp_path, damage, caplog):
    path = marker(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    damage(body)
    path.write_text(json.dumps(body), encoding="utf-8")
    with caplog.at_level("WARNING", logger="credit_intel.api"):
        assert recover_interrupted(tmp_path) == []
    assert not (tmp_path / RUN).exists() and not path.exists()
    assert (pending_dir(tmp_path) / f"{RUN}.json.invalid").exists() and "is not valid" in caplog.text and "report.pdf" not in caplog.text
    assert recover_interrupted(tmp_path) == []  # not looked at again


def test_a_valid_marker_under_the_name_of_another_run_is_not_trusted(tmp_path):
    marker(tmp_path)
    other = make_run_id(datetime(2026, 10, 29, tzinfo=UTC), "cd" * 32)
    marker_path(tmp_path, RUN).rename(pending_dir(tmp_path) / f"{other}.json")  # the content names RUN, the file name names another run
    assert recover_interrupted(tmp_path) == [] and not (tmp_path / RUN).exists() and not (tmp_path / other).exists()
    assert (pending_dir(tmp_path) / f"{other}.json.invalid").exists()


@pytest.mark.parametrize("sha", ["ab" * 4, "ab" * 33, "ab" * 32 + "g"])
def test_a_hash_that_is_not_sixty_four_lower_case_hex_characters_is_not_trusted_even_when_the_run_id_agrees_with_it(tmp_path, sha):
    path = marker(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["input_sha256"] = sha
    body["run_id"] = make_run_id(STARTED, sha)  # consistent with the time, so only the form of the hash is wrong
    renamed = pending_dir(tmp_path) / f"{body['run_id']}.json"
    path.unlink()
    renamed.write_text(json.dumps(body), encoding="utf-8")
    assert recover_interrupted(tmp_path) == [] and not (tmp_path / body["run_id"]).exists() and (pending_dir(tmp_path) / f"{body['run_id']}.json.invalid").exists()


def test_garbage_that_is_not_json_or_a_non_object_is_set_aside(tmp_path):
    for text in ("", "{not json", "[]", "null", "\x00\x01"):
        path = pending_dir(tmp_path) / f"{RUN}.json"
        pending_dir(tmp_path).mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        assert recover_interrupted(tmp_path) == []
        assert not path.exists()
        (pending_dir(tmp_path) / f"{RUN}.json.invalid").unlink()


def test_files_in_the_folder_that_are_not_markers_and_links_are_ignored(tmp_path):
    marker(tmp_path)
    folder = pending_dir(tmp_path)
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    (folder / "notes.json").write_text("{}", encoding="utf-8")
    other = make_run_id(datetime(2026, 10, 29, tzinfo=UTC), "cd" * 32)
    (folder / f"{other}.json").symlink_to(folder / f"{RUN}.json")
    assert recover_interrupted(tmp_path) == [RUN]
    assert (folder / "notes.txt").exists() and (folder / "notes.json").exists() and not (tmp_path / other).exists()
    assert (folder / f"{other}.json").is_symlink() and not (folder / f"{other}.json.invalid").exists()  # ignored, not even set aside


def test_a_record_that_cannot_be_written_leaves_its_marker_for_the_next_start_and_the_others_are_still_done(tmp_path, monkeypatch, caplog):
    second = make_run_id(datetime(2026, 10, 30, 11, tzinfo=UTC), "cd" * 32)
    marker(tmp_path)
    marker(tmp_path, run_id=second, started=datetime(2026, 10, 30, 11, tzinfo=UTC), input_sha256="cd" * 32)
    real = pending.export_failure
    calls = []

    def flaky(output_dir, recorder, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise IngestionError(ErrorCode.EXPORT_FAILED)
        return real(output_dir, recorder, *args, **kwargs)

    monkeypatch.setattr(pending, "export_failure", flaky)
    with caplog.at_level("WARNING", logger="credit_intel.api"):
        assert recover_interrupted(tmp_path) == [second]
    assert marker_path(tmp_path, RUN).exists() and not marker_path(tmp_path, second).exists() and "tried at the next start" in caplog.text
    monkeypatch.setattr(pending, "export_failure", real)
    assert recover_interrupted(tmp_path) == [RUN]


def test_several_markers_are_recorded_in_order(tmp_path):
    ids = []
    for hour in (9, 8, 10):
        when = datetime(2026, 10, 30, hour, tzinfo=UTC)
        sha = f"{hour:02d}" * 32
        ids.append(make_run_id(when, sha))
        marker(tmp_path, run_id=ids[-1], started=when, input_sha256=sha)
    assert recover_interrupted(tmp_path) == sorted(ids)
    assert all((tmp_path / i / "manifest.json").exists() for i in ids) and list(pending_dir(tmp_path).iterdir()) == []


def test_the_run_folder_is_the_run_id_of_the_marker_so_a_status_can_find_it(tmp_path):
    marker(tmp_path)
    recover_interrupted(tmp_path)
    from credit_intel.api.jobs import folder_status

    status = folder_status(RUN, tmp_path / RUN)
    assert status["state"] == "failed" and status["error"]["code"] == "E-RUN-INTERRUPTED" and status["files"] == ["manifest.json"]
    assert status["error"]["message"] == "The service stopped while the run was queued or running. Submit the document again." and status["stage"] == "validated"
    assert os.listdir(tmp_path / RUN) == ["manifest.json"]
