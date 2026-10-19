"""Retry with exponential backoff (PRD FR-011.3; Phase 2 step 10b; B-226). No real waiting."""

import logging
import time
import traceback

import httpx2
import openai
import pytest

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.budget import TokenBudget
from credit_intel.llm.cache import CacheKeyInputs, ResponseCache
from credit_intel.llm.errors import LLMRequestError, LLMTransientError
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.openai_provider import OpenAIProvider
from credit_intel.llm.provider import STRUCTURED_OUTPUT_MODE, LLMRequest, LLMResponse, LLMUsage
from credit_intel.llm.retry import RetryingProvider

REQUEST = LLMRequest(system="SECRET SYSTEM", user="SECRET USER", model_id="m", max_output_tokens=100)
REPLY = LLMResponse("{}", LLMUsage(10, 5))


class Flaky:
    """Fails with the given errors in order, then answers."""

    def __init__(self, *failures, reply=REPLY):
        self.failures, self.reply, self.requests = list(failures), reply, []

    def complete(self, request):
        self.requests.append(request)
        if self.failures:
            raise self.failures.pop(0)
        return self.reply


def transient(reason="HTTP 503"):
    return LLMTransientError(reason)


def wrap(*failures, **kw):
    waits = []
    inner = Flaky(*failures)
    return RetryingProvider(inner, sleep=waits.append, **kw), inner, waits


# --- the happy path and the waits ---------------------------------------------------------------------


def test_a_first_attempt_that_works_makes_no_wait_and_no_retry():
    provider, inner, waits = wrap()

    assert provider.complete(REQUEST) == REPLY and waits == [] and provider.retries == 0
    assert len(inner.requests) == 1


def test_one_transient_failure_waits_one_second_and_then_succeeds():
    provider, inner, waits = wrap(transient())

    assert provider.complete(REQUEST) == REPLY
    assert waits == [1.0] and provider.retries == 1 and len(inner.requests) == 2


def test_two_transient_failures_wait_one_then_two_seconds():
    provider, inner, waits = wrap(transient(), transient())

    assert provider.complete(REQUEST) == REPLY
    assert waits == [1.0, 2.0] and provider.retries == 2 and len(inner.requests) == 3


def test_three_failures_give_up_after_three_attempts_with_no_wait_after_the_last():
    provider, inner, waits = wrap(transient(), transient(), transient("HTTP 429"), transient())

    with pytest.raises(IngestionError) as excinfo:
        provider.complete(REQUEST)

    assert excinfo.value.code is ErrorCode.LLM_UNAVAILABLE and excinfo.value.code.value == "E-LLM-UNAVAILABLE"
    assert len(inner.requests) == 3 and waits == [1.0, 2.0] and provider.retries == 2
    assert "HTTP 429" in str(excinfo.value) and isinstance(excinfo.value.__cause__, LLMTransientError)


def test_the_waits_are_exponential_and_exactly_the_formula():
    provider, _, waits = wrap(*[transient() for _ in range(4)], attempts=5, base_delay_s=0.5, factor=3.0)

    provider.complete(REQUEST)

    assert waits == [0.5, 1.5, 4.5, 13.5]
    assert [provider.delay(n) for n in (1, 2, 3, 4)] == waits


def test_there_is_no_random_jitter():
    runs = []
    for _ in range(3):
        provider, _, waits = wrap(transient(), transient())
        provider.complete(REQUEST)
        runs.append(waits)

    assert runs[0] == runs[1] == runs[2] == [1.0, 2.0]


def test_one_attempt_means_no_retry():
    provider, inner, waits = wrap(transient(), attempts=1)

    with pytest.raises(IngestionError) as excinfo:
        provider.complete(REQUEST)

    assert excinfo.value.code is ErrorCode.LLM_UNAVAILABLE and len(inner.requests) == 1 and waits == []


def test_the_default_wait_is_time_sleep(monkeypatch):
    seen = []
    monkeypatch.setattr(time, "sleep", seen.append)
    provider = RetryingProvider(Flaky(transient(), transient()))

    provider.complete(REQUEST)

    assert seen == [1.0, 2.0]


def test_every_attempt_gets_the_same_request():
    provider, inner, _ = wrap(transient(), transient())

    provider.complete(REQUEST)

    assert all(sent is REQUEST for sent in inner.requests)


def test_the_retry_counter_adds_up_over_calls():
    inner = Flaky(transient(), transient())
    provider = RetryingProvider(inner, sleep=lambda _: None)

    provider.complete(REQUEST)
    inner.failures = [transient()]
    provider.complete(REQUEST)

    assert provider.retries == 3


@pytest.mark.parametrize(
    "bad",
    [dict(attempts=0), dict(attempts=-1), dict(attempts=True), dict(attempts=1.5), dict(base_delay_s=-1), dict(factor=0.5)],
)
def test_nonsense_settings_are_refused(bad):
    with pytest.raises(ValueError):
        RetryingProvider(Flaky(), **bad)


# --- what is not retried ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        IngestionError(ErrorCode.LLM_AUTH),
        LLMRequestError("HTTP 400"),
        ValueError("a bug"),
        RuntimeError("anything else"),
    ],
    ids=["auth", "refused request", "value error", "other"],
)
def test_other_failures_pass_straight_through_on_the_first_attempt(error):
    provider, inner, waits = wrap(error, transient())

    with pytest.raises(type(error)) as excinfo:
        provider.complete(REQUEST)

    assert excinfo.value is error and len(inner.requests) == 1 and waits == [] and provider.retries == 0


