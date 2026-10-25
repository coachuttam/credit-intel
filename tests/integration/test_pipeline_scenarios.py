"""End-to-end scenarios for the offline pipeline (Phase 2 step 9b; B-223).

Synthetic PDFs and a scripted fake provider. Appendix B Examples 1 to 3 and B.6 rows 9, 10
and 14 run through ingestion, location, the model call, verification and the field set.
"""

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

import pipeline_fixture as fx
from credit_intel.config import CONSOLIDATED, LocatorSettings
from credit_intel.extraction.pipeline import ExtractionRun, run_extraction
from credit_intel.extraction.prompt import Prompt, load_prompt
from credit_intel.ingestion.errors import ErrorCode, IngestionError, InvalidOutputError
from credit_intel.llm.errors import LLMTransientError
from credit_intel.llm.provider import FakeProvider
from credit_intel.llm.retry import RetryingProvider
from credit_intel.models import FieldName, PeriodRole, StatementBasis, Status, StatusReason as R

CUR, COMP = PeriodRole.CURRENT, PeriodRole.COMPARATIVE
GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "pipeline_field_set_golden.json"
WITH_PROFIT = fx.ROWS + [("Profit/(loss) for the year", "", "(245.10)", "312.40")]


def run(pdf, tmp_path, replies, **kw) -> tuple[ExtractionRun, FakeProvider]:
    provider = FakeProvider(script=list(replies))
    kw.setdefault("cache_dir", tmp_path / "cache")
    return run_extraction(pdf, provider, kw.pop("llm", fx.LLM), **kw), provider


def serialise(result: ExtractionRun) -> str:
    """The serialised field set, as a test-side stand-in for results.json (Phase 5)."""
    return json.dumps(
        {
            "fields": [r.model_dump(mode="json") for r in result.field_set.fields],
            "counts": result.field_set.counts,
            "ignored": [r.field_id for r in result.field_set.ignored],
            "bases_present": list(result.field_set.bases_present),
        },
        sort_keys=True, indent=2, ensure_ascii=True,
    ) + "\n"  # fmt: skip


def fields_of(pdf, extra=()):
    return json.loads(fx.good_response(pdf))["fields"] + list(extra)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf", rows=WITH_PROFIT)


def status(result, name, role):
    return result.field_set.get(name, role)


# --- the model's mistakes (Appendix B Examples 1 to 3) --------------------------------------------------------


def test_a_clean_reply_is_accepted_in_full(pdf, tmp_path):
    result, _ = run(pdf, tmp_path, [fx.good_response(pdf)])

    assert result.field_set.counts["extracted"] == 6 and result.field_set.counts["requires_review"] == 0


def test_example_1_the_comparative_figure_returned_for_the_current_period_is_rejected(pdf, tmp_path):
    wrong = fx.field(pdf, "current_assets", "current", "1,356.75", "Total current assets")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), [wrong] + fields_of(pdf)[1:])])

    record = status(result, FieldName.CURRENT_ASSETS, CUR)
    assert record.status is Status.REQUIRES_REVIEW and record.status_reason is R.PERIOD_NOT_VERIFIED
    assert status(result, FieldName.CURRENT_ASSETS, COMP).status is Status.EXTRACTED


def test_example_1_the_note_reference_returned_as_the_value_is_rejected(pdf, tmp_path):
    wrong = fx.field(pdf, "current_assets", "current", "14", "Total current assets")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), [wrong] + fields_of(pdf)[1:])])

    assert status(result, FieldName.CURRENT_ASSETS, CUR).status_reason is R.PERIOD_NOT_VERIFIED


def test_example_2_a_bracketed_figure_returned_without_its_brackets_is_a_sign_mismatch(pdf, tmp_path):
    wrong = fx.field(pdf, "net_profit", "current", "245.10", "Profit/(loss) for the year")
    right = fx.field(pdf, "net_profit", "comparative", "312.40", "Profit/(loss) for the year")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), fields_of(pdf, [wrong, right]))])

    assert status(result, FieldName.NET_PROFIT, CUR).status_reason is R.SIGN_MISMATCH
    assert status(result, FieldName.NET_PROFIT, COMP).status is Status.EXTRACTED


