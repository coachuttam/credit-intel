"""The offline, counts-only diagnosis of a tuning run from its cached reply (Phase 2 G5; B-233).

Synthetic PDFs and a scripted fake provider: no network, no key, no real document.
"""

import json

import pytest

import pipeline_fixture as fx
from credit_intel.evaluation.diagnose import diagnose
from credit_intel.evaluation.guard import MEMBERS, SendRefused, file_sha256
from credit_intel.evaluation.runner import run_tuning_document
from credit_intel.llm.provider import FakeProvider


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def record(tmp_path, pdf, set_="tuning"):
    values = ["R9", file_sha256(pdf), set_, "2026-10-20", "assigned", None, None]
    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, values)), separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def run_first(pdf, tmp_path, reply):
    assignments = record(tmp_path, pdf)
    run_tuning_document(pdf, FakeProvider(script=[reply]), fx.LLM, assignments=assignments, cache_dir=tmp_path / "cache")
    return assignments


def test_a_cached_run_is_replayed_without_a_call(pdf, tmp_path):
    assignments = run_first(pdf, tmp_path, fx.good_response(pdf))

    result = diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "cache", llm=fx.LLM)

    assert result["replayed"] is True and result["cache_hits"] == 1 and result["document_id"] == "R9"
    assert result["candidate_pages"] == [1]
    assert len(result["field_proposals"]) == 6 and len(result["attribute_proposals"]) > 0
    page = result["pages"][0]
    assert page["columns"] == 2 and page["problems"] == [] and page["rotation"] == 0
    assert all(a["validated"] for a in page["anchors"])


def test_a_good_run_shows_every_proposal_passing(pdf, tmp_path):
    assignments = run_first(pdf, tmp_path, fx.good_response(pdf))

    result = diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "cache", llm=fx.LLM)

    for field in result["field_proposals"]:
        assert field["evidence_verified"] and field["value_in_evidence"] and field["link_failure"] is None
        assert field["claimed_period_has_column_on_page"] and field["what_if_column_outcome"] == "pass"
    periods = [a for a in result["attribute_proposals"] if a["attribute"] == "period_end"]
    assert periods and all(a["resolved"] and a["resolved_date_equals_proposed"] for a in periods)
    assert all(a["lines_holding_raw_text"] and a["raw_text_occurrences"] >= 1 for a in periods)  # on one line
    assert all(0 in f["column_day_offsets_from_claimed"] for f in result["field_proposals"] if f["role"] == "current")


def test_a_cache_miss_is_reported_and_nothing_is_called(pdf, tmp_path):
    assignments = record(tmp_path, pdf)

    result = diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "empty", llm=fx.LLM)

    assert result == {"document_id": "R9", "replayed": False, "cache_hits": 0}


def test_a_period_that_fails_to_resolve_is_explained(pdf, tmp_path):
    attributes = json.loads(fx.good_response(pdf))["attributes"]
    for attribute in attributes:
        if attribute["attribute"] == "period_end" and attribute["period_role"] == "current":
            attribute["normalised_value"] = "2001-01-01"  # not the page's date
    reply = fx.reply(attributes, json.loads(fx.good_response(pdf))["fields"])
    assignments = run_first(pdf, tmp_path, reply)

    result = diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "cache", llm=fx.LLM)

    current = next(a for a in result["attribute_proposals"] if a.get("role") == "current" and a["attribute"] == "period_end")
    assert current["resolved"] is True and current["resolved_date_equals_proposed"] is False
    assert all(f["claimed_period_has_column_on_page"] is False for f in result["field_proposals"] if f["role"] == "current")


def test_the_output_holds_no_text_quote_or_value(pdf, tmp_path):
    assignments = run_first(pdf, tmp_path, fx.good_response(pdf))

    text = json.dumps(diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "cache", llm=fx.LLM))

    for secret in ("Total current assets", "1,482.30", "1,356.75", "statement.pdf", str(tmp_path)):
        assert secret not in text
    assert "2025" not in text  # no date either


def test_a_held_out_document_is_refused(pdf, tmp_path):
    assignments = record(tmp_path, pdf, set_="held_out")

    with pytest.raises(SendRefused):
        diagnose(pdf, assignments=assignments, cache_dir=tmp_path / "cache", llm=fx.LLM)