def test_an_authentication_failure_after_a_transient_one_is_still_not_retried():
    provider, inner, waits = wrap(transient(), IngestionError(ErrorCode.LLM_AUTH), transient())

    with pytest.raises(IngestionError) as excinfo:
        provider.complete(REQUEST)

    assert excinfo.value.code is ErrorCode.LLM_AUTH and len(inner.requests) == 2 and waits == [1.0]


# --- the error and the logs are safe --------------------------------------------------------------------------


def test_the_unavailable_error_has_a_safe_message():
    provider, _, _ = wrap(transient("HTTP 503"), transient("HTTP 503"), transient("HTTP 503"))

    with pytest.raises(IngestionError) as excinfo:
        provider.complete(REQUEST)

    text = "".join(traceback.format_exception(excinfo.value))
    assert "SECRET" not in text
    assert str(excinfo.value).startswith("E-LLM-UNAVAILABLE: The LLM provider was unavailable")


def test_each_retry_is_logged_without_the_request_or_the_reply(caplog):
    provider, _, _ = wrap(transient("HTTP 429"), transient("timeout"), transient("HTTP 503"))

    with caplog.at_level(logging.INFO, logger="credit_intel.llm"), pytest.raises(IngestionError):
        provider.complete(REQUEST)

    messages = [r.getMessage() for r in caplog.records if r.name == "credit_intel.llm"]
    assert messages[0] == "llm attempt=1 of 3 failed reason=HTTP 429 retry_in_s=1.0"
    assert messages[1] == "llm attempt=2 of 3 failed reason=timeout retry_in_s=2.0"
    assert messages[2] == "llm unavailable after attempts=3 reason=HTTP 503"
    assert all("SECRET" not in m and "{}" not in m for m in messages)
    assert all(r.levelno == logging.WARNING for r in caplog.records if r.name == "credit_intel.llm")


# --- inside the gateway: the ceiling, the cache and the counts -------------------------------------------------------


def inputs():
    return CacheKeyInputs("d" * 64, (1,), "openai", "m", "p1", "s1", 0, 100, STRUCTURED_OUTPUT_MODE)


def gateway(tmp_path, provider, ceiling=100_000):
    return LLMGateway(provider, ResponseCache(tmp_path / "c"), TokenBudget(ceiling))


def test_only_the_reply_that_arrives_is_counted_and_cached(tmp_path):
    provider, inner, _ = wrap(transient(), transient())
    gw = gateway(tmp_path, provider)

    assert gw.complete(REQUEST, inputs()) == REPLY

    assert gw.calls == 1 and len(inner.requests) == 3
    assert gw._budget.used == 15  # one reply's usage, not three attempts
    assert gw.complete(REQUEST, inputs()) == REPLY and len(inner.requests) == 3  # now a hit


def test_giving_up_caches_nothing_and_counts_nothing(tmp_path):
    provider, _, _ = wrap(transient(), transient(), transient())
    gw = gateway(tmp_path, provider)

    with pytest.raises(IngestionError):
        gw.complete(REQUEST, inputs())

    assert gw.calls == 0 and gw._budget.used == 0 and not (tmp_path / "c").exists()


def test_the_ceiling_is_checked_once_for_the_call_not_once_per_attempt(tmp_path):
    class Counting(TokenBudget):
        checks = 0

        def check(self, estimated_input, max_output):
            Counting.checks += 1
            super().check(estimated_input, max_output)

    provider, inner, _ = wrap(transient(), transient())
    gw = LLMGateway(provider, ResponseCache(tmp_path / "c"), Counting(100_000))

    assert gw.complete(REQUEST, inputs()) == REPLY

    assert Counting.checks == 1 and len(inner.requests) == 3


# --- with the OpenAI provider ----------------------------------------------------------------------------------------


class Client:
    def __init__(self, *outcomes):
        from types import SimpleNamespace

        self.outcomes, self.requests = list(outcomes), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def completion():
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate({
        "id": "c", "object": "chat.completion", "created": 1, "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}", "refusal": None}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    })  # fmt: skip


def status_error(cls, code):
    request = httpx2.Request("POST", "https://example.invalid")
    return cls("provider text", response=httpx2.Response(code, request=request), body=None)


def test_a_timeout_and_a_rate_limit_are_retried_against_the_real_provider_class():
    client = Client(openai.APITimeoutError(request=httpx2.Request("POST", "https://x.invalid")),
                    status_error(openai.RateLimitError, 429), completion())  # fmt: skip
    waits = []
    provider = RetryingProvider(OpenAIProvider("sk-test", client=client), sleep=waits.append)

    reply = provider.complete(REQUEST)

    assert reply.text == "{}" and reply.usage == LLMUsage(7, 3)
    assert len(client.requests) == 3 and waits == [1.0, 2.0]


def test_an_authentication_failure_is_one_request_against_the_real_provider_class():
    client = Client(status_error(openai.AuthenticationError, 401), completion())
    provider = RetryingProvider(OpenAIProvider("sk-test", client=client), sleep=lambda _: None)

    with pytest.raises(IngestionError) as excinfo:
        provider.complete(REQUEST)

    assert excinfo.value.code is ErrorCode.LLM_AUTH and len(client.requests) == 1


def test_a_bad_request_is_one_request_against_the_real_provider_class():
    client = Client(status_error(openai.BadRequestError, 400), completion())
    provider = RetryingProvider(OpenAIProvider("sk-test", client=client), sleep=lambda _: None)

    with pytest.raises(LLMRequestError):
        provider.complete(REQUEST)

    assert len(client.requests) == 1
