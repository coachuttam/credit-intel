"""Writing a run folder: atomic, never overwriting, nothing complete-looking after a failure (PRD FR-010.1, FR-010.3, FR-010.4; Phase 5 step 5j; B-267)."""

import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

from credit_intel.export import writer
from credit_intel.export.writer import RUN_ID, STAGING_SUFFIX, write_run
from credit_intel.ingestion.errors import ErrorCode, IngestionError, exit_code

RUN = "20261024T101530.123456Z-0dd49919"
PDF = b"%PDF-1.4\n\xff\xfe\x00 bytes that are not UTF-8 \x80\n%%EOF\n"  # report.pdf (FR-015) is bytes: written exactly as given
FILES = {"memo.md": "# Memo — draft\n\nline two\n", "results.json": '{"a": "é"}\n', "manifest.json": "{}\n", "report.pdf": PDF}


def listing(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir())


def run_folders(output: Path) -> list[str]:
    return [n for n in listing(output) if RUN_ID.fullmatch(n)]


# --- success -----------------------------------------------------------------------------------------------------------------------------------


def test_the_files_are_written_as_given_in_the_run_folder_and_nothing_else_is_left(tmp_path):
    path = write_run(tmp_path / "runs", RUN, FILES)

    assert path == tmp_path / "runs" / RUN and listing(path) == ["manifest.json", "memo.md", "report.pdf", "results.json"]
    assert listing(tmp_path / "runs") == [RUN]
    for name, content in FILES.items():
        assert (path / name).read_bytes() == (content if isinstance(content, bytes) else content.encode("utf-8"))


def test_bytes_are_written_exactly_and_text_is_still_encoded_as_utf_8(tmp_path):
    path = write_run(tmp_path, RUN, {"report.pdf": PDF, "memo.md": "é"})
    assert (path / "report.pdf").read_bytes() == PDF and (path / "memo.md").read_bytes() == "é".encode("utf-8")


def test_a_run_may_have_no_report_and_is_complete_without_it(tmp_path):
    path = write_run(tmp_path, RUN, {k: v for k, v in FILES.items() if k != "report.pdf"})
    assert listing(path) == ["manifest.json", "memo.md", "results.json"]


def test_text_is_utf_8_without_a_byte_order_mark_and_newlines_are_not_changed(tmp_path):
    path = write_run(tmp_path, RUN, {"memo.md": "a\nb\r\n—\n"})

    assert (path / "memo.md").read_bytes() == b"a\nb\r\n\xe2\x80\x94\n"


def test_missing_parent_directories_are_created(tmp_path):
    path = write_run(tmp_path / "a" / "b" / "runs", RUN, FILES)

    assert path.is_dir()


def test_two_different_runs_sit_side_by_side(tmp_path):
    write_run(tmp_path, RUN, FILES)
    write_run(tmp_path, "20261024T101530.123457Z-0dd49919", FILES)

    assert len(run_folders(tmp_path)) == 2


# --- never overwriting -------------------------------------------------------------------------------------------------------------------------


def test_an_existing_run_folder_is_refused_and_left_exactly_as_it_was(tmp_path):
    write_run(tmp_path, RUN, FILES)
    before = {n: (tmp_path / RUN / n).read_bytes() for n in FILES}

    with pytest.raises(IngestionError) as caught:
        write_run(tmp_path, RUN, {"memo.md": "other", "results.json": "other", "manifest.json": "other"})

    assert caught.value.code is ErrorCode.EXPORT_FAILED and exit_code(caught.value) == 7
    assert {n: (tmp_path / RUN / n).read_bytes() for n in FILES} == before
    assert listing(tmp_path) == [RUN]  # no staging folder was made


def test_an_existing_file_or_link_with_the_run_name_is_refused(tmp_path):
    (tmp_path / RUN).write_text("x", encoding="utf-8")
    with pytest.raises(IngestionError):
        write_run(tmp_path, RUN, FILES)
    (tmp_path / RUN).unlink()
    (tmp_path / RUN).symlink_to(tmp_path / "nowhere")
    with pytest.raises(IngestionError):
        write_run(tmp_path, RUN, FILES)
    assert listing(tmp_path) == [RUN]


