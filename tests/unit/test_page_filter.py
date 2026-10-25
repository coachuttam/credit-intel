"""Removing candidate pages the extraction model does not need, and every fallback (PRD v0.4.31; B-296). Mocked classifiers only."""

import logging
from decimal import Decimal

import pytest

from credit_intel.config import JevSettings
from credit_intel.ingestion.models import CandidatePage, LocatorResult
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.classifier import FakeClassifier
from credit_intel.pagefilter.filter import filter_candidates, other_basis, unavailable_outcome
from credit_intel.pagefilter.labels import ClassifierError, PageBasis, PageClassification, PageType

SETTINGS = JevSettings(enabled=True, threshold=0.85)
CONSOLIDATED = StatementBasis.CONSOLIDATED


def label(page_type=PageType.BALANCE_SHEET, conf=0.95, basis=PageBasis.CONSOLIDATED, basis_conf=0.9, tokens=100, latency=50, cached=False):
    return PageClassification(page_type, conf, basis, basis_conf, "jev-1.14.0", tokens, latency, cached)


def located(*pages, method="keywords"):
    return LocatorResult(method, tuple(CandidatePage(p, ("balance_sheet",) if method == "keywords" else (), 5 if method == "keywords" else None, ()) for p in pages))


def run(script, pages=(1, 2, 3), settings=SETTINGS, basis=CONSOLIDATED, method="keywords", **kw):
    classifier = FakeClassifier(script)
    result, outcome = filter_candidates(located(*pages, method=method), {p: f"text of page {p}" for p in pages}, classifier, settings, basis, **kw)
    return result, outcome, classifier


def kept(result):
    return [c.page_number for c in result.candidates]


# --- what is dropped ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("page_type", [PageType.CASH_FLOW, PageType.OTHER])
def test_a_page_the_classifier_is_sure_the_model_does_not_need_is_dropped(page_type):
    result, outcome, _ = run({1: label(), 2: label(page_type, 0.97), 3: label(PageType.PROFIT_LOSS)})

    assert kept(result) == [1, 3] and outcome.pages_sent == (1, 3) and outcome.pages_dropped == (2,)
    record = outcome.records[1]
    assert (record.decision, record.fallback, record.reason) == ("dropped", False, "page_type")


