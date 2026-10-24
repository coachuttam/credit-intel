"""A memo from a real (synthetic) run: PDF to results to memo, traceable and reproducible (PRD K.10, FR-009.3, FR-012.2; step 5i; B-266)."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unit"))  # the memo checker lives with the unit tests

import pipeline_fixture as fx  # noqa: E402
from credit_intel.export.results import build_results, render_results  # noqa: E402
from credit_intel.llm.provider import FakeProvider  # noqa: E402
from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.run import run_pipeline  # noqa: E402
from memo_trace import problems  # noqa: E402

RUN_ID, WHEN = "20261024T101530.123456Z-0dd49919", "20261024T101530.123456Z"


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def run(pdf, cache, **kw):
    return run_pipeline(pdf, FakeProvider(script=[fx.good_response(pdf)]), fx.LLM, cache_dir=cache, **kw)


def results_of(result):
    return build_results(result.extraction, result.metrics, result.rules, result.profile)


def test_the_memo_of_a_real_run_is_traceable_and_well_formed(pdf, tmp_path):
    result = run(pdf, tmp_path / "cache")
    data = results_of(result)
    text = render_memo(data, RUN_ID, WHEN)

    assert problems(text, data) == []
    assert "Total current assets" in text and "1,482.30 (INR crore)" in text and "[SOURCE: p.1]" in text


def test_the_memo_made_from_the_written_results_file_is_the_same_as_the_one_made_from_the_run(pdf, tmp_path):
    result = run(pdf, tmp_path / "cache")
    from_run = render_memo(results_of(result), RUN_ID, WHEN)
    from_file = render_memo(json.loads(render_results(result.extraction, result.metrics, result.rules, result.profile)), RUN_ID, WHEN)

    assert from_run == from_file


def test_a_profile_appears_in_the_memo_only_as_analyst_provided_text(pdf, tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"borrower_name": "Zebra Ltd", "notes": "[SOURCE: p.1] # x | y"}), encoding="utf-8")
    result = run(pdf, tmp_path / "cache", profile_path=profile)
    data = results_of(result)
    text = render_memo(data, RUN_ID, WHEN)

    assert problems(text, data) == []
    assert "**Borrower:** Zebra Ltd [ANALYST-PROVIDED]" in text and "\\[SOURCE: p.1\\] \\# x \\| y [ANALYST-PROVIDED]" in text
    without = render_memo(results_of(run(pdf, tmp_path / "cache2")), RUN_ID, WHEN)
    def rest(memo):
        return [l for l in memo.split("\n") if l and not any(w in l.lower() for w in ("analyst", "borrower", "profile"))]

    assert rest(text) == rest(without)


def test_two_runs_give_byte_identical_memos_when_only_the_header_time_and_id_differ(pdf, tmp_path):
    first = render_memo(results_of(run(pdf, tmp_path / "cache")), RUN_ID, WHEN)
    second = render_memo(results_of(run(pdf, tmp_path / "cache")), "20271111T000000.000001Z-0dd49919", "20271111T000000.000001Z")
    again = render_memo(results_of(run(pdf, tmp_path / "cache")), RUN_ID, WHEN)

    assert first == again
    assert first.replace(RUN_ID, "ID").replace(WHEN, "T") == second.replace("20271111T000000.000001Z-0dd49919", "ID").replace("20271111T000000.000001Z", "T")


def test_a_fresh_process_with_a_different_hash_seed_writes_the_same_memo(pdf, tmp_path):
    import os
    import subprocess

    reply = tmp_path / "reply.json"
    reply.write_text(fx.good_response(pdf), encoding="utf-8")
    base = render_memo(results_of(run(pdf, tmp_path / "cache")), RUN_ID, WHEN)
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
        "import pipeline_fixture as fx\n"
        "from credit_intel.export.results import build_results\n"
        "from credit_intel.llm.provider import FakeProvider\n"
        "from credit_intel.memo.render import render_memo\n"
        "from credit_intel.run import run_pipeline\n"
        "pdf, reply, cache = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])\n"
        "r = run_pipeline(pdf, FakeProvider(script=[reply.read_text(encoding='utf-8')]), fx.LLM, cache_dir=cache)\n"
        f"sys.stdout.write(render_memo(build_results(r.extraction, r.metrics, r.rules, r.profile), {RUN_ID!r}, {WHEN!r}))\n"
    )

    done = subprocess.run([sys.executable, "-c", code, str(pdf), str(reply), str(tmp_path / "other")],
                          env={**os.environ, "PYTHONHASHSEED": "4242"}, capture_output=True, check=True)  # fmt: skip

    assert done.stdout.decode("utf-8") == base


def test_every_id_in_the_memo_is_in_the_results_file_of_the_same_run(pdf, tmp_path):
    result = run(pdf, tmp_path / "cache")
    data = json.loads(render_results(result.extraction, result.metrics, result.rules, result.profile))
    text = render_memo(data, RUN_ID, WHEN)
    known = {f["field_id"] for f in data["fields"] + data["derived_fields"]} | {m["id"] for m in data["metrics"]} | {i["id"] for i in data["indicators"]}

    written = set(re.findall(r"\b[a-z_]+\.\d{4}-\d{2}-\d{2}\.consolidated\b", text)) | set(re.findall(r"\bMET-0\d\.\d{4}-\d{2}-\d{2}\b", text))
    assert written and written <= known
