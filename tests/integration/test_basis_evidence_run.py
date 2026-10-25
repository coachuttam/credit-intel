"""Under an assertion a field and the statement_basis attribute are accepted and marked (PRD H.1, H.1.2, H.4.6 v0.4.24; OD-10 option 3; step A2; B-280)."""

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

import pipeline_fixture as fx
from credit_intel.calculations.calculate import calculate_metrics
from credit_intel.cli import main
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.llm.provider import FakeProvider
from credit_intel.models import BasisEvidence as E, FieldName as F, PeriodRole, StatementBasis as B, Status, StatusReason as R

START = datetime(2026, 10, 24, 10, 15, 30, 123456, tzinfo=UTC)
CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE


@pytest.fixture(autouse=True)
def in_a_scratch_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def run(pdf, tmp_path, provider, **kw):
    return run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "cache", **kw)


class NoCall:
    calls = 0

    def complete(self, request):
        raise AssertionError("no model call may be made")


def record(result, name, role):
    return result.field_set.get(name, role)


# --- a statement that never names its basis (like tuning report R2) ---------------------------------------------------------------------------------


@pytest.fixture
def untitled(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")


def untitled_reply(pdf, bogus_basis_quote=False):
    reply = fx.good_response(pdf)
    return reply if bogus_basis_quote else reply.replace("Consolidated Balance Sheet", "Balance Sheet")


def test_every_field_that_passes_its_other_checks_is_extracted_and_marked_as_asserted(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.CONSOLIDATED)

    extracted = [r for r in result.field_set.fields if r.status is Status.EXTRACTED]
    assert len(extracted) == 6 and {r.basis_evidence for r in extracted} == {E.ANALYST_ASSERTION}
    assert {r.statement_basis for r in extracted} == {B.CONSOLIDATED} and all(r.field_id.endswith(".consolidated") for r in extracted)
    assert {r.status_reason for r in extracted} == {None}


def test_the_statement_basis_attribute_is_extracted_by_the_assertion_and_blocks_nothing(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.CONSOLIDATED)
    attribute = result.attributes.statement_basis

    assert (attribute.status, attribute.normalised_value, attribute.basis_evidence) == (Status.EXTRACTED, "consolidated", E.ANALYST_ASSERTION)
    assert attribute.page_number is None and attribute.evidence_quote is None
    assert record(result, F.CURRENT_ASSETS, CUR).validation.details["blocked_by"] == []


def test_a_basis_proposal_the_model_made_with_a_quote_that_is_not_on_the_page_is_ignored(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled, bogus_basis_quote=True)]), page_range="1", assert_basis=B.CONSOLIDATED)

    assert result.attributes.statement_basis.basis_evidence is E.ANALYST_ASSERTION and result.attribute_basis_differs is False


def test_the_field_records_where_its_basis_came_from(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.CONSOLIDATED)

    assert record(result, F.CURRENT_ASSETS, CUR).validation.details["basis"] == {"value": "consolidated", "read_from": "analyst_assertion"}


def test_the_metrics_are_computed_from_asserted_fields_as_from_any_other(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.CONSOLIDATED)

    metrics = calculate_metrics(result.field_set)

    assert str(metrics.get("MET-03", CUR).value) == "1.647" and metrics.get("MET-03", COMP).defined


def test_the_other_configured_basis_with_a_matching_assertion_gives_standalone_fields(untitled, tmp_path):
    result = run(untitled, tmp_path, FakeProvider(script=[untitled_reply(untitled)]), page_range="1", assert_basis=B.STANDALONE, basis=B.STANDALONE)

    fields = [r for r in result.field_set.fields if r.status is Status.EXTRACTED]
    assert len(fields) == 6 and all(r.field_id.endswith(".standalone") and r.basis_evidence is E.ANALYST_ASSERTION for r in fields)


# --- a document with a titled page and an untitled one ------------------------------------------------------------------------------------------------


