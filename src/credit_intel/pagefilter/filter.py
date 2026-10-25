"""Remove the candidate pages the extraction model does not need (PRD v0.4.31).

``filter_candidates`` takes the locator's candidate pages (after the basis gate and the removal of unknown-basis pages)
and asks a classifier about each. It can only remove pages; it never adds one, never changes a page's basis, and never
sets anything that verification uses. A page is removed only when the classifier is confident (at or above the threshold)
that it is a page type the model does not need (cash flow, other) or that it is on the other basis (a note is never removed). Every other case keeps
the page, exactly as without the classifier:

* a label whose confidence is below the threshold (a fallback), or a page type the model needs (balance sheet, profit and
  loss, **notes**: kept because the label says so);
* an error, a timeout, an invalid reply or an unreadable page (the reason is a fixed word);
* the circuit breaker (after ``max_consecutive_failures`` failures in a row the classifier is skipped), the time budget
  of the document, or a classifier that is not available (no key);
* a run with a page range (the analyst chose those pages) and a filter that would remove every page.

The function never raises for a classifier failure. Nothing it logs or records holds a page's text.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal

from credit_intel.config import JevSettings
from credit_intel.ingestion.models import LocatorResult
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.classifier import PageClassifier
from credit_intel.pagefilter.labels import DROPPABLE_TYPES, ClassifierError, PageBasis, PageType

logger = logging.getLogger("credit_intel.pagefilter")

KEPT, DROPPED = "kept", "dropped"
# Why a page was kept without the classifier's say-so (``fallback`` true). ``low_confidence`` and the failure words
# (``labels.FAILURE_REASONS``) are the others.
SKIPPED_REASONS = ("breaker_open", "budget_spent", "unavailable", "all_pages_dropped", "page_range")


@dataclass(frozen=True)
class PageRecord:
    page_number: int
    decision: str  # "kept" or "dropped"
    fallback: bool  # the page is on today's path because the classifier could not be trusted or used
    reason: str | None  # why it is a fallback, or why a page was dropped ("page_type" or "basis")
    page_type: str | None
    type_confidence: float | None
    basis: str | None
    basis_confidence: float | None
    model_id: str | None
    latency_ms: int
    input_tokens: int
    cost_usd: Decimal | None
    cached: bool


@dataclass(frozen=True)
class PageFilterOutcome:
    """What the classifier step did in one run. ``results.json`` gets the deterministic part (``to_results``); the manifest gets all of it."""

    active: bool  # the classifier was asked about at least one page
    skipped_reason: str | None  # why it was not used at all, if it was not
    threshold: float
    requested_model: str
    model_ids: tuple[str, ...]  # the versioned IDs that answered
    records: tuple[PageRecord, ...]
    pages_sent: tuple[int, ...]
    pages_dropped: tuple[int, ...]
    calls: int
    fallbacks: int
    input_tokens: int
    cost_usd: Decimal | None
    latency_ms: int

    def to_results(self) -> dict:
        """The part that is the same on a replay: no latency, no cost, no per-call numbers."""
        return {
            "enabled": True,
            "threshold": self.threshold,
            "requested_model": self.requested_model,
            "model_ids": list(self.model_ids),
            "skipped_reason": self.skipped_reason,
            "pages_sent": list(self.pages_sent),
            "pages_dropped": list(self.pages_dropped),
        }

    def to_manifest(self) -> dict:
        return {
            **self.to_results(),
            "calls": self.calls,
            "fallbacks": self.fallbacks,
            "input_tokens": self.input_tokens,
            "estimated_cost_usd": _plain(self.cost_usd),
            "latency_ms": self.latency_ms,
            "pages": [
                {
                    "page": r.page_number, "decision": r.decision, "fallback": r.fallback, "reason": r.reason,
                    "page_type": r.page_type, "type_confidence": r.type_confidence,
                    "basis": r.basis, "basis_confidence": r.basis_confidence,
                    "model_id": r.model_id, "latency_ms": r.latency_ms, "input_tokens": r.input_tokens,
                    "estimated_cost_usd": _plain(r.cost_usd), "cached": r.cached,
                }
                for r in self.records
            ],  # fmt: skip
        }


def _plain(amount: Decimal | None) -> str | None:
    """A cost in plain decimal notation (no exponent), for the manifest."""
    return None if amount is None else format(amount, "f")


def _cost(tokens: int, price: Decimal | None) -> Decimal | None:
    return None if price is None else Decimal(tokens) * price / Decimal(1_000_000)


def _skipped_record(page: int, reason: str) -> PageRecord:
    return PageRecord(page, KEPT, True, reason, None, None, None, None, None, 0, 0, None, False)


def other_basis(configured: StatementBasis) -> PageBasis | None:
    if configured is StatementBasis.CONSOLIDATED:
        return PageBasis.STANDALONE
    if configured is StatementBasis.STANDALONE:
        return PageBasis.CONSOLIDATED
    return None


@dataclass(frozen=True)
class PageFilterSetup:
    """What a run is given when the optional step is switched on: its settings and the classifier, or why there is none."""

    settings: JevSettings
    classifier: PageClassifier | None
    unavailable_reason: str | None = None
    # For the evaluation only: also filter a page range, to measure what the classifier would remove from the analyst's pages. The
    # command never sets it; an analyst's pages are not filtered (v0.4.31).
    filter_page_ranges: bool = False


def unavailable_outcome(settings: JevSettings, reason: str, pages: tuple[int, ...]) -> PageFilterOutcome:
    """The record of a run where the classifier was switched on but could not be used (for example no key)."""
    records = tuple(_skipped_record(p, "unavailable") for p in pages)
    return PageFilterOutcome(False, reason, settings.threshold, settings.model, (), records, pages, (), 0, len(records), 0, None, 0)


def filter_candidates(
    located: LocatorResult,
    page_texts: Mapping[int, str],
    classifier: PageClassifier,
    settings: JevSettings,
    configured_basis: StatementBasis,
    *,
    document_tag: str = "-",
    clock: Callable[[], float] = time.monotonic,
    filter_page_ranges: bool = False,
) -> tuple[LocatorResult, PageFilterOutcome]:
    """The locator result without the pages the classifier confidently says are not needed, and a record of what happened."""
    pages = tuple(sorted(c.page_number for c in located.candidates))
    if (located.method != "keywords" and not filter_page_ranges) or not pages:  # the analyst's pages are never filtered
        outcome = PageFilterOutcome(False, "page_range", settings.threshold, settings.model, (), (), pages, (), 0, 0, 0, None, 0)
        return located, outcome
    started = clock()
    avoid = other_basis(configured_basis)
    failures = 0
    records: list[PageRecord] = []
    for page in pages:
        if failures >= settings.max_consecutive_failures:
            records.append(_skipped_record(page, "breaker_open"))
            continue
        if clock() - started >= settings.time_budget_seconds:
            records.append(_skipped_record(page, "budget_spent"))
            continue
        try:
            label = classifier.classify(page, page_texts.get(page, ""))
        except ClassifierError as error:
            failures += 1
            records.append(_skipped_record(page, error.reason))
            continue
        except Exception:  # the pipeline never fails because of the classifier, whatever it raises
            failures += 1
            records.append(_skipped_record(page, "error"))
            continue
        failures = 0
        type_sure = label.type_confidence >= settings.threshold
        basis_sure = label.basis_confidence >= settings.threshold
        drop_for = None
        if label.page_type in DROPPABLE_TYPES and type_sure:
            drop_for = "page_type"
        elif avoid is not None and label.basis is avoid and basis_sure and label.page_type is not PageType.NOTES:
            drop_for = "basis"  # a note is never dropped: interest expense and borrowings often sit in one
        low = not type_sure or (avoid is not None and label.basis is avoid and not basis_sure)  # the label cannot be trusted: today's path
        records.append(
            PageRecord(
                page, DROPPED if drop_for else KEPT, bool(low and not drop_for), "low_confidence" if low and not drop_for else drop_for,
                label.page_type.value, label.type_confidence, label.basis.value, label.basis_confidence, label.model_id,
                label.latency_ms, label.input_tokens, _cost(label.input_tokens, settings.price_input_per_million), label.cached,
            )
        )  # fmt: skip
    if all(r.decision == DROPPED for r in records):  # a filter that leaves nothing is no filter
        records = [replace(r, decision=KEPT, fallback=True, reason="all_pages_dropped") for r in records]
    sent = tuple(r.page_number for r in records if r.decision == KEPT)
    dropped = tuple(r.page_number for r in records if r.decision == DROPPED)
    kept = tuple(c for c in located.candidates if c.page_number in sent)
    total_tokens = sum(r.input_tokens for r in records)
    costs = [r.cost_usd for r in records if r.cost_usd is not None]
    outcome = PageFilterOutcome(
        active=any(r.model_id is not None for r in records),
        skipped_reason=None,
        threshold=settings.threshold,
        requested_model=settings.model,
        model_ids=tuple(sorted({r.model_id for r in records if r.model_id})),
        records=tuple(records),
        pages_sent=sent,
        pages_dropped=dropped,
        calls=sum(1 for r in records if r.model_id is not None and not r.cached),
        fallbacks=sum(1 for r in records if r.fallback),
        input_tokens=total_tokens,
        cost_usd=sum(costs, Decimal(0)) if settings.price_input_per_million is not None else None,
        latency_ms=sum(r.latency_ms for r in records),
    )
    for r in records:
        logger.info(
            "stage=page_classified doc=%s page=%d type=%s type_conf=%s basis=%s basis_conf=%s decision=%s fallback=%s reason=%s ms=%d jev_tokens=%d jev_cost_usd=%s cached=%s",
            document_tag, r.page_number, r.page_type or "-", "-" if r.type_confidence is None else f"{r.type_confidence:.3f}",
            r.basis or "-", "-" if r.basis_confidence is None else f"{r.basis_confidence:.3f}", r.decision,
            "yes" if r.fallback else "no", r.reason or "-", r.latency_ms, r.input_tokens,
            "-" if r.cost_usd is None else r.cost_usd, "yes" if r.cached else "no",
        )  # fmt: skip
    logger.info(
        "stage=pages_filtered doc=%s candidates=%d sent=%d dropped=%d fallbacks=%d calls=%d jev_tokens=%d jev_cost_usd=%s ms=%d models=%s",
        document_tag, len(pages), len(sent), len(dropped), outcome.fallbacks, outcome.calls, total_tokens,
        "-" if outcome.cost_usd is None else outcome.cost_usd, outcome.latency_ms, ",".join(outcome.model_ids) or "-",
    )  # fmt: skip
    return replace(located, candidates=kept), outcome