def test_example_2_the_bracketed_figure_is_a_negative_value(pdf, tmp_path):
    good = fx.field(pdf, "net_profit", "current", "(245.10)", "Profit/(loss) for the year")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), fields_of(pdf, [good]))])

    record = status(result, FieldName.NET_PROFIT, CUR)
    assert record.status is Status.EXTRACTED and record.value == Decimal("-2451000000")  # a loss is valid


def test_example_3_a_scale_the_page_does_not_declare_is_not_verified(pdf, tmp_path):
    wrong = fx.field(pdf, "total_equity", "current", "600.00", "Total equity", scale="lakh")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), [*fields_of(pdf)[:4], wrong, fields_of(pdf)[5]])])

    assert status(result, FieldName.TOTAL_EQUITY, CUR).status_reason is R.SCALE_NOT_VERIFIED


def test_a_label_of_another_field_is_not_recognised(pdf, tmp_path):
    wrong = fx.field(pdf, "revenue", "current", "2,282.30", "Total assets", label="Total assets")

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), fields_of(pdf, [wrong]))])

    assert status(result, FieldName.REVENUE, CUR).status_reason is R.LABEL_NOT_RECOGNISED


def test_a_quote_that_is_not_on_the_page_is_not_verified(pdf, tmp_path):
    wrong = fx.field(pdf, "total_equity", "current", "600.00", "Total equity")
    wrong["evidence_quote"] = "Total equity 999.99 999.99"

    result, _ = run(pdf, tmp_path, [fx.reply(fx.good_attributes(pdf), [*fields_of(pdf)[:4], wrong, fields_of(pdf)[5]])])

    assert status(result, FieldName.TOTAL_EQUITY, CUR).status_reason is R.EVIDENCE_NOT_VERIFIED


def test_a_missing_currency_attribute_blocks_every_field(pdf, tmp_path):
    reply = fx.reply(fx.good_attributes(pdf, drop=("reporting_currency",)), fields_of(pdf))

    result, _ = run(pdf, tmp_path, [reply])

    assert result.field_set.counts["extracted"] == 0 and result.field_set.counts["requires_review"] == 6
    assert all(r.status_reason is R.CURRENCY_NOT_VERIFIED for r in result.field_set.fields if r.status is Status.REQUIRES_REVIEW)


def test_an_empty_reply_is_not_a_failure_everything_is_not_found(pdf, tmp_path):
    result, _ = run(pdf, tmp_path, [fx.reply([], [])])  # FR-011.5: partial extraction does not fail the run

    assert result.field_set.fields == () or result.field_set.counts["not_found"] == len(result.field_set.fields)
    assert result.attributes.current_period_end.status is Status.NOT_FOUND


# --- invalid output and the corrective retry (FR-004.1) ---------------------------------------------------------------


def test_invalid_output_gets_one_corrective_retry(pdf, tmp_path):
    result, provider = run(pdf, tmp_path, ["not json", fx.good_response(pdf)])

    assert result.extraction.attempts == 2 and result.stats.llm_calls == 2
    assert result.field_set.counts["extracted"] == 6
    assert "rejected" in provider.calls[1].user and provider.calls[1].user.startswith(provider.calls[0].user)


def test_a_reply_naming_the_derived_field_is_invalid_and_retried(pdf, tmp_path):
    bad = json.loads(fx.good_response(pdf))
    bad["fields"][0]["field_name"] = "ebit"

    result, _ = run(pdf, tmp_path, [json.dumps(bad), fx.good_response(pdf)])

    assert result.extraction.attempts == 2