def mixed_pdf(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), invariant=1)
    fx._statement_page(pdf, [("Profit before tax", "", "352.70", "300.10"), ("Total current assets", "14", "1,482.30", "1,356.75"),
                             ("Total current liabilities", "15", "900.00", "850.00")], "Consolidated Balance Sheet", "(Rs. in crore)")  # fmt: skip
    fx._statement_page(pdf, [("Finance costs", "20", "38.50", "35.00"), ("Non-current borrowings", "16", "400.00", "350.00"),
                             ("Current borrowings", "17", "150.00", "120.00"), ("Total equity", "", "600.00", "500.00")], "Balance Sheet", "(Rs. in crore)")  # fmt: skip
    pdf.save()
    return path


def mixed_reply(pdf):
    data = {"attributes": fx.good_attributes(pdf), "fields": []}
    data["fields"] = [
        fx.field(pdf, "profit_before_tax", "current", "352.70", "Profit before tax"), fx.field(pdf, "profit_before_tax", "comparative", "300.10", "Profit before tax"),
        fx.field(pdf, "current_assets", "current", "1,482.30", "Total current assets"), fx.field(pdf, "current_assets", "comparative", "1,356.75", "Total current assets"),
        fx.field(pdf, "interest_expense", "current", "38.50", "Finance costs", page=2), fx.field(pdf, "interest_expense", "comparative", "35.00", "Finance costs", page=2),
        fx.field(pdf, "borrowings_non_current", "current", "400.00", "Non-current borrowings", page=2), fx.field(pdf, "borrowings_non_current", "comparative", "350.00", "Non-current borrowings", page=2),
        fx.field(pdf, "borrowings_current", "current", "150.00", "Current borrowings", page=2), fx.field(pdf, "borrowings_current", "comparative", "120.00", "Current borrowings", page=2),
        fx.field(pdf, "total_equity", "current", "600.00", "Total equity", page=2), fx.field(pdf, "total_equity", "comparative", "500.00", "Total equity", page=2),
    ]  # fmt: skip
    return json.dumps(data)


@pytest.fixture
def mixed(tmp_path):
    return mixed_pdf(tmp_path / "mixed.pdf")


def test_a_titled_page_keeps_the_title_as_its_evidence_and_the_untitled_page_takes_the_assertion(mixed, tmp_path):
    result = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)

    evidence = {(r.field_name, r.period_role): r.basis_evidence for r in result.field_set.fields if r.status is Status.EXTRACTED and r.origin.value == "source"}
    assert evidence[(F.PROFIT_BEFORE_TAX, CUR)] is E.TITLE and evidence[(F.CURRENT_ASSETS, COMP)] is E.TITLE
    assert evidence[(F.INTEREST_EXPENSE, CUR)] is E.ANALYST_ASSERTION and evidence[(F.TOTAL_EQUITY, COMP)] is E.ANALYST_ASSERTION
    assert result.basis_assertion.applied_pages == (2,)


def test_the_attribute_is_verified_from_the_title_so_the_assertion_changes_nothing_about_it(mixed, tmp_path):
    result = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)

    assert result.attributes.statement_basis.basis_evidence is E.TITLE and result.attributes.statement_basis.page_number == 1


def test_derived_values_are_asserted_when_any_input_is_and_title_when_none_is(mixed, tmp_path):
    from credit_intel.calculations.borrowings import total_borrowings_for
    from credit_intel.calculations.derived import derive_ebit

    result = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)
    fs = result.field_set

    ebit = derive_ebit(None, fs.get(F.PROFIT_BEFORE_TAX, CUR), fs.get(F.INTEREST_EXPENSE, CUR))  # title + assertion
    total = total_borrowings_for(fs, CUR)  # assertion + assertion
    only_titled = derive_ebit(None, fs.get(F.PROFIT_BEFORE_TAX, CUR), fs.get(F.PROFIT_BEFORE_TAX, CUR))  # title + title
    assert ebit.basis_evidence is E.ANALYST_ASSERTION and total.basis_evidence is E.ANALYST_ASSERTION and only_titled.basis_evidence is E.TITLE
    assert total.value == 5_500_000_000


