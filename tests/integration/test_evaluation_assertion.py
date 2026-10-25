"""The analyst's basis assertion through the tuning tools: runner, counts-only summary, dry run and the live test's environment (PRD H.4.6 v0.4.24; live-round plan step L0; B-284)."""

import json

import pytest

import pipeline_fixture as fx
from credit_intel.evaluation.dry_run import dry_run, main as dry_run_main
from credit_intel.evaluation.runner import run_tuning_document, tuning_options
from credit_intel.evaluation.summary import to_line
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis as B


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")


def reply(pdf):
    return fx.good_response(pdf).replace("Consolidated Balance Sheet", "Balance Sheet")


def tune(pdf, tmp_path, provider=None, **kw):
    provider = provider or FakeProvider(script=[reply(pdf)])
    return run_tuning_document(pdf, provider, fx.LLM, cache_dir=tmp_path / "cache", synthetic=True, **kw), provider


# --- the runner and its counts-only summary -----------------------------------------------------------------------------------------------------


def test_a_run_with_an_assertion_reports_it_and_how_many_records_rest_on_it(untitled, tmp_path):
    summary, provider = tune(untitled, tmp_path, page_range="1", assert_basis=B.CONSOLIDATED)

    assert summary["outcome"] == "completed" and len(provider.calls) == 1
    assert summary["basis_assertion"] == {"basis": "consolidated", "pages": [1], "applied_pages": [1]}
    assert summary["basis_evidence"] == {"analyst_assertion": 6}


def test_a_run_without_one_reports_none_and_title_evidence_only(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "titled.pdf")

    summary, _ = tune(pdf, tmp_path, provider=FakeProvider(script=[fx.good_response(pdf)]))

    assert summary["basis_assertion"] is None and set(summary["basis_evidence"]) == {"title"}


def test_the_summary_holds_page_numbers_and_names_but_no_text_quote_label_or_value(untitled, tmp_path):
    summary, _ = tune(untitled, tmp_path, page_range="1", assert_basis=B.CONSOLIDATED)
    line = to_line("tuning run", summary)

    for forbidden in ("Total current assets", "1,482.30", "Acme", "untitled.pdf", str(tmp_path), "Balance Sheet"):
        assert forbidden not in line
    assert '"basis_assertion"' in line and '"basis_evidence"' in line