def test_two_invalid_replies_fail_the_run_with_the_raw_reply_attached(pdf, tmp_path):
    provider = FakeProvider(script=["first bad", "second bad", fx.good_response(pdf)])

    with pytest.raises(InvalidOutputError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.LLM_INVALID_OUTPUT and excinfo.value.raw_response == "second bad"
    assert len(provider.calls) == 2


def test_an_invalid_first_reply_is_not_cached_but_the_corrected_one_is(pdf, tmp_path):
    first, _ = run(pdf, tmp_path, ["not json", fx.good_response(pdf)])
    second, provider = run(pdf, tmp_path, ["not json"])  # the first call is repeated, the retry is a hit

    assert len(provider.calls) == 1 and second.stats.cache_hits == 1
    assert second.field_set == first.field_set


def test_the_ceiling_can_stop_the_retry(pdf, tmp_path):
    small = replace(fx.LLM, token_ceiling=7000)  # the first call (about 5,400 reserved) fits; the second (about 9,500) does not
    provider = FakeProvider(script=["not json", fx.good_response(pdf)])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, small, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.LLM_BUDGET_EXCEEDED and len(provider.calls) == 1


# --- a page range (FR-013) -----------------------------------------------------------------------------------------------


def test_a_page_range_on_the_statement_page_works_like_the_locator(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "two.pdf", narrative_page="Directors report")

    result, _ = run(pdf, tmp_path, [fx.good_response(pdf)], page_range="1")

    assert result.located.method == "page_range" and result.field_set.counts["extracted"] == 6


def test_a_page_range_on_a_page_with_no_statement_title_stops_before_any_call(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "two.pdf", narrative_page="Directors report")
    provider = FakeProvider(script=[fx.good_response(pdf)])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, page_range="2", cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE and provider.calls == []


def test_a_page_range_outside_the_document_is_refused(pdf, tmp_path):
    provider = FakeProvider(script=[fx.good_response(pdf)])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, page_range="5", cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.PAGE_RANGE and provider.calls == []


# --- two bases in one document (D-06, B.6 rows 9 and 10) --------------------------------------------------------------------


@pytest.fixture
def both(tmp_path):
    pdf = fx.two_basis_pdf(tmp_path / "statement.pdf")
    reply = fx.reply(fx.good_attributes(pdf), fields_of(pdf, fx.standalone_fields(pdf)))
    return pdf, reply


def test_the_consolidated_run_uses_page_one_and_sets_the_standalone_fields_aside(both, tmp_path):
    pdf, reply = both

    result, _ = run(pdf, tmp_path, [reply])

    assert result.field_set.get(FieldName.CURRENT_ASSETS, CUR).raw_value == "1,482.30"
    assert result.field_set.get(FieldName.CURRENT_ASSETS, CUR).field_id == "current_assets.2025-03-31.consolidated"
    assert len(result.field_set.ignored) == 4 and result.field_set.bases_present == ("consolidated", "standalone")
    assert result.attribute_basis_differs is False


def test_b6_row_10_the_same_document_with_the_standalone_basis_uses_page_two(both, tmp_path):
    pdf, reply = both

    result, _ = run(pdf, tmp_path, [reply], basis=StatementBasis.STANDALONE)

    record = result.field_set.get(FieldName.CURRENT_ASSETS, CUR)
    assert record.raw_value == "1,000.00" and record.field_id == "current_assets.2025-03-31.standalone"
    assert record.value == Decimal("10000000000")
    assert len(result.field_set.ignored) == 6
    assert result.attribute_basis_differs is True  # the model read consolidated; nothing is blocked
    assert result.field_set.counts["extracted"] == 4


def test_a_document_with_only_a_standalone_statement_runs_with_the_standalone_basis(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf", title="Standalone Balance Sheet")
    reply = fx.good_response(pdf).replace("Consolidated", "Standalone").replace("consolidated", "standalone")

    result, _ = run(pdf, tmp_path, [reply], basis=StatementBasis.STANDALONE)

    assert result.field_set.counts["extracted"] == 6 and result.attribute_basis_differs is False
    assert result.field_set.get(FieldName.TOTAL_EQUITY, CUR).field_id == "total_equity.2025-03-31.standalone"


def test_configured_locator_settings_reach_every_stage(tmp_path):
    settings = LocatorSettings(
        title_prefix_words=("consolidated", "standalone", "separate", "group"),
        basis_phrases={CONSOLIDATED: ("consolidated", "group"), "standalone": ("standalone", "separate")},
    )
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf", title="Group Balance Sheet")
    reply = fx.good_response(pdf).replace("Consolidated Balance Sheet", "Group Balance Sheet").replace('"Consolidated"', '"Group"')

    result, _ = run(pdf, tmp_path, [reply], locator_settings=settings)

    assert result.field_set.counts["extracted"] == 6
    assert result.field_set.get(FieldName.TOTAL_EQUITY, CUR).field_id.endswith(".consolidated")


def test_the_two_bases_are_never_reconciled_into_a_conflict(both, tmp_path):
    pdf, reply = both

    for basis in (StatementBasis.CONSOLIDATED, StatementBasis.STANDALONE):
        result, _ = run(pdf, tmp_path, [reply], basis=basis, cache_dir=tmp_path / f"c-{basis.value}")
        assert result.field_set.counts["conflicting"] == 0


# --- the cache key (FR-003.5) -----------------------------------------------------------------------------------------------


def test_the_cache_is_written_to_the_directory_given(pdf, tmp_path):
    target = tmp_path / "my-cache"

    run(pdf, tmp_path, [fx.good_response(pdf)], cache_dir=target)

    assert len(list(target.glob("*.json"))) == 1


def test_a_changed_prompt_version_model_or_output_limit_is_a_cache_miss(pdf, tmp_path):
    reply = fx.good_response(pdf)
    run(pdf, tmp_path, [reply])

    other_prompt = Prompt(version="extraction-v3", system=load_prompt().system)  # any version but the default
    _, p1 = run(pdf, tmp_path, [reply], prompt=other_prompt)
    _, p2 = run(pdf, tmp_path, [reply], llm=replace(fx.LLM, model_id="other-model"))
    _, p3 = run(pdf, tmp_path, [reply], llm=replace(fx.LLM, max_output_tokens=1000))
    _, p4 = run(pdf, tmp_path, [reply])  # unchanged: a hit

    assert [len(p.calls) for p in (p1, p2, p3, p4)] == [1, 1, 1, 0]


def test_different_candidate_pages_or_a_different_document_are_cache_misses(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "two.pdf", narrative_page="The company reported 1,482.30 crore")
    other = fx.balance_sheet_pdf(tmp_path / "other.pdf", rows=fx.ROWS[:4] + [("Total current liabilities", "15", "901.00", "850.00")])
    reply = fx.good_response(pdf)
    run(pdf, tmp_path, [reply], page_range="1")

    _, wider = run(pdf, tmp_path, [reply], page_range="1-2")
    _, same = run(pdf, tmp_path, [reply], page_range="1")
    _, changed = run(other, tmp_path, [fx.good_response(other)])

    assert [len(p.calls) for p in (wider, same, changed)] == [1, 0, 1]


# --- reproducibility (FR-012.2) ------------------------------------------------------------------------------------------------


def test_two_fresh_caches_give_identical_serialised_results(pdf, tmp_path):
    first, _ = run(pdf, tmp_path, [fx.good_response(pdf)], cache_dir=tmp_path / "a")
    second, _ = run(pdf, tmp_path, [fx.good_response(pdf)], cache_dir=tmp_path / "b")

    assert serialise(first) == serialise(second)


def test_a_cache_hit_gives_the_same_serialised_result_as_the_first_run(pdf, tmp_path):
    first, _ = run(pdf, tmp_path, [fx.good_response(pdf)])
    second, provider = run(pdf, tmp_path, [])

    assert provider.calls == [] and serialise(first) == serialise(second)


CHILD = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[4])\n"
    "import test_pipeline_scenarios as t\n"
    "import pipeline_fixture as fx\n"
    "from credit_intel.extraction.pipeline import run_extraction\n"
    "from credit_intel.llm.provider import FakeProvider\n"
    "provider = FakeProvider(script=[Path(sys.argv[2]).read_text(encoding='utf-8')])\n"
    "result = run_extraction(Path(sys.argv[1]), provider, fx.LLM, cache_dir=Path(sys.argv[3]))\n"
    "sys.stdout.buffer.write(t.serialise(result).encode('ascii'))\n"
)