def test_a_folder_that_appears_between_the_check_and_the_rename_is_not_overwritten(tmp_path, monkeypatch):
    real = os.rename

    def rename_after_a_rival(source, target):
        Path(target).mkdir()
        (Path(target) / "rival.txt").write_text("theirs", encoding="utf-8")
        real(source, target)

    monkeypatch.setattr(writer.os, "rename", rename_after_a_rival)

    with pytest.raises(IngestionError) as caught:
        write_run(tmp_path, RUN, FILES)

    assert caught.value.code is ErrorCode.EXPORT_FAILED and isinstance(caught.value.__cause__, OSError)
    assert listing(tmp_path / RUN) == ["rival.txt"] and listing(tmp_path) == [RUN]


# --- bad requests and messages -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("run_id", ["", "run", "20261024T101530Z-0dd49919", "20261024T101530.123456Z-0DD49919", "../20261024T101530.123456Z-0dd49919", RUN + "x"])
def test_a_run_id_not_of_the_documented_form_is_refused_before_anything_is_written(tmp_path, run_id):
    with pytest.raises(ValueError):
        write_run(tmp_path / "out", run_id, FILES)

    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", ["", "../x", "a/b", ".hidden", "a\\b", "x\n", "..", "sp ace"])
def test_a_file_name_that_is_not_plain_is_refused(tmp_path, name):
    with pytest.raises(ValueError):
        write_run(tmp_path / "out", RUN, {name: "x"})
    with pytest.raises(ValueError):
        write_run(tmp_path / "out", RUN, {})

    assert not (tmp_path / "out").exists()


