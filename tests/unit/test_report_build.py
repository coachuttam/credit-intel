"""Making the report so that it never fails the run (PRD FR-015 criteria 7 and 8, v0.4.56; step 3 of its build; B-328).

The real worker runs on real memos; stub workers (small Python scripts) stand in for a hung, crashing or lying one.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from memo_results import GOLDEN, RUN_ID, WHEN  # noqa: E402

from credit_intel.memo.render import render_memo  # noqa: E402
from credit_intel.memo.sections import DRAFT_STATEMENT  # noqa: E402
from credit_intel.report import REASONS, RENDER_TIME_LIMIT, ReportOutcome, build_pdf, build, make_report  # noqa: E402


@pytest.fixture(scope="module")
def memo():
    return render_memo(json.loads(GOLDEN.read_text(encoding="utf-8")), RUN_ID, WHEN)


def small(extra=""):
    return f"# Draft credit memo\n\n**Run ID:** `{RUN_ID}`  \n\n> **{DRAFT_STATEMENT}**\n\n## 1. Borrower overview\n\n{extra}\n\n## 9. Limitations and human-review requirements\n\n- A limit.\n"


def stub(tmp_path, body):
    path = tmp_path / "worker_stub.py"
    path.write_text("import os, sys, time\ndata = sys.stdin.buffer.read()\n" + body, encoding="utf-8")
    return (sys.executable, str(path))


PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


# --- the real worker ------------------------------------------------------------------------------------------------


def test_the_time_limit_is_a_constant_of_120_seconds():
    assert RENDER_TIME_LIMIT == 120.0 and build.RENDER_TIME_LIMIT == 120.0


def test_a_good_memo_gives_a_written_report_equal_to_the_direct_build(memo):
    outcome = make_report(memo)
    assert outcome.status == "written" and outcome.reason is None and outcome.pdf == build_pdf(memo)


def test_the_manifest_entry_of_a_written_report(memo):
    entry = make_report(memo).manifest_entry()
    import hashlib

    pdf = build_pdf(memo)
    assert entry["status"] == "written" and entry["file"] == "report.pdf" and entry["size"] == len(pdf)
    assert entry["sha256"] == hashlib.sha256(pdf).hexdigest()
    assert set(entry["packages"]) == {"reportlab", "markdown-it-py"} and all(entry["packages"].values())
    assert set(entry) == {"status", "file", "size", "sha256", "packages"}


def test_the_manifest_entries_of_a_failed_and_a_skipped_report():
    assert ReportOutcome("failed", reason="timeout").manifest_entry() == {"status": "failed", "reason": "timeout"}
    assert ReportOutcome.skipped().manifest_entry() == {"status": "skipped"} and ReportOutcome.skipped().pdf is None


def test_a_memo_with_a_character_the_font_lacks_fails_the_report_and_not_the_run(caplog):
    with caplog.at_level(logging.WARNING, logger="credit_intel.report"):
        outcome = make_report(small("Name: 漢字"))
    assert (outcome.status, outcome.reason, outcome.pdf) == ("failed", "glyph_missing", None)
    assert [r.getMessage() for r in caplog.records] == ["report not written (glyph_missing); memo.md is complete"]
    assert "漢" not in caplog.text


def test_a_memo_the_renderer_cannot_use_is_a_render_error():
    outcome = make_report("# no statement, no run id\n")
    assert (outcome.status, outcome.reason) == ("failed", "render_error")


def test_a_memo_that_cannot_be_encoded_is_a_render_error_and_does_not_raise():
    outcome = make_report("lone surrogate: \ud800")
    assert (outcome.status, outcome.reason) == ("failed", "render_error")


def test_a_failed_check_in_the_real_worker_is_check_failed_and_returns_no_bytes(memo):
    code = "import credit_intel.report.check as c\nc.problems = lambda pdf, memo: ['forced']\nfrom credit_intel.report import worker\nraise SystemExit(worker.main())"
    outcome = make_report(memo, command=(sys.executable, "-c", code))
    assert (outcome.status, outcome.reason, outcome.pdf) == ("failed", "check_failed", None)


# --- a worker that fails in every way ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body, reason",
    [
        ("sys.stdout.buffer.write(b'FAIL check_failed\\n')", "check_failed"),
        ("sys.stdout.buffer.write(b'FAIL glyph_missing\\n')", "glyph_missing"),
        ("sys.stdout.buffer.write(b'FAIL render_error\\n')", "render_error"),
        ("sys.stdout.buffer.write(b'FAIL timeout\\n')", "timeout"),
        ("sys.stdout.buffer.write(b'FAIL something_else\\n')", "render_error"),
        ("sys.stdout.buffer.write(b'FAIL \\n')", "render_error"),
        ("sys.exit(1)", "render_error"),
        ("os.kill(os.getpid(), 9)", "render_error"),
        ("pass", "render_error"),
        ("sys.stdout.buffer.write(b'garbage')", "render_error"),
        ("sys.stdout.buffer.write(b'OK\\nnot a pdf')", "render_error"),
        ("sys.stdout.buffer.write(b'OK\\n%PDF-1.4 cut off')", "render_error"),
        ("sys.stdout.buffer.write(b'OK\\n')", "render_error"),
        ("sys.stdout.buffer.write(b'OK \\n' + " + repr(PDF) + ")", "render_error"),
        ("sys.stdout.buffer.write(b'OK\\n' + " + repr(PDF) + "); sys.exit(3)", "render_error"),
    ],
)
def test_a_worker_that_fails_or_answers_badly_is_a_failed_report_with_a_reason_from_the_list(tmp_path, body, reason):
    outcome = make_report(small(), command=stub(tmp_path, body))
    assert outcome.status == "failed" and outcome.reason == reason and outcome.pdf is None and outcome.reason in REASONS


def test_an_answer_that_ends_like_a_pdf_but_does_not_start_like_one_is_not_accepted(tmp_path):
    outcome = make_report(small(), command=stub(tmp_path, "sys.stdout.buffer.write(b'OK\\nnot a pdf at all\\n%%EOF\\n')"))
    assert (outcome.status, outcome.reason) == ("failed", "render_error")


def test_a_worker_that_answers_properly_is_a_written_report(tmp_path):
    outcome = make_report(small(), command=stub(tmp_path, "sys.stdout.buffer.write(b'OK\\n' + " + repr(PDF) + ")"))
    assert outcome.status == "written" and outcome.pdf == PDF


def test_a_worker_that_cannot_be_started_is_a_render_error():
    outcome = make_report(small(), command=("/nonexistent/worker",))
    assert (outcome.status, outcome.reason) == ("failed", "render_error")


def test_a_worker_that_runs_past_the_time_limit_is_stopped_as_a_timeout(tmp_path):
    started = time.monotonic()
    outcome = make_report(small(), time_limit=1.0, command=stub(tmp_path, "time.sleep(600)"))
    assert (outcome.status, outcome.reason) == ("failed", "timeout") and time.monotonic() - started < 15


def test_a_worker_that_never_reads_a_huge_memo_still_times_out(tmp_path):
    started = time.monotonic()
    outcome = make_report("x" * 5_000_000, time_limit=1.0, command=(sys.executable, "-c", "import time; time.sleep(600)"))
    assert (outcome.status, outcome.reason) == ("failed", "timeout") and time.monotonic() - started < 15


def test_a_stopped_worker_and_its_children_are_gone(tmp_path):
    pids = tmp_path / "pids.txt"
    body = (
        "import subprocess\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        f"open({str(pids)!r}, 'w').write(f'{{os.getpid()}} {{child.pid}}')\n"
        "time.sleep(600)\n"
    )
    make_report(small(), time_limit=1.5, command=stub(tmp_path, body))
    worker, child = (int(n) for n in pids.read_text().split())
    time.sleep(0.3)
    for pid in (worker, child):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_what_a_worker_writes_to_its_error_stream_is_discarded(tmp_path, capfd):
    outcome = make_report(small(), command=stub(tmp_path, "sys.stderr.write('SECRET-TEXT'); sys.exit(1)"))
    captured = capfd.readouterr()
    assert outcome.reason == "render_error" and "SECRET" not in captured.out + captured.err


# --- it never raises, and the warning is fixed -----------------------------------------------------------------------------------------


def test_make_report_never_raises_whatever_goes_wrong(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("something unforeseen")

    monkeypatch.setattr(build, "_run_worker", boom)
    outcome = make_report(small())
    assert (outcome.status, outcome.reason) == ("failed", "render_error")


@pytest.mark.parametrize("reason", REASONS)
def test_the_warning_is_one_fixed_line_with_the_reason_and_nothing_from_the_document(tmp_path, caplog, reason):
    memo = small("SECRETWORD7 and 漢")
    with caplog.at_level(logging.WARNING, logger="credit_intel.report"):
        make_report(memo, command=stub(tmp_path, f"sys.stdout.buffer.write(b'FAIL {reason}\\n')"))
    (record,) = caplog.records
    assert record.levelno == logging.WARNING and record.name == "credit_intel.report"
    assert record.getMessage() == f"report not written ({reason}); memo.md is complete"
    assert "SECRETWORD7" not in caplog.text


def test_a_written_report_logs_no_warning(memo, caplog):
    with caplog.at_level(logging.WARNING, logger="credit_intel.report"):
        make_report(memo)
    assert caplog.records == []