def test_a_fresh_process_gives_the_golden_serialised_result(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "statement.pdf", rows=WITH_PROFIT)
    reply = tmp_path / "reply.json"
    reply.write_text(fx.good_response(pdf), encoding="utf-8")
    here = str(Path(__file__).resolve().parent)

    done = subprocess.run(
        [sys.executable, "-I", "-c", CHILD, str(pdf), str(reply), str(tmp_path / "cache"), here],
        capture_output=True, timeout=180, check=False,
    )  # fmt: skip

    assert done.returncode == 0, done.stderr.decode(errors="replace")
    assert done.stdout == GOLDEN.read_bytes()


def test_the_golden_result_has_extracted_and_not_found_fields_and_no_run_identifiers():
    data = json.loads(GOLDEN.read_bytes())
    text = GOLDEN.read_text(encoding="utf-8")

    assert data["counts"]["extracted"] == 6 and data["counts"]["not_found"] == 18
    assert len(data["fields"]) == 24 and data["ignored"] == [] and data["bases_present"] == ["consolidated"]
    assert "run_id" not in text and "timestamp" not in text


# --- transient provider failures (FR-011.3) -----------------------------------------------------------------------------


class FailsThenAnswers:
    def __init__(self, failures, inner):
        self.failures, self.inner = failures, inner

    def complete(self, request):
        if self.failures:
            self.failures -= 1
            raise LLMTransientError("HTTP 503")
        return self.inner.complete(request)


