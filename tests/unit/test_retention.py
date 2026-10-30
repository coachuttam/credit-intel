"""The sweep of orphaned uploads and ``prune`` (PRD SEC-14, SEC-18, OD-40; Phase 7 step 3)."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from credit_intel.api.retention import LEGACY_UPLOAD_AGE, UPLOAD_PREFIX, PruneReport, prune, render, sweep_stale_uploads, upload_prefix
from credit_intel.config import ApiSettings

NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
DEAD, ALIVE, OWN = 4_000_001, 4_000_002, 4_000_003


def settings(tmp_path):
    return ApiSettings(1, 4, 1200, tmp_path / "out", tmp_path / "cache")


def make_dir(root, name, age_days=0.0, *, content="x"):
    path = root / name
    path.mkdir(parents=True)
    (path / "file.bin").write_text(content, encoding="utf-8")
    moved = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (moved, moved))
    return path


def run_id(days_old, suffix="abcdef12"):
    return (NOW - timedelta(days=days_old)).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + suffix


def make_run(tmp_path, days_old, suffix="abcdef12"):
    folder = tmp_path / "out" / run_id(days_old, suffix)
    folder.mkdir(parents=True)
    (folder / "memo.md").write_text("m", encoding="utf-8")
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    return folder


def make_entry(tmp_path, name, age_days):
    folder = tmp_path / "cache"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text("{}", encoding="utf-8")
    moved = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (moved, moved))
    return path


KEY = "a" * 64
OLD_KEY = "b" * 64


# --- the sweep --------------------------------------------------------------------------------------------------------------------------------------


def swept(tmp_path, **kwargs):
    return sweep_stale_uploads(tmp_path, pid=OWN, alive=lambda pid: pid == ALIVE, now=lambda: NOW, **kwargs)


def test_the_upload_directory_is_named_for_the_process_that_made_it():
    assert upload_prefix(123) == f"{UPLOAD_PREFIX}123-" and upload_prefix() == f"{UPLOAD_PREFIX}{os.getpid()}-"
    assert UPLOAD_PREFIX == "credit-intel-upload-"


def test_a_directory_of_a_process_that_is_gone_or_of_this_process_s_own_number_is_removed_and_one_of_a_living_other_process_is_kept(tmp_path):
    dead = make_dir(tmp_path, f"{UPLOAD_PREFIX}{DEAD}-abc123")
    alive = make_dir(tmp_path, f"{UPLOAD_PREFIX}{ALIVE}-def456")
    own = make_dir(tmp_path, f"{UPLOAD_PREFIX}{OWN}-ghi789")  # nothing of this process exists yet: an earlier life with the same number left it
    assert swept(tmp_path) == sorted([dead.name, own.name])
    assert not dead.exists() and not own.exists() and alive.exists()


def test_a_directory_of_this_process_s_own_number_goes_even_though_that_process_is_of_course_running(tmp_path):
    own = make_dir(tmp_path, f"{UPLOAD_PREFIX}{OWN}-ghi789")
    other = make_dir(tmp_path, f"{UPLOAD_PREFIX}{ALIVE}-jkl012")
    assert sweep_stale_uploads(tmp_path, pid=OWN, alive=lambda pid: True, now=lambda: NOW) == [own.name]  # every number is "alive" here, as the real own number is
    assert not own.exists() and other.exists()


def test_a_directory_from_before_the_name_carried_a_number_goes_only_when_it_is_a_day_old(tmp_path):
    young = make_dir(tmp_path, f"{UPLOAD_PREFIX}abc123", age_days=0.5)
    boundary = make_dir(tmp_path, f"{UPLOAD_PREFIX}def456", age_days=LEGACY_UPLOAD_AGE.days)
    old = make_dir(tmp_path, f"{UPLOAD_PREFIX}ghi789", age_days=3)
    assert swept(tmp_path) == sorted([boundary.name, old.name])
    assert young.exists() and not boundary.exists() and not old.exists()


def test_only_directories_with_the_exact_name_are_touched(tmp_path):
    keep = [make_dir(tmp_path, "something-else"), make_dir(tmp_path, f"x{UPLOAD_PREFIX}{DEAD}-a"), make_dir(tmp_path, "credit-intel-upload"), make_dir(tmp_path, "credit-intel-uploads-1-a")]
    plain_file = tmp_path / f"{UPLOAD_PREFIX}{DEAD}-file"
    plain_file.write_text("a file, not a folder", encoding="utf-8")
    assert swept(tmp_path) == []
    assert all(p.exists() for p in keep) and plain_file.exists()


def test_a_link_is_never_followed_or_removed(tmp_path):
    target = make_dir(tmp_path / "elsewhere", "precious")
    link = tmp_path / f"{UPLOAD_PREFIX}{DEAD}-link"
    link.symlink_to(target, target_is_directory=True)
    assert swept(tmp_path) == []
    assert link.is_symlink() and (target / "file.bin").exists()


def test_a_directory_of_another_user_is_not_touched(tmp_path, monkeypatch):
    other = make_dir(tmp_path, f"{UPLOAD_PREFIX}{DEAD}-theirs")
    monkeypatch.setattr(os, "getuid", lambda: os.stat(other).st_uid + 1)
    assert swept(tmp_path) == [] and other.exists()


def test_a_missing_or_unreadable_temporary_folder_is_not_an_error(tmp_path):
    assert swept(tmp_path / "absent") == []


def test_the_sweep_is_quiet_about_what_is_in_the_directories(tmp_path, caplog):
    make_dir(tmp_path, f"{UPLOAD_PREFIX}{DEAD}-abc", content="SECRET DOCUMENT WORDS")
    with caplog.at_level("INFO", logger="credit_intel.api"):
        swept(tmp_path)
    assert "swept 1 orphaned upload" in caplog.text and "SECRET" not in caplog.text and "abc" not in caplog.text


# --- prune: what it removes ---------------------------------------------------------------------------------------------------------------------


def test_prune_removes_whole_run_folders_that_are_at_least_the_given_days_old_by_their_run_id(tmp_path):
    old, boundary, young = make_run(tmp_path, 40, "00000001"), make_run(tmp_path, 30, "00000002"), make_run(tmp_path, 29.9, "00000003")
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert report.runs == sorted([old.name, boundary.name]) and report.dry_run is False
    assert not old.exists() and not boundary.exists() and young.exists() and (young / "memo.md").exists()


def test_a_run_folder_is_removed_whole_never_in_part(tmp_path):
    old = make_run(tmp_path, 40)
    (old / "report.pdf").write_bytes(b"%PDF-")
    prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert not old.exists()


def test_prune_touches_nothing_in_the_output_folder_that_is_not_a_run_folder(tmp_path):
    (tmp_path / "out" / ".pending").mkdir(parents=True)
    marker = tmp_path / "out" / ".pending" / f"{run_id(90)}.json"
    marker.write_text("{}", encoding="utf-8")
    stray = tmp_path / "out" / "notes.txt"
    stray.write_text("x", encoding="utf-8")
    odd = tmp_path / "out" / "20250101T000000.000000Z-ABCDEF12"  # not the fixed form
    odd.mkdir()
    link_target = tmp_path / "elsewhere"
    link_target.mkdir()
    (link_target / "keep.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "out" / run_id(90, "11111111")
    link.symlink_to(link_target, target_is_directory=True)
    file_named_like_a_run = tmp_path / "out" / run_id(90, "22222222")
    file_named_like_a_run.write_text("a file", encoding="utf-8")
    not_staging = [
        tmp_path / "out" / f".{run_id(90)}.partial",  # no random part
        tmp_path / "out" / f"{run_id(90)}.abc.partial",  # no leading dot
        tmp_path / "out" / f".{run_id(90)}.ab-c.partial",  # a character the writer never uses
        tmp_path / "out" / f".{run_id(90)}.abc.partial.bak",
        tmp_path / "out" / ".20250101T000000.000000Z-ABCDEF12.abc.partial",
        tmp_path / "out" / ".not-a-run.abc.partial",
        tmp_path / "out" / f".{run_id(90)}..partial",  # an empty random part
        tmp_path / "out" / f".{run_id(90, 'abcdef123')}.abc.partial",  # nine hex characters in the run ID
    ]
    for path in not_staging:
        path.mkdir()
    staging_file = tmp_path / "out" / f".{run_id(90, '33333333')}.abc.partial"
    staging_file.write_text("a file named like a staging folder", encoding="utf-8")
    staging_link = tmp_path / "out" / f".{run_id(90, '44444444')}.abc.partial"
    staging_link.symlink_to(link_target, target_is_directory=True)
    report = prune(settings(tmp_path), 1, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")  # everything above exists first, and all of it is 90 days old
    assert report.runs == [] and report.staging == []
    for path in (marker, *not_staging, stray, odd, file_named_like_a_run, staging_file):
        assert path.exists(), path
    assert link.is_symlink() and staging_link.is_symlink() and (link_target / "keep.txt").exists()


def staging_folder(tmp_path, days_old, suffix="abcdef12", random="x9Y_z", *, mtime_days=None):
    folder = tmp_path / "out" / f".{run_id(days_old, suffix)}.{random}.partial"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    if mtime_days is not None:
        moved = (NOW - timedelta(days=mtime_days)).timestamp()
        os.utime(folder, (moved, moved))
    return folder


def test_prune_removes_the_staging_folders_a_crash_left_aged_from_the_run_id_in_the_name_like_a_run_folder(tmp_path):
    old, boundary, young = staging_folder(tmp_path, 40, "00000001"), staging_folder(tmp_path, 30, "00000002"), staging_folder(tmp_path, 29.9, "00000003")
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert report.staging == sorted([old.name, boundary.name]) and report.runs == []
    assert not old.exists() and not boundary.exists() and young.exists() and (young / "manifest.json").exists()


def test_a_staging_folder_is_aged_by_its_name_and_not_by_when_it_was_touched(tmp_path):
    old_name_new_mtime = staging_folder(tmp_path, 90, "00000001", mtime_days=0)
    new_name_old_mtime = staging_folder(tmp_path, 1, "00000002", mtime_days=90)
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert report.staging == [old_name_new_mtime.name] and not old_name_new_mtime.exists() and new_name_old_mtime.exists()


def test_run_folders_and_staging_folders_are_counted_apart_and_a_dry_run_removes_neither(tmp_path):
    run, staging = make_run(tmp_path, 40, "00000001"), staging_folder(tmp_path, 40, "00000002")
    dry = prune(settings(tmp_path), 30, dry_run=True, now=lambda: NOW, temp_root=tmp_path / "t")
    assert (dry.runs, dry.staging) == ([run.name], [staging.name]) and run.exists() and staging.exists()
    real = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert (real.runs, real.staging) == (dry.runs, dry.staging) and not run.exists() and not staging.exists()


def test_the_name_prune_looks_for_is_the_name_the_writer_really_gives_its_staging_folder(tmp_path, monkeypatch):
    """A crash is simulated by a write that fails and a clean-up that does not happen; the folder it leaves must be the one prune recognises."""
    import shutil

    from credit_intel.export import writer
    from credit_intel.ingestion.errors import IngestionError

    old_id = run_id(40)
    monkeypatch.setattr(writer.shutil, "rmtree", lambda *a, **k: None)
    monkeypatch.setattr(writer, "_write_file", lambda *a, **k: (_ for _ in ()).throw(OSError("the machine stopped")))
    with pytest.raises(IngestionError):
        writer.write_run(tmp_path / "out", old_id, {"manifest.json": "{}"})
    monkeypatch.undo()
    left = [p.name for p in (tmp_path / "out").iterdir()]
    assert len(left) == 1 and left[0].startswith(f".{old_id}.") and left[0].endswith(".partial")
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert report.staging == left and not (tmp_path / "out" / left[0]).exists()
    shutil.rmtree(tmp_path / "out", ignore_errors=True)


def test_prune_removes_cache_entries_by_modification_time_and_only_files_named_like_entries(tmp_path):
    old, young = make_entry(tmp_path, f"{OLD_KEY}.json", 40), make_entry(tmp_path, f"{KEY}.json", 5)
    other = [make_entry(tmp_path, "notes.json", 99), make_entry(tmp_path, f"{OLD_KEY}.txt", 99), make_entry(tmp_path, f"{'E' * 64}.json", 99), make_entry(tmp_path, f".{OLD_KEY}.tmp", 99)]
    (tmp_path / "cache" / ("c" * 64 + ".json")).mkdir()  # a folder with an entry's name
    link = tmp_path / "cache" / ("d" * 64 + ".json")
    link.symlink_to(young)
    old_target = make_entry(tmp_path, "notes-old.txt", 400)
    old_link = tmp_path / "cache" / ("f" * 64 + ".json")
    old_link.symlink_to(old_target)  # a link that would look old if it were followed
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert report.cache_entries == 1 and not old.exists() and young.exists() and all(p.exists() for p in other) and link.is_symlink() and old_link.is_symlink() and old_target.exists()
    assert (tmp_path / "cache" / ("c" * 64 + ".json")).is_dir()


def test_prune_removes_old_upload_directories_by_age_whatever_process_made_them_and_only_those(tmp_path):
    root = tmp_path / "t"
    old = make_dir(root, f"{UPLOAD_PREFIX}{ALIVE}-old", age_days=40)
    young = make_dir(root, f"{UPLOAD_PREFIX}{ALIVE}-young", age_days=1)
    unrelated = make_dir(root, "other-old-folder", age_days=400)
    report = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=root)
    assert report.uploads == 1 and not old.exists() and young.exists() and unrelated.exists()


def test_a_dry_run_reports_the_same_and_removes_nothing(tmp_path):
    run = make_run(tmp_path, 40)
    entry = make_entry(tmp_path, f"{OLD_KEY}.json", 40)
    upload = make_dir(tmp_path / "t", f"{UPLOAD_PREFIX}{DEAD}-x", age_days=40)
    dry = prune(settings(tmp_path), 30, dry_run=True, now=lambda: NOW, temp_root=tmp_path / "t")
    assert run.exists() and entry.exists() and upload.exists()
    real = prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert (dry.runs, dry.cache_entries, dry.uploads) == (real.runs, real.cache_entries, real.uploads) == ([run.name], 1, 1)
    assert dry.dry_run is True and real.dry_run is False and not run.exists() and not entry.exists() and not upload.exists()


def test_missing_folders_are_not_an_error(tmp_path):
    report = prune(settings(tmp_path), 7, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "none")
    assert (report.runs, report.cache_entries, report.uploads) == ([], 0, 0)


@pytest.mark.parametrize("days", [0, -1, 1.5, "30", None, True])
def test_the_number_of_days_must_be_a_whole_number_of_at_least_one(tmp_path, days):
    run = make_run(tmp_path, 400)
    with pytest.raises(ValueError):
        prune(settings(tmp_path), days, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert run.exists()  # nothing was removed on the way to the error


def test_a_removed_run_does_not_take_a_younger_one_with_it(tmp_path):
    keep = [make_run(tmp_path, d, f"0000000{d % 10}") for d in (1, 2, 29)]
    make_run(tmp_path, 31, "99999999")
    prune(settings(tmp_path), 30, dry_run=False, now=lambda: NOW, temp_root=tmp_path / "t")
    assert all(p.exists() and (p / "manifest.json").exists() for p in keep)


# --- what it says -----------------------------------------------------------------------------------------------------------------------------


def test_the_lines_name_run_ids_and_counts_and_warn_about_what_removal_costs():
    lines = render(PruneReport(30, False, runs=["20260101T000000.000000Z-abcdef12"], staging=[".20260101T000000.000000Z-abcdef12.xY_z.partial"], cache_entries=3, uploads=2))
    assert lines[0] == "removed run 20260101T000000.000000Z-abcdef12" and lines[1] == "removed staging folder .20260101T000000.000000Z-abcdef12.xY_z.partial"
    assert "removed 1 run folders, 1 staging folders, 3 cache entries and 2 upload directories older than 30 days" in lines[2]
    assert any("without its cache entries a run cannot be reproduced" in l for l in lines) and any("can no longer be checked against its stored files" in l for l in lines)
    assert not any("dry run" in l for l in lines)


def test_a_dry_run_says_would_remove_and_that_nothing_was():
    lines = render(PruneReport(7, True, runs=["20260101T000000.000000Z-abcdef12"]))
    assert lines[0].startswith("would remove run ") and "would remove 1 run folders, 0 staging folders, 0 cache entries" in lines[1] and lines[-1] == "dry run: nothing was removed"
    assert not any("cache entries a run" in l for l in lines)  # no cache entry, no note about the cache


def test_an_empty_report_has_one_summary_line_only():
    assert render(PruneReport(7, False)) == ["removed 0 run folders, 0 staging folders, 0 cache entries and 0 upload directories older than 7 days"]
