"""Reproducibility: the same input, configuration, code and cached replies give the same outputs (PRD FR-012.2, NFR-06, Definition of Done item 5;
Phase 5 step 5m; B-273).

The whole command is run, not its parts. The run folders are compared file by file.
"""

import io
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.llm.provider import FakeProvider

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
FILES = ("memo.md", "results.json", "manifest.json")
STAMP = re.compile(r"\d{8}T\d{6}\.\d{6}Z")


def clock(start=START):
    ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(ticks)


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    return path


def run(pdf, config, out_dir, *extra, replies=None, start=START):
    out, err = io.StringIO(), io.StringIO()
    code = main([str(pdf), "--config", str(config), "--output-dir", str(out_dir), *extra],
                provider_factory=lambda s, e: FakeProvider(script=replies or []), clock=clock(start), stdout=out, stderr=err, env={})  # fmt: skip
    assert code == 0, err.getvalue()
    return Path(out.getvalue().strip())


def read(folder):
    return {name: (folder / name).read_bytes() for name in FILES}


def test_a_cold_run_and_a_cached_run_give_the_same_results_and_memo_and_a_manifest_that_differs_only_in_cache_and_tokens(pdf, config, tmp_path):
    cold = read(run(pdf, config, tmp_path / "a", replies=[fx.good_response(pdf)]))
    warm = read(run(pdf, config, tmp_path / "b"))  # the response cache serves it: no reply is scripted

    assert cold["results.json"] == warm["results.json"] and cold["memo.md"] == warm["memo.md"]
    a, b = (json.loads(x["manifest.json"]) for x in (cold, warm))
    assert a["cache"] == {"hits": 0, "misses": 1} and b["cache"] == {"hits": 1, "misses": 0}
    differing = {key for key in a if a[key] != b[key]}
    assert differing == {"cache", "tokens", "stage_events"}
    assert [(e["state"], e["at"]) for e in a["stage_events"]] == [(e["state"], e["at"]) for e in b["stage_events"]]
    assert {e["state"] for e, f in zip(a["stage_events"], b["stage_events"]) if e["counts"] != f["counts"]} == {"fields_extracted"}


def test_runs_at_different_times_differ_only_in_the_run_id_and_times_and_never_in_results(pdf, config, tmp_path):
    first = run(pdf, config, tmp_path / "a", replies=[fx.good_response(pdf)])
    second = run(pdf, config, tmp_path / "b", start=START + timedelta(days=40, microseconds=17))
    one, two = read(first), read(second)

    assert first.name != second.name and first.name[-8:] == second.name[-8:]
    assert one["results.json"] == two["results.json"]
    assert STAMP.sub("T", one["memo.md"].decode()) == STAMP.sub("T", two["memo.md"].decode())
    assert STAMP.sub("T", one["manifest.json"].decode()).replace("cache", "c") != ""  # the manifest is where the times live
    assert STAMP.search(one["manifest.json"].decode()) and not STAMP.search(one["results.json"].decode())


def test_results_json_holds_no_time_run_id_path_or_machine_detail(pdf, config, tmp_path):
    text = read(run(pdf, config, tmp_path / "out", replies=[fx.good_response(pdf)]))["results.json"].decode()

    assert not STAMP.search(text) and str(tmp_path) not in text and "T10:15" not in text
    for word in ("hostname", "user", "pid", "git", "version"):
        assert f'"{word}' not in text.lower()


def test_neither_the_output_path_nor_the_working_directory_reaches_any_file(pdf, config, tmp_path):
    folder = run(pdf, config, tmp_path / "deep" / "er" / "out", replies=[fx.good_response(pdf)])

    for name, data in read(folder).items():
        assert str(tmp_path).encode() not in data and b"deep" not in data, name


def test_the_order_of_the_keys_in_the_profile_file_changes_nothing(pdf, config, tmp_path):
    forward, backward = tmp_path / "f.json", tmp_path / "b.json"
    forward.write_text(json.dumps({"borrower_name": "Zebra", "industry": "Steel", "notes": "n"}), encoding="utf-8")
    backward.write_text(json.dumps({"notes": "n", "industry": "Steel", "borrower_name": "Zebra"}), encoding="utf-8")
    one = read(run(pdf, config, tmp_path / "a", "--profile", str(forward), replies=[fx.good_response(pdf)]))
    two = read(run(pdf, config, tmp_path / "b", "--profile", str(backward)))

    assert one["results.json"] == two["results.json"] and one["memo.md"] == two["memo.md"]


CHILD = """
import io, sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from credit_intel.cli import main
from credit_intel.llm.provider import FakeProvider

pdf, reply, out_dir, config = sys.argv[1:5]
start = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
ticks = iter(start + timedelta(milliseconds=7 * n) for n in range(10000))
out, err = io.StringIO(), io.StringIO()
code = main([pdf, "--config", config, "--output-dir", out_dir],
            provider_factory=lambda s, e: FakeProvider(script=[Path(reply).read_text(encoding="utf-8")]),
            clock=lambda: next(ticks), stdout=out, stderr=err,
            env={"CREDIT_INTEL_PARSE_TIMEOUT_SECONDS": "60", "CREDIT_INTEL_PARSE_MEMORY_MB": "2048"})  # the real worker process, in a fresh process
sys.stdout.write(out.getvalue())
sys.exit(code)
"""


def fresh_process(tmp_path, name, pdf, config, seed, **env):
    work = tmp_path / name
    work.mkdir()
    reply = work / "reply.json"
    reply.write_text(fx.good_response(pdf), encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", CHILD, str(pdf), str(reply), str(work / "out"), str(config)], cwd=work, capture_output=True,
                          env={**os.environ, "PYTHONHASHSEED": str(seed), **env})  # fmt: skip
    assert done.returncode == 0, done.stderr.decode()
    return work / "out" / Path(done.stdout.decode().strip()).name


def test_whole_run_folders_from_fresh_processes_are_byte_identical_whatever_the_hash_seed_time_zone_or_locale(pdf, config, tmp_path):
    one = fresh_process(tmp_path, "one", pdf, config, 1, TZ="UTC", LC_ALL="C")
    two = fresh_process(tmp_path, "two", pdf, config, 424242, TZ="Asia/Kolkata", LC_ALL="C.UTF-8")
    three = fresh_process(tmp_path, "three", pdf, config, "random", TZ="America/Los_Angeles", LANG="en_US.UTF-8")

    assert one.name == two.name == three.name
    assert read(one) == read(two) == read(three)


def test_two_runs_in_one_process_leave_independent_folders_with_the_same_results(pdf, config, tmp_path):
    first = read(run(pdf, config, tmp_path / "a", replies=[fx.good_response(pdf)]))
    second = read(run(pdf, config, tmp_path / "a", start=START + timedelta(seconds=1)))

    assert first["results.json"] == second["results.json"]
    assert len(list((tmp_path / "a").iterdir())) == 2


def test_a_changed_input_changes_the_results_so_the_comparison_above_can_fail(pdf, config, tmp_path):
    other = fx.balance_sheet_pdf(tmp_path / "other.pdf", rows=[("Total current assets", "14", "9,999.00", "1,356.75"), *fx.ROWS[2:]])
    one = read(run(pdf, config, tmp_path / "a", replies=[fx.good_response(pdf)]))
    two = read(run(other, config, tmp_path / "b", replies=[fx.good_response(other)]))

    assert one["results.json"] != two["results.json"] and one["memo.md"] != two["memo.md"]
