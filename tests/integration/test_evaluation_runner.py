"""Counts-only summaries, the tuning runner and the dry run (Phase 2 Part A; B-232).

Synthetic PDFs and a scripted fake provider: no network, no key, no real document.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.config import PricingSettings
from credit_intel.evaluation.dry_run import dry_run, main
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.runner import run_tuning_document
from credit_intel.evaluation.summary import summarise_run, summarise_stop, to_line
from credit_intel.extraction.extract import render_pages
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import load_prompt
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.llm.budget import estimate_tokens
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import StatementBasis

PRICES = PricingSettings(Decimal("0.15"), Decimal("0.60"))


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def record(tmp_path, pdf, set_="tuning", document_id="R9"):
    values = [document_id, file_sha256(pdf), set_, "2026-10-20", "assigned", None, None]
    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, values)), separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def page_text(pdf):
    return PdfplumberExtractor().extract_pages(pdf)[0].text


def tuning(pdf, tmp_path, replies=None, **kw):
    provider = FakeProvider(script=replies if replies is not None else [fx.good_response(pdf)])
    kw.setdefault("assignments", record(tmp_path, pdf))
    kw.setdefault("cache_dir", tmp_path / "cache")
    return run_tuning_document(pdf, provider, fx.LLM, pricing=PRICES, **kw), provider


# --- the summary ------------------------------------------------------------------------------------------


def test_a_completed_run_is_summarised_by_counts(pdf, tmp_path):
    summary, _ = tuning(pdf, tmp_path)

    assert summary["outcome"] == "completed" and summary["document_id"] == "R9"
    assert summary["pages"] == 1 and summary["candidate_pages"] == [1] and summary["locator"] == "keywords"
    assert summary["fields"]["counts"] == {"extracted": 6, "not_found": 18, "conflicting": 0, "requires_review": 0}
    assert summary["fields"]["by_basis"] == {"consolidated": 6} and summary["fields"]["proposed"] == 6
    assert summary["prompt_version"] == "extraction-v2" and summary["attempts"] == 1
    assert summary["llm_calls"] == 1 and summary["tokens_in"] > 0 and summary["tokens_out"] > 0
    assert Decimal(summary["cost_usd"]) > 0 and summary["sha256_prefix"] == file_sha256(pdf)[:12]


def test_the_outcomes_name_fields_and_statuses_but_no_values(pdf, tmp_path):
    summary, _ = tuning(pdf, tmp_path)

    assert "current_assets/current/consolidated: extracted" in summary["fields"]["outcomes"]
    assert len(summary["fields"]["outcomes"]) == 6
    assert summary["attributes"]["period_end.current"] == "extracted"
    assert summary["attributes"]["entity_name"] == "extracted"


def test_reasons_are_counted_when_fields_fail(pdf, tmp_path):
    wrong = fx.field(pdf, "current_assets", "current", "1,356.75", "Total current assets")
    reply = fx.reply(fx.good_attributes(pdf), [wrong] + json.loads(fx.good_response(pdf))["fields"][1:])

    summary, _ = tuning(pdf, tmp_path, replies=[reply])

    assert summary["fields"]["counts"]["requires_review"] == 1
    assert summary["fields"]["reasons"] == {"period_not_verified": 1}
    assert "current_assets/current/consolidated: requires_review (period_not_verified)" in summary["fields"]["outcomes"]


def test_the_summary_holds_no_document_text_quotes_or_values(pdf, tmp_path):
    summary, _ = tuning(pdf, tmp_path)
    line = to_line("tuning run", summary)

    for document_line in page_text(pdf).split("\n"):
        assert document_line not in line
    for secret in ("Acme", "Industries", "1,482.30", "1,356.75", "14823000000", "Rs. in crore", "statement.pdf", str(tmp_path)):
        assert secret not in line, secret


def test_the_line_is_one_ascii_line_with_sorted_keys_and_is_repeatable(pdf, tmp_path):
    summary, _ = tuning(pdf, tmp_path)
    again, _ = tuning(pdf, tmp_path, replies=[], cache_dir=tmp_path / "cache")  # served from the cache

    line = to_line("tuning run", summary)

    assert line.isascii() and "\n" not in line and line.startswith("tuning run: {")
    payload = json.loads(line.split(": ", 1)[1])
    assert list(payload) == sorted(payload) and payload == json.loads(json.dumps(summary, sort_keys=True))
    assert again["llm_calls"] == 0 and again["cache_hits"] == 1  # the same document, not re-sent


def test_a_run_without_prices_has_no_cost(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])

    summary = run_tuning_document(pdf, provider, fx.LLM, assignments=record(tmp_path, pdf), cache_dir=tmp_path / "c")

    assert summary["cost_usd"] is None and summary["tokens_in"] > 0


# --- a stop is a result -----------------------------------------------------------------------------------------


def test_a_missing_configured_basis_is_a_stopped_result_with_no_call(pdf, tmp_path):
    summary, provider = tuning(pdf, tmp_path, basis=StatementBasis.STANDALONE)

    assert summary["outcome"] == "stopped" and summary["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert "bases found: consolidated" in summary["detail"] and provider.calls == []
    assert "tokens_in" not in summary


def test_the_stop_summary_is_counts_only():
    summary = summarise_stop(IngestionError(ErrorCode.NO_STATEMENT_PAGES), "R2", "ab" * 32)

    assert summary == {"outcome": "stopped", "document_id": "R2", "sha256_prefix": "abababababab",
                       "error_code": "E-EXTRACT-NO-STATEMENT-PAGES", "detail": None}  # fmt: skip


def test_an_unreadable_file_is_a_catalogued_error_not_a_result(tmp_path):
    provider = FakeProvider(script=["unused"])

    with pytest.raises(IngestionError) as excinfo:
        run_tuning_document(tmp_path / "absent.pdf", provider, fx.LLM, assignments=tmp_path / "a.jsonl")

    assert excinfo.value.code is ErrorCode.NOT_FOUND and provider.calls == []
    assert "absent" not in str(excinfo.value) and str(tmp_path) not in str(excinfo.value)


# --- the guard runs first --------------------------------------------------------------------------------------------


def test_a_document_not_on_the_record_is_refused_before_any_call(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])
    empty = tmp_path / "assignments.jsonl"
    empty.write_text("", encoding="utf-8")

    with pytest.raises(SendRefused):
        run_tuning_document(pdf, provider, fx.LLM, assignments=empty, cache_dir=tmp_path / "c")

    assert provider.calls == [] and not (tmp_path / "c").exists()


def test_a_held_out_document_is_refused_before_any_call(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])

    with pytest.raises(SendRefused) as excinfo:
        run_tuning_document(pdf, provider, fx.LLM, assignments=record(tmp_path, pdf, "held_out", "H1"), cache_dir=tmp_path / "c")

    assert "H1" in str(excinfo.value) and provider.calls == []


def test_a_synthetic_document_needs_the_explicit_exemption_a_test_gives(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])
    nothing = tmp_path / "assignments.jsonl"
    nothing.write_text("", encoding="utf-8")

    summary = run_tuning_document(pdf, provider, fx.LLM, assignments=nothing, cache_dir=tmp_path / "c", synthetic=True)

    assert summary["document_id"] == "synthetic" and summary["outcome"] == "completed"


# --- the dry run: sizes and estimates with nothing sent -----------------------------------------------------------


def test_the_dry_run_sizes_the_candidate_pages_and_the_gate(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf), pricing=PRICES)

    assert result["document_id"] == "R9" and result["set"] == "tuning" and result["pages"] == 1
    assert result["candidate_pages"] == [1] and result["candidate_chars_total"] == len(page_text(pdf))
    assert result["basis_gate"] == {"passes": True, "error_code": None, "detail": None}
    assert result["prompt_version"] == "extraction-v2" and result["max_output_tokens"] == fx.LLM.max_output_tokens


def test_the_dry_run_estimate_is_the_same_one_the_budget_uses(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf), pricing=PRICES)
    document = ingest(pdf)
    expected = estimate_tokens(load_prompt().system + render_pages(document, (1,)))

    assert result["input_estimate_tokens"] == expected
    assert result["reservation_per_call"] == expected + fx.LLM.max_output_tokens
    assert result["reservation_two_calls"] == 2 * result["reservation_per_call"]


def test_the_suggested_ceiling_covers_two_calls_in_whole_ten_thousands(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf), pricing=PRICES)

    ceiling = result["suggested_ceiling"]
    assert ceiling % 10_000 == 0 and ceiling >= result["reservation_two_calls"]
    assert ceiling - result["reservation_two_calls"] < 10_000


def test_the_dry_run_worst_cases_follow_the_prices_exactly(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf), pricing=PRICES)
    estimate = result["input_estimate_tokens"]
    one = (estimate * Decimal("0.15") + fx.LLM.max_output_tokens * Decimal("0.60")) / 1_000_000

    assert Decimal(result["worst_case_usd_one_call"]) == one
    assert Decimal(result["worst_case_usd_two_calls"]) == 2 * one
    assert Decimal(result["ceiling_bound_usd"]) == Decimal(result["suggested_ceiling"]) * Decimal("0.60") / 1_000_000


def test_without_prices_the_dry_run_gives_sizes_but_no_cost(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf))

    assert result["worst_case_usd_one_call"] is None and result["ceiling_bound_usd"] is None
    assert result["input_estimate_tokens"] > 0


def test_a_basis_the_document_lacks_shows_in_the_gate_with_no_call_possible(pdf, tmp_path):
    result = dry_run(pdf, fx.LLM, basis="standalone", assignments=record(tmp_path, pdf))

    assert result["basis_gate"]["passes"] is False
    assert result["basis_gate"]["error_code"] == "E-EXTRACT-BASIS-UNAVAILABLE"
    assert "bases found: consolidated" in result["basis_gate"]["detail"]


def test_a_document_with_no_statement_pages_has_no_estimate(tmp_path):
    pdf = fx.blank_text_pdf(tmp_path / "report.pdf")

    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf))

    assert result["candidate_pages"] == [] and result["input_estimate_tokens"] is None
    assert result["basis_gate"]["error_code"] == "E-EXTRACT-NO-STATEMENT-PAGES" and result["suggested_ceiling"] is None


def test_an_unrecorded_document_is_reported_without_an_id_not_refused(pdf, tmp_path):
    empty = tmp_path / "assignments.jsonl"
    empty.write_text("", encoding="utf-8")

    result = dry_run(pdf, fx.LLM, assignments=empty)  # a dry run sends nothing, so it needs no permission

    assert result["document_id"] is None and result["set"] is None


def test_a_page_range_is_honoured_by_the_dry_run(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "two.pdf", narrative_page="Directors report")

    result = dry_run(pdf, fx.LLM, page_range="1-2", assignments=record(tmp_path, pdf))

    assert result["locator"] == "page_range" and result["candidate_pages"] == [1, 2]
    assert set(result["candidate_chars"]) == {1, 2}


def test_the_dry_run_output_has_no_document_text(pdf, tmp_path):
    line = json.dumps(dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf), pricing=PRICES), sort_keys=True)

    for document_line in page_text(pdf).split("\n"):
        assert document_line not in line
    assert "Acme" not in line and "1,482.30" not in line and str(tmp_path) not in line


def test_the_command_prints_one_json_line(pdf, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CREDIT_INTEL_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("CREDIT_INTEL_LLM_PROVIDER", "openai")
    monkeypatch.setenv("CREDIT_INTEL_LLM_MODEL_ID", "gpt-4o-mini")
    monkeypatch.chdir(Path(__file__).resolve().parents[2])

    code = main([str(pdf)])

    out = capsys.readouterr().out
    assert code == 0 and out.startswith("dry run: {") and out.count("\n") == 1
    assert json.loads(out.split(": ", 1)[1])["max_output_tokens"] == 8192


def test_the_command_reports_an_unreadable_input_on_stderr(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])

    code = main([str(tmp_path / "absent.pdf")])

    captured = capsys.readouterr()
    assert code == 1 and captured.out == ""
    assert captured.err.strip() == "dry run: stopped E-INPUT-NOT-FOUND" and str(tmp_path) not in captured.err


# --- pages of unknown basis (H.4.6, v0.4.21; B-235) ---------------------------------------------------------------------------


def mixed_pdf(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "mixed.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    fx._statement_page(pdf, fx.STANDALONE_ROWS, "Balance Sheet", "(Rs. in crore)")
    fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    pdf.save()
    return path


def test_the_summary_counts_the_pages_removed_for_an_unknown_basis(tmp_path):
    pdf = mixed_pdf(tmp_path)

    summary, _ = tuning(pdf, tmp_path, replies=[fx.reply([], [])])

    assert summary["candidate_pages"] == [2] and summary["excluded_candidates"] == 1
    assert summary["excluded_by_reason"] == {"basis_unknown": 1}


def test_the_dry_run_prices_only_the_pages_that_would_be_sent(tmp_path):
    pdf = mixed_pdf(tmp_path)

    result = dry_run(pdf, fx.LLM, assignments=record(tmp_path, pdf))

    assert result["candidate_pages"] == [2] and result["removed_for_unknown_basis"] == [1]
    assert result["basis_gate"]["passes"] is True