def test_transient_failures_are_retried_and_the_run_succeeds_and_counts_them(pdf, tmp_path):
    inner = FakeProvider(script=[fx.good_response(pdf)])
    provider = RetryingProvider(FailsThenAnswers(2, inner), sleep=lambda _: None)

    result = run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "c")

    assert result.field_set.counts["extracted"] == 6
    assert result.stats.llm_calls == 1 and result.stats.llm_retries == 2 and len(inner.calls) == 1


def test_a_provider_that_stays_down_fails_the_run_with_the_catalogued_code(pdf, tmp_path, caplog):
    inner = FakeProvider(script=[fx.good_response(pdf)])
    provider = RetryingProvider(FailsThenAnswers(9, inner), sleep=lambda _: None)

    with caplog.at_level("INFO"), pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.LLM_UNAVAILABLE and inner.calls == []
    last = [r.getMessage() for r in caplog.records if r.name == "credit_intel.pipeline"][-1]
    assert "after=fields_extracted" in last and "code=E-LLM-UNAVAILABLE" in last
    assert not list((tmp_path / "c").glob("*.json"))


def test_a_run_without_a_retrying_provider_reports_no_retries(pdf, tmp_path):
    result, _ = run(pdf, tmp_path, [fx.good_response(pdf)])

    assert result.stats.llm_retries == 0


# --- pages of unknown basis are not sent (H.4.6, v0.4.21; B-235) ----------------------------------------------------------


def untitled_then_consolidated(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "mixed.pdf"
    pdf = canvas.Canvas(str(path), invariant=1)
    fx._statement_page(pdf, fx.STANDALONE_ROWS, "Balance Sheet", "(Rs. in crore)")  # a title that names no basis
    fx._statement_page(pdf, fx.ROWS, "Consolidated Balance Sheet", "(Rs. in crore)")
    pdf.save()
    return path


def test_b6_row_27_the_untitled_page_is_not_sent_and_is_recorded(tmp_path):
    pdf = untitled_then_consolidated(tmp_path)

    result, provider = run(pdf, tmp_path, [fx.reply([], [])])

    sent = provider.calls[0].user
    assert "=== PAGE 2 ===" in sent and "=== PAGE 1 ===" not in sent
    assert [c.page_number for c in result.located.candidates] == [2]
    assert [(e.page_number, e.reason) for e in result.located.excluded_candidates] == [(1, "basis_unknown")]


def test_b6_row_31_a_page_range_run_sends_the_untitled_page_too(tmp_path):
    pdf = untitled_then_consolidated(tmp_path)

    result, provider = run(pdf, tmp_path, [fx.reply([], [])], page_range="1-2")

    assert "=== PAGE 1 ===" in provider.calls[0].user and "=== PAGE 2 ===" in provider.calls[0].user
    assert result.located.excluded_candidates == ()


def test_b6_row_28_only_untitled_pages_stop_at_the_gate_before_any_call(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "untitled.pdf", title="Balance Sheet")
    provider = FakeProvider(script=[fx.reply([], [])])

    with pytest.raises(IngestionError) as excinfo:
        run_extraction(pdf, provider, fx.LLM, cache_dir=tmp_path / "c")

    assert excinfo.value.code is ErrorCode.BASIS_UNAVAILABLE and provider.calls == []


def test_a_page_of_the_other_known_basis_is_still_sent(both, tmp_path):
    pdf, reply = both

    result, provider = run(pdf, tmp_path, [reply])

    assert "=== PAGE 1 ===" in provider.calls[0].user and "=== PAGE 2 ===" in provider.calls[0].user
    assert result.located.excluded_candidates == ()


# --- the code derives the comparative period end (FR-005.9, v0.4.22; B-237) -------------------------------------------------------


def year_heading_reply(pdf, comparative=None):
    reply = json.loads(fx.good_response(pdf, drop_attributes=("period_end",)))
    quote = "As at March 31,\n2025 2024"  # the date wraps over the title line and the year headings
    reply["attributes"].append(fx.attribute(pdf, "period_end", "March 31, 2025", "2025-03-31", quote, "current"))
    if comparative:
        reply["attributes"].append(comparative)
    return json.dumps(reply)


def test_b6_row_34_a_reply_with_no_comparative_period_still_places_the_comparative_fields(tmp_path):
    pdf = fx.year_heading_pdf(tmp_path / "years.pdf")

    result, _ = run(pdf, tmp_path, [year_heading_reply(pdf)])

    assert result.field_set.counts["extracted"] == 6 and result.field_set.unplaced == ()
    comparative = result.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.COMPARATIVE)
    assert comparative.raw_value == "1,356.75" and comparative.period_end.isoformat() == "2024-03-31"
    assert comparative.validation.details["period"]["evidence"]["method"] == "derived_comparative"
    assert result.attributes.comparative_period_end.raw_text == "2024"


