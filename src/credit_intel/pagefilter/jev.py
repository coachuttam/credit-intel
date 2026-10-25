"""The Jev (TypeSafe AI) page classifier (PRD v0.4.31).

Jev answers typed questions about a "state". Two Choice questions are put about one page, in one call: its type and
the basis its heading names. The reply gives each question's chosen option, its confidence (0 to 1, from the option
probabilities) and the full probabilities. Jev is never asked for a figure, a date or a currency: it is documented as
weak at numbers, and nothing here reads a number from it.

The state is the top of the page (the title block and the first rows), not the whole page, because accuracy falls as
irrelevant detail grows (the docs' "context rot") and the type and the basis are named by the headings. One page per call keeps
every call far under the 32k-token per-question limit; a page that is over it gets HTTP 400 and falls back.

The SDK is imported when the first call is made, so a run with ``USE_JEV`` off never imports it. The key is read from the
environment only and passed to the client explicitly; it is never logged or stored. Every failure is reduced to a fixed
reason word (``ClassifierError``) and carries no text.
"""

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from credit_intel.config import JevSettings, typesafe_api_key
from credit_intel.pagefilter.cache import DEFAULT_JEV_CACHE_DIR, JevCache, cache_key
from credit_intel.pagefilter.labels import ClassifierError, PageBasis, PageClassification, PageType

QUESTIONS_VERSION = "pagefilter-1"  # a change to a question or an option description is a new version, so a new cache key
TYPE_QUESTION = "page_type"
BASIS_QUESTION = "basis"

TYPE_INSTRUCTIONS = (
    "Which kind of page of an annual report is this? Judge only by the headings and the row labels near the top of the page."
)
TYPE_OPTIONS: dict[PageType, str] = {
    PageType.BALANCE_SHEET: "A balance sheet or statement of financial position: assets, liabilities and equity at one date.",
    PageType.PROFIT_LOSS: "An income statement or statement of profit and loss: revenue, expenses and profit for a period.",
    PageType.CASH_FLOW: "A statement of cash flows.",
    PageType.NOTES: "Notes to the financial statements, a schedule, or a detailed breakdown of one line of a statement.",
    PageType.OTHER: "Anything else: narrative, a cover or contents page, a directors' or auditor's report, a statement of changes in equity or of comprehensive income.",
}
BASIS_INSTRUCTIONS = "Does the heading of this page say whether the statements are consolidated or standalone?"
BASIS_OPTIONS: dict[PageBasis, str] = {
    PageBasis.CONSOLIDATED: "The heading says consolidated, or names the group.",
    PageBasis.STANDALONE: "The heading says standalone, separate, or parent company only.",
    PageBasis.UNCLEAR: "The heading does not say which basis the page is on.",
}
ORDERS = ("forward", "reversed")  # the option order; the docs warn the model leans to the first option, so evaluation tries both

_REASON_BY_CLASS = (  # SDK exception class name -> reason word, most specific first
    ("TypeSafeAPITimeoutError", "timeout"),
    ("TypeSafeAPIConnectionError", "connection"),
    ("TypeSafeRateLimitError", "rate_limit"),
    ("TypeSafeAuthenticationError", "auth"),
    ("TypeSafePermissionDeniedError", "auth"),
    ("TypeSafeBadRequestError", "bad_request"),
    ("TypeSafeUnprocessableEntityError", "bad_request"),
    ("TypeSafeInternalServerError", "server"),
    ("TypeSafeAPIResponseValidationError", "invalid_reply"),
    ("TypeSafeError", "sdk_error"),
)


def failure_reason(error: BaseException) -> str:
    """The fixed reason word for an exception from the SDK or anywhere else; never any of its text."""
    names = {cls.__name__ for cls in type(error).__mro__}
    for name, reason in _REASON_BY_CLASS:
        if name in names:
            return reason
    return "error"


def question_text() -> str:
    """All the words of the two questions (for the cost estimate)."""
    parts = [TYPE_INSTRUCTIONS, BASIS_INSTRUCTIONS, *TYPE_OPTIONS.values(), *BASIS_OPTIONS.values(), *(k.value for k in TYPE_OPTIONS), *(k.value for k in BASIS_OPTIONS)]
    return "\n".join(parts)


def page_state(text: str, lines: int) -> str:
    """The top of the page: its first ``lines`` non-empty lines."""
    kept = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(kept[:lines])


def _ordered(options: Mapping[Any, str], order: str) -> dict[str, str]:
    items = [(key.value, text) for key, text in options.items()]
    return dict(reversed(items) if order == "reversed" else items)