def test_without_the_assertion_the_untitled_page_is_not_accepted_and_the_same_reply_is_served_from_the_cache(mixed, tmp_path):
    run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)

    second = run(mixed, tmp_path, NoCall(), page_range="1-2")  # the gate passes on page 1's title; nothing is asserted

    assert second.stats.cache_hits == 1 and second.stats.llm_calls == 0 and second.basis_assertion is None
    on_page_2 = [r for r in second.field_set.fields if r.page_number == 2]
    assert on_page_2 and {r.status for r in on_page_2} == {Status.REQUIRES_REVIEW} and {r.status_reason for r in on_page_2} == {R.BASIS_UNKNOWN}
    on_page_1 = [r for r in second.field_set.fields if r.page_number == 1]
    assert {r.status for r in on_page_1} == {Status.EXTRACTED} and {r.basis_evidence for r in on_page_1} == {E.TITLE}


def test_an_asserted_basis_never_replaces_a_known_one(mixed, tmp_path):
    second = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)
    page_1 = [r for r in second.field_set.fields if r.page_number == 1]

    assert page_1 and all(r.validation.details["basis"]["read_from"] == "cited_page" for r in page_1)


# --- through the command line and into the output -------------------------------------------------------------------------------------------------------


def test_the_exported_results_mark_each_field_with_its_basis_evidence(untitled, tmp_path):
    config = tmp_path / "settings.toml"
    config.write_text('[llm]\nprovider = "fake"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n', encoding="utf-8")
    ticks = iter(START + timedelta(milliseconds=7 * n) for n in range(10_000))
    out, err = io.StringIO(), io.StringIO()

    code = main([str(untitled), "--pages", "1", "--assert-basis", "consolidated", "--config", str(config)],
                provider_factory=lambda s, e: FakeProvider(script=[untitled_reply(untitled)]), clock=lambda: next(ticks), stdout=out, stderr=err, env={})  # fmt: skip
    data = json.loads((Path(out.getvalue().strip()) / "results.json").read_text(encoding="utf-8"))

    assert code == 0, err.getvalue()
    sourced = [f for f in data["fields"] if f["status"] == "extracted"]
    assert len(sourced) == 6 and {f["basis_evidence"] for f in sourced} == {"analyst_assertion"}
    statement_basis = next(a for a in data["attributes"] if a["attribute"] == "statement_basis")
    assert statement_basis["basis_evidence"] == "analyst_assertion" and statement_basis["page_number"] is None
    assert {a["basis_evidence"] for a in data["attributes"] if a["attribute"] != "statement_basis"} == {None}


def forced(monkeypatch, applied):
    """Make the pipeline use an assertion whose applied pages are not what the pages say, to test the verifier's own guards."""
    from credit_intel.extraction import pipeline
    from credit_intel.extraction.assertion import BasisAssertion

    monkeypatch.setattr(pipeline, "apply_assertion", lambda *a, **k: BasisAssertion(B.CONSOLIDATED, (1, 2), applied))


def test_a_page_the_assertion_was_not_applied_to_is_never_given_the_asserted_basis(mixed, tmp_path, monkeypatch):
    forced(monkeypatch, ())

    result = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)

    on_page_2 = [r for r in result.field_set.fields if r.page_number == 2]
    assert on_page_2 and {r.status_reason for r in on_page_2} == {R.BASIS_UNKNOWN} and {r.basis_evidence for r in on_page_2} == {E.TITLE}


def test_a_page_with_a_known_basis_is_never_overridden_even_if_it_is_listed_as_applied(mixed, tmp_path, monkeypatch):
    forced(monkeypatch, (1, 2))

    result = run(mixed, tmp_path, FakeProvider(script=[mixed_reply(mixed)]), page_range="1-2", assert_basis=B.CONSOLIDATED)

    on_page_1 = [r for r in result.field_set.fields if r.page_number == 1]
    assert on_page_1 and {r.basis_evidence for r in on_page_1} == {E.TITLE} and {r.validation.details["basis"]["read_from"] for r in on_page_1} == {"cited_page"}
