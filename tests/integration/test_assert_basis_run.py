"""--assert-basis through the pipeline and the command line: the flag, the conflict stop and the gate (PRD H.4.6 v0.4.24, FR-014; OD-10 option 3; step A1; B-278).

Step A1: where the assertion applies, the conflict stop, the gate and the flag. Step A2 (B-280, `test_basis_evidence_run.py`): what a field and the
``statement_basis`` attribute do under an assertion. The records and the memo disclosure come in the next step.
"""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.cli import main
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis as B, Status

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)


def clock():
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    return lambda: next(ticks)


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")


def untitled_reply(pdf):
    return fx.good_response(pdf).replace("Consolidated Balance Sheet", "Balance Sheet")


def run(pdf, tmp_path, provider, **kw):
    return run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "cache", **kw)


class NoCall:
    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        raise AssertionError("no model call may be made")


# --- the pipeline -----------------------------------------------------------------------------------------------------------------------------


def test_without_an_assertion_an_untitled_statement_stops_at_the_gate_before_any_call(untitled, tmp_path):
    provider = NoCall()

    with pytest.raises(IngestionError) as caught:
        run(untitled, tmp_path, provider, page_range="1")

    assert caught.value.code is ErrorCode.BASIS_UNAVAILABLE and provider.calls == 0


def test_with_an_assertion_the_gate_passes_and_the_pages_are_sent(untitled, tmp_path):
    provider = FakeProvider(script=[untitled_reply(untitled)])

    result = run(untitled, tmp_path, provider, page_range="1", assert_basis=B.CONSOLIDATED)

    assert len(provider.calls) == 1 and result.stats.llm_calls == 1
    assert result.basis_assertion.basis is B.CONSOLIDATED and result.basis_assertion.pages == (1,) and result.basis_assertion.applied_pages == (1,)


def test_a_page_naming_the_other_basis_stops_the_run_before_any_call(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")
    provider = NoCall()

    with pytest.raises(IngestionError) as caught:
        run(pdf, tmp_path, provider, page_range="1-2", assert_basis=B.CONSOLIDATED)

    assert caught.value.code is ErrorCode.BASIS_UNAVAILABLE and "pages whose title names the other basis: 2" in caught.value.detail and provider.calls == 0


def test_an_asserted_basis_other_than_the_configured_one_stops_at_the_gate_and_says_which_was_asserted(untitled, tmp_path):
    provider = NoCall()

    with pytest.raises(IngestionError) as caught:
        run(untitled, tmp_path, provider, page_range="1", assert_basis=B.STANDALONE, basis=B.CONSOLIDATED)

    assert "standalone (asserted)" in caught.value.detail and provider.calls == 0


def test_the_other_configured_basis_with_the_same_assertion_passes(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.STANDALONE, basis=B.STANDALONE)

    assert result.basis_assertion.applied_pages == (1,) and result.configured_basis is B.STANDALONE


def test_an_assertion_on_pages_that_all_name_the_basis_is_recorded_as_not_applied(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "titled.pdf")

    result = run(pdf, tmp_path, FakeProvider(script=[fx.good_response(pdf)]), page_range="1", assert_basis=B.CONSOLIDATED)

    assert result.basis_assertion.applied_pages == () and result.basis_assertion.pages == (1,)
    assert {r.status for r in result.field_set.fields} >= {Status.EXTRACTED}


def test_no_assertion_records_none_and_changes_nothing(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "titled.pdf")

    result = run(pdf, tmp_path, FakeProvider(script=[fx.good_response(pdf)]))

    assert result.basis_assertion is None


def test_an_assertion_needs_a_page_range_in_the_library_too(untitled, tmp_path):
    with pytest.raises(ValueError):
        run(untitled, tmp_path, NoCall(), assert_basis=B.CONSOLIDATED)


def test_the_assertion_is_not_part_of_the_request_so_the_cache_serves_it_whatever_is_asserted(untitled, tmp_path):
    first = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.CONSOLIDATED)
    again = NoCall()

    second = run(untitled, tmp_path, again, page_range="1", assert_basis=B.CONSOLIDATED)

    assert first.stats.cache_misses == 1 and second.stats.cache_hits == 1 and again.calls == 0


# --- the command line -------------------------------------------------------------------------------------------------------------------------


def settings(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    return path


def cli(tmp_path, *argv, replies=None, factory=None):
    out, err = io.StringIO(), io.StringIO()
    code = main([*map(str, argv), "--config", str(settings(tmp_path))], provider_factory=factory or (lambda s, e: FakeProvider(script=replies or [])),
                clock=clock(), stdout=out, stderr=err, env={})  # fmt: skip
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("argv", [["--assert-basis", "consolidated"], ["--assert-basis", "standalone", "--basis", "standalone"]])
def test_the_flag_without_pages_is_a_usage_error_with_exit_2_and_nothing_runs(untitled, tmp_path, argv):
    def no_provider(s, e):
        raise AssertionError("nothing may run")

    code, out, err = cli(tmp_path, untitled, *argv, factory=no_provider)

    assert code == 2 and out == "" and "--assert-basis requires --pages" in err and "usage: credit-intel" in err
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("value", ["unknown", "both", ""])
def test_a_basis_that_cannot_be_asserted_is_a_usage_error(untitled, tmp_path, value):
    code, out, err = cli(tmp_path, untitled, "--pages", "1", "--assert-basis", value)

    assert code == 2 and out == "" and "usage: credit-intel" in err


def test_an_empty_page_range_does_not_count_as_pages(untitled, tmp_path):
    code, out, err = cli(tmp_path, untitled, "--pages", "", "--assert-basis", "consolidated")

    assert code == 2 and "--assert-basis requires --pages" in err


def test_a_run_with_pages_and_the_flag_passes_the_gate_and_exits_0(untitled, tmp_path):
    code, out, err = cli(tmp_path, untitled, "--pages", "1", "--assert-basis", "consolidated", replies=[untitled_reply(untitled)])

    assert code == 0 and Path(out.strip()).is_dir() and "asserted_pages=1" in err


def test_a_conflicting_page_exits_4_names_the_page_and_leaves_a_failure_record(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")

    code, out, err = cli(tmp_path, pdf, "--pages", "1-2", "--assert-basis", "consolidated")

    assert code == 4 and out == "" and "E-EXTRACT-BASIS-UNAVAILABLE" in err and "pages whose title names the other basis: 2" in err
    (folder,) = sorted((tmp_path / "runs").iterdir())
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert [p.name for p in folder.iterdir()] == ["manifest.json"] and manifest["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE" and manifest["failed_stage"] == "statements_located"


def test_without_the_flag_the_same_untitled_document_stops_at_the_gate_with_exit_4(untitled, tmp_path):
    code, out, err = cli(tmp_path, untitled, "--pages", "1")

    assert code == 4 and "E-EXTRACT-BASIS-UNAVAILABLE" in err and "bases found: unknown" in err


def test_a_failure_message_with_an_assertion_holds_no_document_text(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")

    code, out, err = cli(tmp_path, pdf, "--pages", "1-2", "--assert-basis", "consolidated")

    for forbidden in ("Total current assets", "1,482.30", "Acme", "Standalone Balance Sheet", str(tmp_path)):
        assert forbidden not in err


def test_an_assertion_without_a_page_range_is_refused_before_anything_is_read_even_if_no_page_would_qualify(tmp_path):
    blank = fx.blank_text_pdf(tmp_path / "blank.pdf")  # a keyword run on this finds no statement pages

    with pytest.raises(ValueError, match="page range"):
        run(blank, tmp_path, NoCall(), assert_basis=B.CONSOLIDATED)