def test_a_conflict_is_a_stopped_result_that_names_the_pages_and_the_requested_basis_and_makes_no_call(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")
    provider = FakeProvider(script=[])

    summary, _ = tune(pdf, tmp_path, provider=provider, page_range="1-2", assert_basis=B.CONSOLIDATED)

    assert summary["outcome"] == "stopped" and summary["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert "pages whose title names the other basis: 2" in summary["detail"] and summary["asserted_basis"] == "consolidated" and provider.calls == []


def test_without_the_assertion_an_untitled_statement_stops_at_the_gate(untitled, tmp_path):
    summary, provider = tune(untitled, tmp_path, provider=FakeProvider(script=[]), page_range="1")

    assert summary["outcome"] == "stopped" and summary["asserted_basis"] is None and provider.calls == []


# --- the dry run --------------------------------------------------------------------------------------------------------------------------------


def llm_settings():
    return fx.LLM


def empty_record(tmp_path):
    """A present, empty assignment record: the guard fails closed on a missing one, so a test supplies an empty file."""
    path = tmp_path / "assignments.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def test_the_dry_run_reports_the_assertion_and_passes_the_gate_it_would_pass(untitled, tmp_path):
    result = dry_run(untitled, llm_settings(), page_range="1", assert_basis="consolidated", assignments=empty_record(tmp_path))

    assert result["basis_gate"]["passes"] is True and result["asserted_basis"] == "consolidated"
    assert result["basis_assertion"] == {"basis": "consolidated", "pages": [1], "applied_pages": [1]} and result["candidate_pages"] == [1]


def test_the_dry_run_without_the_assertion_shows_the_gate_failing_for_an_untitled_statement(untitled, tmp_path):
    result = dry_run(untitled, llm_settings(), page_range="1", assignments=empty_record(tmp_path))

    assert result["basis_gate"]["passes"] is False and result["basis_gate"]["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert result["basis_assertion"] is None and result["asserted_basis"] is None


def test_the_dry_run_shows_a_conflict_as_the_gate_failing_with_the_pages(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "two.pdf")

    result = dry_run(pdf, llm_settings(), page_range="1-2", assert_basis="consolidated", assignments=empty_record(tmp_path))

    assert result["basis_gate"]["passes"] is False and "other basis: 2" in result["basis_gate"]["detail"] and result["basis_assertion"] is None


def test_an_assertion_other_than_the_configured_basis_stops_the_dry_run_gate_and_says_so(untitled, tmp_path):
    result = dry_run(untitled, llm_settings(), page_range="1", assert_basis="standalone", assignments=empty_record(tmp_path))

    assert result["basis_gate"]["passes"] is False and "standalone (asserted)" in result["basis_gate"]["detail"]


def test_the_dry_run_library_refuses_an_assertion_without_pages(untitled, tmp_path):
    with pytest.raises(ValueError, match="page range"):
        dry_run(untitled, llm_settings(), assert_basis="consolidated", assignments=empty_record(tmp_path))


def test_the_dry_run_command_takes_the_flag_prints_counts_only_and_needs_pages(untitled, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CREDIT_INTEL_MAX_OUTPUT_TOKENS", "2000")
    monkeypatch.setenv("CREDIT_INTEL_LLM_PROVIDER", "fake")
    monkeypatch.setenv("CREDIT_INTEL_LLM_MODEL_ID", "m")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\nmax_output_tokens = 2000\n', encoding="utf-8")

    assert dry_run_main([str(untitled), "--pages", "1", "--assert-basis", "consolidated"]) == 0
    out = capsys.readouterr().out
    data = json.loads(out.removeprefix("dry run: "))
    assert data["basis_assertion"]["applied_pages"] == [1] and "Total current assets" not in out and "1,482.30" not in out
    with pytest.raises(SystemExit) as stop:
        dry_run_main([str(untitled), "--assert-basis", "consolidated"])
    assert stop.value.code == 2


# --- the live test's environment ------------------------------------------------------------------------------------------------------------------


def test_the_environment_gives_the_basis_pages_and_assertion():
    assert tuning_options({}) == {"basis": B.CONSOLIDATED, "page_range": None, "assert_basis": None}
    assert tuning_options({"CREDIT_INTEL_BASIS": "standalone", "CREDIT_INTEL_PAGES": " 36-38 ", "CREDIT_INTEL_ASSERT_BASIS": "standalone"}) == {
        "basis": B.STANDALONE, "page_range": "36-38", "assert_basis": B.STANDALONE}  # fmt: skip
    assert tuning_options({"CREDIT_INTEL_PAGES": "", "CREDIT_INTEL_ASSERT_BASIS": ""})["page_range"] is None


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"CREDIT_INTEL_ASSERT_BASIS": "consolidated"}, "CREDIT_INTEL_ASSERT_BASIS needs CREDIT_INTEL_PAGES"),
        ({"CREDIT_INTEL_ASSERT_BASIS": "unknown", "CREDIT_INTEL_PAGES": "1"}, "CREDIT_INTEL_ASSERT_BASIS must be"),
        ({"CREDIT_INTEL_BASIS": "unknown"}, "CREDIT_INTEL_BASIS must be"),
    ],
)
def test_a_bad_environment_names_the_variable_and_never_its_value(env, name):
    with pytest.raises(ValueError, match=name) as caught:
        tuning_options(env)

    assert "unknown" not in str(caught.value).replace("must be consolidated or standalone", "")


def test_the_live_test_takes_its_run_options_from_the_environment_helper_and_documents_the_new_variable():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "live" / "test_live_tuning.py").read_text(encoding="utf-8")

    assert "**tuning_options(os.environ)" in source and "CREDIT_INTEL_ASSERT_BASIS" in source
    assert 'os.environ.get("CREDIT_INTEL_PAGES")' not in source  # the options are read in one place


def test_the_dry_run_refuses_an_assertion_without_pages_even_when_no_page_would_qualify(tmp_path):
    blank = fx.blank_text_pdf(tmp_path / "blank.pdf")  # a keyword run finds no candidate pages in it

    with pytest.raises(ValueError, match="page range"):
        dry_run(blank, llm_settings(), assert_basis="consolidated", assignments=empty_record(tmp_path))