@pytest.mark.parametrize("page_type", [PageType.BALANCE_SHEET, PageType.PROFIT_LOSS, PageType.NOTES])
def test_a_page_type_the_model_needs_is_kept_even_at_full_confidence(page_type):
    result, outcome, _ = run({1: label(page_type, 1.0), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3] and outcome.pages_dropped == () and outcome.fallbacks == 0


def test_a_page_on_the_other_basis_is_dropped_when_the_classifier_is_sure():
    result, outcome, _ = run({1: label(), 2: label(basis=PageBasis.STANDALONE, basis_conf=0.9), 3: label()})

    assert kept(result) == [1, 3] and outcome.records[1].reason == "basis" and outcome.records[1].decision == "dropped"


def test_a_note_is_kept_whatever_its_basis_and_confidence():
    result, outcome, _ = run({1: label(PageType.NOTES, 0.99, PageBasis.STANDALONE, 0.99), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3] and outcome.records[0].decision == "kept" and not outcome.records[0].fallback


def test_the_other_basis_depends_on_the_configured_one():
    standalone_page = label(basis=PageBasis.STANDALONE, basis_conf=0.95)
    consolidated_page = label(basis=PageBasis.CONSOLIDATED, basis_conf=0.95)

    assert kept(run({1: standalone_page, 2: label(), 3: label()})[0]) == [2, 3]
    assert kept(run({1: standalone_page, 2: standalone_page, 3: label(basis=PageBasis.UNCLEAR)}, basis=StatementBasis.STANDALONE)[0]) == [1, 2, 3]
    assert kept(run({1: consolidated_page, 2: label(basis=PageBasis.STANDALONE), 3: label(basis=PageBasis.UNCLEAR)}, basis=StatementBasis.STANDALONE)[0]) == [2, 3]
    assert other_basis(CONSOLIDATED) is PageBasis.STANDALONE and other_basis(StatementBasis.UNKNOWN) is None


def test_an_unclear_basis_is_never_a_reason_to_drop():
    result, outcome, _ = run({1: label(basis=PageBasis.UNCLEAR, basis_conf=1.0), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3] and outcome.fallbacks == 0


# --- the threshold and the fallback to today's path --------------------------------------------------------------------------


def test_a_label_below_the_threshold_keeps_the_page_and_is_a_fallback():
    result, outcome, _ = run({1: label(PageType.OTHER, 0.84), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3]
    record = outcome.records[0]
    assert (record.decision, record.fallback, record.reason) == ("kept", True, "low_confidence") and outcome.fallbacks == 1


def test_a_label_exactly_at_the_threshold_counts_as_sure():
    result, outcome, _ = run({1: label(PageType.OTHER, 0.85), 2: label(), 3: label()})

    assert kept(result) == [2, 3] and outcome.fallbacks == 0


def test_a_kept_label_with_low_confidence_is_still_a_fallback_because_it_cannot_be_trusted():
    _, outcome, _ = run({1: label(PageType.BALANCE_SHEET, 0.4), 2: label(), 3: label()})

    assert outcome.records[0].fallback and outcome.records[0].reason == "low_confidence"


def test_a_low_confidence_basis_that_would_drop_the_page_keeps_it():
    result, outcome, _ = run({1: label(basis=PageBasis.STANDALONE, basis_conf=0.5), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3] and outcome.records[0].fallback


def test_a_page_dropped_for_its_type_is_not_a_fallback_even_if_the_basis_was_unsure():
    result, outcome, _ = run({1: label(PageType.CASH_FLOW, 0.99, PageBasis.STANDALONE, 0.2), 2: label(), 3: label()})

    assert kept(result) == [2, 3] and not outcome.records[0].fallback


# --- errors never fail the run --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["no_key", "timeout", "connection", "rate_limit", "auth", "bad_request", "server", "invalid_reply", "sdk_error", "error"])
def test_a_classifier_error_keeps_the_page_with_the_reason_word(reason):
    result, outcome, _ = run({1: ClassifierError(reason), 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3]
    record = outcome.records[0]
    assert (record.decision, record.fallback, record.reason, record.model_id) == ("kept", True, reason, None)


@pytest.mark.parametrize("raised", [RuntimeError("boom"), TimeoutError(), KeyError("x"), ValueError("v"), ConnectionError("c")])
def test_any_other_exception_is_treated_the_same_way(raised):
    result, outcome, _ = run({1: raised, 2: label(), 3: label()})

    assert kept(result) == [1, 2, 3] and outcome.records[0].reason == "error"


def test_a_keyboard_interrupt_is_not_swallowed():
    with pytest.raises(KeyboardInterrupt):
        run({1: KeyboardInterrupt(), 2: label(), 3: label()})


def test_every_page_failing_gives_exactly_the_locator_result():
    original = located(1, 2, 3)

    result, outcome = filter_candidates(original, {}, FakeClassifier({}), SETTINGS, CONSOLIDATED)

    assert result.candidates == original.candidates and outcome.pages_dropped == () and not outcome.active


def test_the_breaker_stops_calling_after_the_allowed_failures_in_a_row():
    settings = JevSettings(enabled=True, max_consecutive_failures=2)
    script = {1: ClassifierError("server"), 2: ClassifierError("server"), 3: label(PageType.OTHER, 0.99), 4: label(PageType.OTHER, 0.99)}

    result, outcome, classifier = run(script, pages=(1, 2, 3, 4), settings=settings)

    assert classifier.calls == [1, 2] and kept(result) == [1, 2, 3, 4]
    assert [r.reason for r in outcome.records] == ["server", "server", "breaker_open", "breaker_open"]


def test_a_success_resets_the_count_of_failures():
    settings = JevSettings(enabled=True, max_consecutive_failures=2)
    script = {1: ClassifierError("timeout"), 2: label(), 3: ClassifierError("timeout"), 4: label(PageType.OTHER, 0.99)}

    result, _, classifier = run(script, pages=(1, 2, 3, 4), settings=settings)

    assert classifier.calls == [1, 2, 3, 4] and kept(result) == [1, 2, 3]


def test_the_time_budget_stops_the_calls_and_keeps_the_rest():
    settings = JevSettings(enabled=True, time_budget_seconds=5.0)
    ticks = iter([0.0, 1.0, 6.0, 7.0, 8.0])  # the start, the checks before pages 1 and 2, then past the budget
    script = {1: label(PageType.OTHER, 0.99), 2: label(), 3: label(PageType.OTHER, 0.99)}

    result, outcome, classifier = run(script, settings=settings, clock=lambda: next(ticks))

    assert classifier.calls == [1] and kept(result) == [2, 3]
    assert [r.reason for r in outcome.records] == ["page_type", "budget_spent", "budget_spent"]


def test_a_filter_that_would_leave_nothing_keeps_every_page():
    result, outcome, _ = run({1: label(PageType.OTHER, 0.99), 2: label(PageType.CASH_FLOW, 0.99), 3: label(PageType.OTHER, 0.99)})

    assert kept(result) == [1, 2, 3] and outcome.pages_dropped == ()
    assert all(r.fallback and r.reason == "all_pages_dropped" and r.decision == "kept" for r in outcome.records)


def test_a_page_range_is_never_filtered_and_the_classifier_is_not_called():
    result, outcome, classifier = run({1: label(PageType.OTHER, 0.99)}, method="page_range")

    assert kept(result) == [1, 2, 3] and classifier.calls == [] and outcome.skipped_reason == "page_range" and not outcome.active


def test_the_filter_never_adds_a_page_or_reorders_the_rest():
    original = located(4, 9, 12)

    result, _ = filter_candidates(original, {4: "a", 9: "b", 12: "c"}, FakeClassifier({4: label(), 9: label(PageType.OTHER, 0.99), 12: label()}), SETTINGS, CONSOLIDATED)

    assert [c.page_number for c in result.candidates] == [4, 12] and set(result.candidates) <= set(original.candidates)
    assert result.excluded_candidates == original.excluded_candidates and result.method == original.method


def test_the_locator_result_given_is_not_changed():
    original = located(1, 2, 3)

    filter_candidates(original, {1: "a", 2: "b", 3: "c"}, FakeClassifier({1: label(), 2: label(PageType.OTHER, 0.99), 3: label()}), SETTINGS, CONSOLIDATED)

    assert [c.page_number for c in original.candidates] == [1, 2, 3]


# --- the record --------------------------------------------------------------------------------------------------------------------


def test_the_outcome_counts_calls_tokens_cost_latency_and_models():
    priced = JevSettings(enabled=True, price_input_per_million=Decimal("0.042"))
    script = {1: label(tokens=1000, latency=100), 2: label(PageType.OTHER, 0.99, tokens=2000, latency=200), 3: label(tokens=500, latency=50, cached=True)}

    _, outcome, _ = run(script, settings=priced)

    assert outcome.active and outcome.calls == 2  # a cached answer is not a call
    assert (outcome.input_tokens, outcome.latency_ms, outcome.model_ids) == (3500, 350, ("jev-1.14.0",))
    assert outcome.cost_usd == Decimal("3500") * Decimal("0.042") / Decimal(1_000_000)
    assert outcome.records[0].cost_usd == Decimal("1000") * Decimal("0.042") / Decimal(1_000_000)


def test_without_a_price_no_cost_is_estimated():
    _, outcome, _ = run({1: label(), 2: label(), 3: label()})

    assert outcome.cost_usd is None and all(r.cost_usd is None for r in outcome.records)


def test_the_results_part_has_nothing_that_changes_between_a_run_and_its_replay():
    _, outcome, _ = run({1: label(latency=90), 2: label(PageType.OTHER, 0.99, latency=70), 3: label()}, settings=JevSettings(enabled=True, price_input_per_million=Decimal("0.042")))

    part = outcome.to_results()

    assert part == {"enabled": True, "threshold": 0.85, "requested_model": "jev-latest", "model_ids": ["jev-1.14.0"], "skipped_reason": None,
                    "pages_sent": [1, 3], "pages_dropped": [2]}  # fmt: skip


def test_the_manifest_part_has_one_record_per_page_with_label_confidence_fallback_latency_and_cost():
    _, outcome, _ = run({1: label(latency=90, tokens=10), 2: ClassifierError("timeout"), 3: label(PageType.OTHER, 0.5)}, settings=JevSettings(enabled=True, price_input_per_million=Decimal("0.042")))

    pages = outcome.to_manifest()["pages"]

    assert [p["page"] for p in pages] == [1, 2, 3]
    assert pages[0] | {"estimated_cost_usd": None} == {"page": 1, "decision": "kept", "fallback": False, "reason": None, "page_type": "balance_sheet",
        "type_confidence": 0.95, "basis": "consolidated", "basis_confidence": 0.9, "model_id": "jev-1.14.0", "latency_ms": 90, "input_tokens": 10,
        "estimated_cost_usd": None, "cached": False}  # fmt: skip
    assert pages[1]["reason"] == "timeout" and pages[1]["fallback"] and pages[1]["page_type"] is None
    assert pages[2]["reason"] == "low_confidence" and pages[0]["estimated_cost_usd"] == "0.00000042"


def test_the_log_has_one_line_per_page_and_a_summary_and_no_text(caplog):
    caplog.set_level(logging.INFO, logger="credit_intel.pagefilter")

    run({1: label(), 2: label(PageType.OTHER, 0.99), 3: ClassifierError("server")}, document_tag="abc123def456")

    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 4 and lines[0].startswith("stage=page_classified doc=abc123def456 page=1 type=balance_sheet type_conf=0.950")
    assert "decision=dropped fallback=no reason=page_type" in lines[1] and "decision=kept fallback=yes reason=server" in lines[2]
    assert lines[3].startswith("stage=pages_filtered doc=abc123def456 candidates=3 sent=2 dropped=1 fallbacks=1 calls=2")
    assert "text of page" not in caplog.text


def test_a_classifier_switched_on_but_unavailable_keeps_every_page_and_says_why():
    outcome = unavailable_outcome(SETTINGS, "no_key", (3, 1, 2))

    assert outcome.skipped_reason == "no_key" and not outcome.active and outcome.pages_sent == (3, 1, 2) and outcome.pages_dropped == ()
    assert all(r.fallback and r.reason == "unavailable" for r in outcome.records) and outcome.fallbacks == 3