def test_a_failure_message_has_no_path_and_the_cause_is_kept(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(IngestionError) as caught:
        write_run(blocker / "runs", RUN, FILES)

    assert str(tmp_path) not in str(caught.value) and RUN not in str(caught.value)
    assert isinstance(caught.value.__cause__, OSError)


# --- fault injection: a failure at any step leaves nothing that looks complete --------------------------------------------------------------------


def counting(monkeypatch, fail_at):
    """Make the ``fail_at``-th call among fsync, replace, rename and open raise an OS error; return the call counter."""
    calls = {"n": 0}

    def wrap(name):
        real = getattr(os, name)

        def inner(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == fail_at:
                raise OSError(errno.ENOSPC, "injected")
            return real(*args, **kwargs)

        monkeypatch.setattr(writer.os, name, inner)

    for name in ("fsync", "replace", "rename", "open"):
        wrap(name)
    return calls


def test_a_failure_at_every_step_leaves_no_run_folder_and_no_staging_folder(tmp_path):
    # Find how many steps a clean write takes.
    probe = pytest.MonkeyPatch()
    calls = counting(probe, fail_at=10**9)
    write_run(tmp_path / "clean", RUN, FILES)
    total = calls["n"]
    probe.undo()
    assert total >= 8

    raised = []
    for step in range(1, total + 1):
        output = tmp_path / f"fail-{step}"
        with pytest.MonkeyPatch.context() as patch:
            counting(patch, fail_at=step)
            try:
                write_run(output, RUN, FILES)
            except IngestionError as error:
                assert error.code is ErrorCode.EXPORT_FAILED and isinstance(error.__cause__, OSError), step
                assert listing(output) == [], step  # a reported failure leaves nothing at all
                raised.append(step)
            else:  # only the best-effort flush of the parent directory, after the run was published, may fail silently
                assert listing(output) == [RUN] and listing(output / RUN) == sorted(FILES), step
    assert raised == list(range(1, total - 1)) and total - 1 not in raised and total not in raised


def test_a_failure_while_writing_a_later_file_leaves_no_earlier_file_behind(tmp_path, monkeypatch):
    real = writer._write_file
    seen = []

    def failing(directory, name, text):
        seen.append(name)
        if len(seen) == 2:
            raise OSError(errno.ENOSPC, "disk full")
        real(directory, name, text)

    monkeypatch.setattr(writer, "_write_file", failing)

    with pytest.raises(IngestionError):
        write_run(tmp_path, RUN, FILES)

    assert listing(tmp_path) == [] and seen == ["memo.md", "results.json"]


def test_an_interrupt_stops_the_write_cleans_up_and_is_not_turned_into_an_error(tmp_path, monkeypatch):
    def interrupted(directory, name, text):
        raise KeyboardInterrupt

    monkeypatch.setattr(writer, "_write_file", interrupted)

    with pytest.raises(KeyboardInterrupt):
        write_run(tmp_path, RUN, FILES)

    assert listing(tmp_path) == []


def test_a_cleanup_that_also_fails_still_reports_the_export_failure(tmp_path, monkeypatch):
    def broken_write(directory, name, text):
        raise OSError(errno.EIO, "io")

    monkeypatch.setattr(writer, "_write_file", broken_write)
    monkeypatch.setattr(writer.shutil, "rmtree", lambda path: (_ for _ in ()).throw(OSError("cannot remove")))

    with pytest.raises(IngestionError) as caught:
        write_run(tmp_path, RUN, FILES)

    assert caught.value.code is ErrorCode.EXPORT_FAILED
    assert run_folders(tmp_path) == [] and all(n.endswith(STAGING_SUFFIX) for n in listing(tmp_path))


# --- a crash (the process dies, so nothing is cleaned up) -------------------------------------------------------------------------------------------


CRASH = """
import os, sys
from pathlib import Path
from credit_intel.export import writer

output, run, crash_at = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
calls = {"n": 0}
for name in ("fsync", "replace", "rename", "open"):
    real = getattr(os, name)
    def make(real):
        def inner(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == crash_at:
                os._exit(9)
            return real(*args, **kwargs)
        return inner
    setattr(writer.os, name, make(real))
writer.write_run(output, run, {"memo.md": "m\\n", "results.json": "r\\n", "manifest.json": "x\\n"})
"""


def test_a_process_that_dies_at_any_step_never_leaves_a_run_folder_that_is_incomplete(tmp_path):
    outcomes = {}
    for step in range(1, 40):
        output = tmp_path / f"crash-{step}"
        done = subprocess.run([sys.executable, "-c", CRASH, str(output), RUN, str(step)], capture_output=True)
        folders = run_folders(output) if output.exists() else []
        outcomes[step] = (done.returncode, folders)
        if done.returncode == 0:
            assert listing(output / RUN) == ["manifest.json", "memo.md", "results.json"]
            break
        assert done.returncode == 9
        for folder in folders:  # a run folder exists only if the final rename happened, and then it is whole
            assert listing(output / folder) == ["manifest.json", "memo.md", "results.json"]
        for name in listing(output) if output.exists() else []:
            assert RUN_ID.fullmatch(name) or (name.startswith(".") and name.endswith(STAGING_SUFFIX)), name
    assert any(code == 9 and not folders for code, folders in outcomes.values()) and any(code == 0 for code, _ in outcomes.values())


def test_an_existing_empty_run_folder_is_refused_too(tmp_path):
    (tmp_path / RUN).mkdir()  # a rename onto an empty directory would otherwise succeed

    with pytest.raises(IngestionError):
        write_run(tmp_path, RUN, FILES)

    assert listing(tmp_path) == [RUN] and listing(tmp_path / RUN) == []


def test_an_error_that_is_not_an_operating_system_error_is_not_dressed_up_as_an_export_failure(tmp_path, monkeypatch):
    def bug(directory, name, text):
        raise RuntimeError("a bug")

    monkeypatch.setattr(writer, "_write_file", bug)

    with pytest.raises(RuntimeError):
        write_run(tmp_path, RUN, FILES)

    assert listing(tmp_path) == []  # and the staging folder is still removed