def build_questions(order: str = "forward") -> dict[str, Any]:
    """The two Choice questions (imports the SDK)."""
    from typesafe_sdk import Choice

    return {
        TYPE_QUESTION: Choice(instructions=TYPE_INSTRUCTIONS, criteria=_ordered(TYPE_OPTIONS, order)),
        BASIS_QUESTION: Choice(instructions=BASIS_INSTRUCTIONS, criteria=_ordered(BASIS_OPTIONS, order)),
    }


class JevClassifier:
    """Classifies pages with Jev. ``client`` can be given (a test double with the SDK's ``system_one``); otherwise it is built on first use."""

    sends_off_machine = True

    def __init__(
        self,
        settings: JevSettings,
        env: Mapping[str, str],
        *,
        cache_dir: Path = DEFAULT_JEV_CACHE_DIR,
        order: str = "forward",
        client: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if order not in ORDERS:
            raise ValueError("order is forward or reversed")
        self._settings = settings
        self._key = typesafe_api_key(env)
        self._client = client
        self._order = order
        self._clock = clock
        self.cache = JevCache(cache_dir)

    @property
    def has_key(self) -> bool:
        return self._client is not None or self._key is not None

    def _build_client(self) -> Any:
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        # No retry: a failed classification only means the page is sent as without Jev, so waiting is the wrong response.
        return TypeSafeClient(
            api_key=self._key,
            model=self._settings.model,
            retry=RetryPolicy(max_retries=0, timeout=self._settings.timeout_seconds),
            timeout=self._settings.timeout_seconds,
        )

    def classify(self, page_number: int, text: str) -> PageClassification:
        settings = self._settings
        state = page_state(text, settings.state_lines)
        if not state:
            raise ClassifierError("invalid_reply")  # nothing to read: the page is sent as without Jev
        key = cache_key(settings.model, QUESTIONS_VERSION, settings.state_lines, self._order, state)
        cached = self.cache.get(key)
        if cached is not None:
            try:
                return self._from_record(cached, latency_ms=0, cached=True)
            except (KeyError, ValueError, TypeError):
                pass  # a damaged cache file is only a miss
        if not self.has_key:
            raise ClassifierError("no_key")
        started = self._clock()
        try:
            if self._client is None:
                self._client = self._build_client()
            response = self._client.system_one(state, build_questions(self._order), model=settings.model)
            record = self._record_of(response)
        except ClassifierError:
            raise
        except Exception as error:  # the pipeline never fails because of Jev: every error becomes a reason word
            raise ClassifierError(failure_reason(error)) from None
        record["latency_ms"] = int((self._clock() - started) * 1000)
        self.cache.put(key, {k: v for k, v in record.items() if k != "latency_ms"})
        return self._from_record(record, latency_ms=record["latency_ms"], cached=False)

    @staticmethod
    def _record_of(response: Any) -> dict[str, Any]:
        """The numbers of a reply, checked. Anything unexpected is ``invalid_reply``."""
        try:
            kind, basis = response.choices[TYPE_QUESTION], response.choices[BASIS_QUESTION]
            record = {
                "model_id": str(response.model),
                "input_tokens": int(response.usage.input_tokens),
                "page_type": str(kind.choice),
                "type_confidence": float(kind.confidence),
                "type_probabilities": sorted((str(k), float(v)) for k, v in kind.probabilities.items()),
                "basis": str(basis.choice),
                "basis_confidence": float(basis.confidence),
                "basis_probabilities": sorted((str(k), float(v)) for k, v in basis.probabilities.items()),
            }
            PageType(record["page_type"])
            PageBasis(record["basis"])
        except Exception:
            raise ClassifierError("invalid_reply") from None
        for name in ("type_confidence", "basis_confidence"):
            if not 0.0 <= record[name] <= 1.0:
                raise ClassifierError("invalid_reply")
        return record

    @staticmethod
    def _from_record(record: Mapping[str, Any], *, latency_ms: int, cached: bool) -> PageClassification:
        return PageClassification(
            page_type=PageType(record["page_type"]),
            type_confidence=float(record["type_confidence"]),
            basis=PageBasis(record["basis"]),
            basis_confidence=float(record["basis_confidence"]),
            model_id=str(record["model_id"]),
            input_tokens=0 if cached else int(record["input_tokens"]),
            latency_ms=latency_ms,
            cached=cached,
            type_probabilities=tuple((str(k), float(v)) for k, v in record["type_probabilities"]),
            basis_probabilities=tuple((str(k), float(v)) for k, v in record["basis_probabilities"]),
        )
