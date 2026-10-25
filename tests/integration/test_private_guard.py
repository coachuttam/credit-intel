"""The owner's private/ folder is closed to both models unless the owner approves the run (PRD v0.4.31, SEC-10; B-299). Synthetic documents only."""

import json
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.config import LLMSettings
from credit_intel.evaluation.guard import ENV_PRIVATE_APPROVED, MEMBERS, SendRefused, check_private_path, file_sha256, is_private_path
from credit_intel.evaluation.runner import run_tuning_document
from credit_intel.llm.provider import FakeProvider

OPENAI = LLMSettings(provider="openai", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "private").mkdir()
    return tmp_path


def tuning_record(tmp_path, pdf):
    path = tmp_path / "assignments.jsonl"
    path.write_text(json.dumps(dict(zip(MEMBERS, ("R9", file_sha256(pdf), "tuning", "2026-10-20", "assigned", None, None), strict=True))) + "\n", encoding="utf-8")
    return path


def test_the_owners_private_folder_is_recognised_as_written_relative_absolute_or_through_a_link(workdir):
    document = workdir / "private" / "report.pdf"
    document.write_bytes(b"%PDF-")
    link = workdir / "report-link.pdf"
    link.symlink_to(document)

    assert is_private_path(document) and is_private_path(Path("private/report.pdf")) and is_private_path(link)


def test_other_places_are_not_private_including_a_system_folder_that_happens_to_be_called_private(workdir):
    other = workdir / "elsewhere"
    other.mkdir()
    (other / "report.pdf").write_bytes(b"%PDF-")

    assert not is_private_path(other / "report.pdf") and not is_private_path(Path("/private/var/folders/x/report.pdf"))


def test_the_project_private_folder_counts_from_any_working_directory(tmp_path, monkeypatch):
    from credit_intel.evaluation.guard import PROJECT_ROOT

    monkeypatch.chdir(tmp_path)

    assert is_private_path(PROJECT_ROOT / "private" / "R1_report.pdf") and not is_private_path(PROJECT_ROOT / "docs" / "PRD.md")


def test_the_approval_is_exactly_one_in_the_environment(workdir):
    document = workdir / "private" / "report.pdf"

    for value in (None, "", "0", "true", "yes"):
        env = {} if value is None else {ENV_PRIVATE_APPROVED: value}
        with pytest.raises(SendRefused):
            check_private_path(document, env)
    check_private_path(document, {ENV_PRIVATE_APPROVED: "1"})
    check_private_path(workdir / "public.pdf", {})


def test_the_refusal_names_no_path(workdir):
    with pytest.raises(SendRefused) as caught:
        check_private_path(workdir / "private" / "secret-name.pdf", {})

    assert "secret-name" not in str(caught.value) and str(workdir) not in str(caught.value)


def run(pdf, tmp_path, env, llm=OPENAI, **kw):
    provider = FakeProvider(script=[fx.good_response(pdf)])
    return run_tuning_document(pdf, provider, llm, assignments=tuning_record(tmp_path, pdf), cache_dir=tmp_path / "cache", env=env, **kw), provider


def test_the_tuning_runner_refuses_a_private_document_before_any_call_unless_the_owner_approved(workdir):
    pdf = fx.balance_sheet_pdf(workdir / "private" / "report.pdf")
    provider = FakeProvider(script=[fx.good_response(pdf)])

    with pytest.raises(SendRefused):
        run_tuning_document(pdf, provider, OPENAI, assignments=tuning_record(workdir, pdf), cache_dir=workdir / "cache", env={})

    assert provider.calls == []
    summary, ran = run(pdf, workdir, {ENV_PRIVATE_APPROVED: "1"})
    assert summary["outcome"] == "completed" and len(ran.calls) == 1


def test_the_approval_does_not_open_a_private_document_that_is_not_recorded_as_tuning(workdir):
    pdf = fx.balance_sheet_pdf(workdir / "private" / "report.pdf")

    with pytest.raises(SendRefused):
        run_tuning_document(pdf, FakeProvider(), OPENAI, assignments=workdir / "none.jsonl", cache_dir=workdir / "cache", env={ENV_PRIVATE_APPROVED: "1"})


def test_a_document_outside_private_needs_no_approval(workdir):
    pdf = fx.balance_sheet_pdf(workdir / "report.pdf")

    summary, _ = run(pdf, workdir, {})

    assert summary["outcome"] == "completed"


def test_a_provider_that_sends_nothing_and_synthetic_documents_are_not_held_to_it(workdir):
    pdf = fx.balance_sheet_pdf(workdir / "private" / "report.pdf")
    local = LLMSettings(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000)

    summary, _ = run(pdf, workdir, {}, llm=local)
    synthetic, _ = run(pdf, workdir, {}, synthetic=True)

    assert summary["outcome"] == "completed" and synthetic["outcome"] == "completed"