def test_a_comparative_the_model_proposes_and_gets_wrong_does_not_stop_the_derived_one(tmp_path):
    pdf = fx.year_heading_pdf(tmp_path / "years.pdf")
    wrong = fx.attribute(pdf, "period_end", "2024", "2024-03-31", "A heading that is not on the page", "comparative")

    result, _ = run(pdf, tmp_path, [year_heading_reply(pdf, wrong)])

    assert result.field_set.counts["extracted"] == 6


def test_a_page_with_full_date_headings_and_no_year_headings_derives_nothing(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "dates.pdf")
    reply = fx.good_response(pdf, drop_attributes=())
    reply = json.loads(reply)
    reply["attributes"] = [a for a in reply["attributes"] if a.get("period_role") != "comparative"]

    result, _ = run(pdf, tmp_path, [json.dumps(reply)])

    assert result.attributes.comparative_period_end.status is Status.NOT_FOUND
    assert result.field_set.counts["extracted"] == 3  # the current-period fields only


# --- older year-columns (PRD v0.4.29, FR-005.9; Appendix B.6 rows 62 and 63) ------------------------------------------------


def three_year_reply(pdf):
    reply = json.loads(fx.good_response(pdf, drop_attributes=("period_end",)))
    quote = "As at March 31,\n2026 2025 2024"
    reply["attributes"].append(fx.attribute(pdf, "period_end", "March 31, 2026", "2026-03-31", quote, "current"))
    for entry in reply["fields"]:
        entry["evidence_quote"] = fx.line_of(pdf, entry["line_item_label"])
    return json.dumps(reply)


def test_b6_row_62_a_three_year_statement_places_the_current_and_the_comparative_figures(tmp_path):
    pdf = fx.three_year_pdf(tmp_path / "three.pdf")

    result, _ = run(pdf, tmp_path, [three_year_reply(pdf)])

    assert result.field_set.counts["extracted"] == 6 and result.field_set.unplaced == ()
    current = result.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.CURRENT)
    comparative = result.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.COMPARATIVE)
    assert (current.raw_value, current.period_end.isoformat()) == ("1,482.30", "2026-03-31")
    assert (comparative.raw_value, comparative.period_end.isoformat()) == ("1,356.75", "2025-03-31")


def test_b6_row_62_the_older_column_is_never_taken_as_a_figure_of_either_period(tmp_path):
    pdf = fx.three_year_pdf(tmp_path / "three.pdf")
    reply = json.loads(three_year_reply(pdf))
    reply["fields"][0]["raw_value"] = "111.11"  # the older column's figure, claimed as the current period's

    result, _ = run(pdf, tmp_path, [json.dumps(reply)])

    assert result.field_set.get(FieldName.CURRENT_ASSETS, PeriodRole.CURRENT).status is Status.REQUIRES_REVIEW
    assert result.field_set.counts["extracted"] == 5


def test_b6_row_63_a_gap_in_the_headers_makes_the_whole_page_unplaceable_as_before(tmp_path):
    pdf = fx.three_year_pdf(tmp_path / "gap.pdf", headers=("2026", "2025", "2023"))

    result, _ = run(pdf, tmp_path, [three_year_reply(pdf)])

    assert result.field_set.counts["extracted"] == 0
    reviewed = [f for f in result.field_set.fields if f.status is Status.REQUIRES_REVIEW]
    assert reviewed and {f.status_reason for f in reviewed} <= {R.PERIOD_NOT_VERIFIED, R.PERIOD_MISMATCH}
    assert not [f for f in result.field_set.fields if f.status is Status.EXTRACTED]
