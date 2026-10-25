"""The assertion in results.json, the manifest and the memo, from real runs through the command line (PRD FR-010.1, FR-012.1, K.0; OD-10 option 3; step A3; B-282)."""

import io
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unit"))  # the memo checker lives with the unit tests

import pipeline_fixture as fx  # noqa: E402
from credit_intel.cli import main  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from credit_intel.memo.render import render_memo  # noqa: E402
from memo_trace import problems  # noqa: E402

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
FILES = ("memo.md", "results.json", "manifest.json")


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")


@pytest.fixture
def titled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "titled.pdf")


def reply_for(pdf, untitled_page=True):
    text = fx.good_response(pdf)
    return text.replace("Consolidated Balance Sheet", "Balance Sheet") if untitled_page else text


def run(pdf, tmp_path, *argv, out_dir="runs", replies=None, start=START):
    config = tmp_path / "settings.toml"
    config.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), "--output-dir", str(tmp_path / out_dir), *argv],
                provider_factory=lambda s, e: FakeProvider(script=replies or []), clock=lambda: next(ticks), stdout=out, stderr=err, env={})  # fmt: skip
    return code, out.getvalue(), err.getvalue()


def folder_of(out):
    return Path(out.strip())


def read(folder):
    return {name: (folder / name).read_bytes() for name in FILES}


def test_results_and_manifest_record_the_assertion_with_the_pages_it_was_applied_to(untitled, tmp_path):
    code, out, err = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", replies=[reply_for(untitled)])
    folder = folder_of(out)
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    assert code == 0, err
    expected = {"applied_pages": [1], "basis": "consolidated", "pages": [1]}
    assert results["extraction"]["basis_assertion"] == expected and manifest["basis_assertion"] == expected


def test_without_the_flag_both_files_record_none(titled, tmp_path):
    code, out, _ = run(titled, tmp_path, replies=[fx.good_response(titled)])
    folder = folder_of(out)

    assert code == 0
    assert json.loads((folder / "results.json").read_text(encoding="utf-8"))["extraction"]["basis_assertion"] is None
    assert json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["basis_assertion"] is None


def test_an_assertion_that_was_not_needed_is_recorded_with_no_applied_pages(titled, tmp_path):
    code, out, _ = run(titled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", replies=[fx.good_response(titled)])
    folder = folder_of(out)
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))

    assert code == 0 and results["extraction"]["basis_assertion"] == {"applied_pages": [], "basis": "consolidated", "pages": [1]}
    assert "was not needed" in (folder / "memo.md").read_text(encoding="utf-8")


def test_the_memo_discloses_the_assertion_and_is_traceable_to_the_results(untitled, tmp_path):
    code, out, err = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", replies=[reply_for(untitled)])
    folder = folder_of(out)
    memo = (folder / "memo.md").read_text(encoding="utf-8")
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))

    assert code == 0, err
    assert "**Basis asserted by the analyst** for page 1 (consolidated); not established by the document. [ANALYST-PROVIDED]" in memo.split("## 1. ")[0]
    assert memo.count("These figures rest on a statement basis that was asserted by the analyst") == 2
    assert problems(memo, results) == []
    assert "| `current_assets.2025-03-31.consolidated` | 1,482.30 (INR crore) | extracted | [SOURCE: p.1] | basis asserted by the analyst |" in memo


def test_the_memo_made_from_the_written_results_is_the_memo_that_was_written(untitled, tmp_path):
    code, out, _ = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", replies=[reply_for(untitled)])
    folder = folder_of(out)
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    written = (folder / "memo.md").read_text(encoding="utf-8")
    generated = re.search(r"\*\*Generated:\*\* `([^`]+)`", written).group(1)  # the one time the memo holds that results.json does not
    assert render_memo(results, manifest["run_id"], generated) == written


def test_a_run_stopped_by_a_conflict_records_the_requested_basis_only(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")

    code, out, err = run(pdf, tmp_path, "--pages", "1-2", "--assert-basis", "consolidated")
    (folder,) = sorted((tmp_path / "runs").iterdir())
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    assert code == 4 and manifest["basis_assertion"] == {"basis": "consolidated", "pages": None, "applied_pages": None}
    assert manifest["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE"


def test_a_failure_without_the_flag_records_none(tmp_path):
    text = tmp_path / "note.pdf"
    text.write_text("not a pdf", encoding="utf-8")

    code, _, _ = run(text, tmp_path)
    (folder,) = sorted((tmp_path / "runs").iterdir())

    assert code == 3 and json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["basis_assertion"] is None


def test_two_runs_with_the_assertion_give_byte_identical_results_and_memo(untitled, tmp_path):
    _, first, _ = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", out_dir="a", replies=[reply_for(untitled)])
    _, second, _ = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", out_dir="b")  # served from the cache

    one, two = read(folder_of(first)), read(folder_of(second))
    assert one["results.json"] == two["results.json"] and one["memo.md"] == two["memo.md"]


def test_the_assertion_changes_the_results_and_the_memo_so_the_comparison_can_fail(untitled, tmp_path):
    _, asserted, _ = run(untitled, tmp_path, "--pages", "1", "--assert-basis", "consolidated", out_dir="a", replies=[reply_for(untitled)])
    titled = fx.balance_sheet_pdf(tmp_path / "titled.pdf")
    _, plain, _ = run(titled, tmp_path, "--pages", "1", out_dir="b", replies=[fx.good_response(titled)])

    assert read(folder_of(asserted))["results.json"] != read(folder_of(plain))["results.json"]
    assert "asserted by the analyst" not in (folder_of(plain) / "memo.md").read_text(encoding="utf-8")
