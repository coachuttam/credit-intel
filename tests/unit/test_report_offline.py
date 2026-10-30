"""The offline report command (PRD FR-015 criterion 11, v0.4.56; step 5 of its build; B-330): ``python -m credit_intel.report <run-folder> --output FILE``."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402

from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.report import ReportOutcome, build, make_report  # noqa: E402
from credit_intel.report import __main__ as offline  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    """A run folder: memo.md and results.json of the golden run, and a manifest so that it looks like one."""
    path = tmp_path / "runs" / "20261024T101530.123456Z-0dd49919"
    path.mkdir(parents=True)
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    (path / "memo.md").write_text(render_memo(data, RUN_ID, WHEN), encoding="utf-8")
    (path / "results.json").write_bytes(GOLDEN.read_bytes())
    (path / "manifest.json").write_text("{}\n", encoding="utf-8")
    return path


def digest(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


def run(folder, output, capsys):
    code = offline.main([str(folder), "--output", str(output)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_it_writes_the_report_of_the_folder_to_the_named_file_and_prints_its_path(folder, tmp_path, capsys):
    before = digest(folder)
    output = tmp_path / "out" / "report.pdf"
    output.parent.mkdir()
    code, out, err = run(folder, output, capsys)
    expected = make_report((folder / "memo.md").read_text(encoding="utf-8"), json.loads((folder / "results.json").read_text(encoding="utf-8")))

    assert code == 0 and out.strip() == str(output) and err == ""
    assert expected.status == "written" and output.read_bytes() == expected.pdf  # with the charts, as a run builds it
    assert digest(folder) == before  # the run folder is not touched


def test_it_refuses_a_file_that_exists_and_leaves_it_as_it_was(folder, tmp_path, capsys):
    output = tmp_path / "taken.pdf"
    output.write_bytes(b"keep me")
    code, out, err = run(folder, output, capsys)
    assert code == 1 and out == "" and "already exists" in err and output.read_bytes() == b"keep me"


def test_it_refuses_a_link_that_exists(folder, tmp_path, capsys):
    target = tmp_path / "target.pdf"
    target.write_bytes(b"x")
    link = tmp_path / "link.pdf"
    os.symlink(target, link)
    code, _, err = run(folder, link, capsys)
    assert code == 1 and "already exists" in err and target.read_bytes() == b"x"


def test_it_never_writes_inside_the_run_folder(folder, tmp_path, capsys):
    before = digest(folder)
    code, out, err = run(folder, folder / "report.pdf", capsys)
    assert code == 1 and "inside a run folder" in err and digest(folder) == before and not (folder / "report.pdf").exists()


def test_it_never_writes_in_a_sub_folder_of_the_run_folder_either(folder, tmp_path, capsys):
    before = digest(folder)
    sub = folder / "extra"
    sub.mkdir()
    code, _, err = run(folder, sub / "report.pdf", capsys)
    assert code == 1 and "inside a run folder" in err and list(sub.iterdir()) == [] and digest(folder) == before


def test_it_never_writes_beside_the_files_of_any_run_folder(folder, tmp_path, capsys):
    other = tmp_path / "runs" / "20261025T101530.123456Z-aaaaaaaa"
    other.mkdir()
    (other / "manifest.json").write_text("{}\n", encoding="utf-8")
    code, _, err = run(folder, other / "report.pdf", capsys)
    assert code == 1 and "inside a run folder" in err and list(other.iterdir()) == [other / "manifest.json"]


@pytest.mark.parametrize("damage", ["no_memo", "no_results", "bad_json", "bad_utf8"])
def test_it_refuses_a_folder_it_cannot_read(folder, tmp_path, capsys, damage):
    if damage == "no_memo":
        (folder / "memo.md").unlink()
    elif damage == "no_results":
        (folder / "results.json").unlink()
    elif damage == "bad_json":
        (folder / "results.json").write_text("{not json", encoding="utf-8")
    else:
        (folder / "memo.md").write_bytes(b"\xff\xfe\x00")
    output = tmp_path / "r.pdf"
    code, _, err = run(folder, output, capsys)
    assert code == 1 and "cannot be read" in err and not output.exists()


def test_a_folder_that_does_not_exist_is_refused(tmp_path, capsys):
    code, _, err = run(tmp_path / "nowhere", tmp_path / "r.pdf", capsys)
    assert code == 1 and "cannot be read" in err


def test_a_memo_that_is_not_the_memo_of_its_results_is_not_presented(folder, tmp_path, capsys):
    memo = (folder / "memo.md").read_text(encoding="utf-8")
    (folder / "memo.md").write_text(memo.replace("1.65", "1.56", 1), encoding="utf-8")
    output = tmp_path / "r.pdf"
    code, _, err = run(folder, output, capsys)
    assert code == 1 and "does not match" in err and not output.exists()


def test_a_report_that_cannot_be_built_is_exit_1_with_the_reason_and_no_file(folder, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(offline, "make_report", lambda memo, results=None, **kw: ReportOutcome("failed", reason="timeout"))
    output = tmp_path / "r.pdf"
    code, out, err = run(folder, output, capsys)
    assert code == 1 and out == "" and "not written (timeout)" in err and not output.exists()


def test_a_file_that_appears_after_the_check_is_still_not_overwritten(folder, tmp_path, capsys, monkeypatch):
    output = tmp_path / "late.pdf"
    output.write_bytes(b"late arrival")
    monkeypatch.setattr(Path, "exists", lambda self: False)  # the early checks see nothing; only the exclusive open can notice
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    code, _, err = run(folder, output, capsys)
    assert code == 1 and "could not be written" in err and output.read_bytes() == b"late arrival"


def test_the_output_option_is_required(folder, capsys):
    with pytest.raises(SystemExit) as stop:
        offline.main([str(folder)])
    assert stop.value.code == 2


def test_it_runs_as_a_command_in_a_fresh_process_and_loads_no_model_code(folder, tmp_path):
    output = tmp_path / "cli.pdf"
    done = subprocess.run([sys.executable, "-I", "-m", "credit_intel.report", str(folder), "--output", str(output)], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.strip() == str(output) and output.read_bytes().startswith(b"%PDF-")
    probe = "import sys, credit_intel.report.__main__; print(sorted(m for m in sys.modules if m.split('.')[0] in ('openai', 'typesafe_sdk') or m.startswith('credit_intel.llm')))"
    loaded = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True).stdout.strip()
    assert loaded == "[]"


def test_the_offline_report_equals_the_one_a_run_writes_for_the_same_memo(folder, tmp_path, capsys):
    output = tmp_path / "o.pdf"
    assert run(folder, output, capsys)[0] == 0
    built = build.make_report((folder / "memo.md").read_text(encoding="utf-8"), json.loads((folder / "results.json").read_text(encoding="utf-8")))
    assert built.pdf == output.read_bytes()
