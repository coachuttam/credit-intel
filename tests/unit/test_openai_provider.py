"""The OpenAI provider against a fake client, with no network (Phase 2 step 10a; B-225).

PRD D-02, FR-011.3, SEC-03, SEC-10. Real SDK exception and response types are built by hand.
"""

import traceback
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.chat import ChatCompletion

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.budget import TokenBudget, estimate_tokens
from credit_intel.llm.cache import CacheKeyInputs, ResponseCache
from credit_intel.llm.errors import LLMRequestError, LLMTransientError
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.openai_provider import SCHEMA_NAME, OpenAIProvider, response_format
from credit_intel.llm.provider import STRUCTURED_OUTPUT_MODE, LLMProvider, LLMRequest, LLMUsage
from credit_intel.llm.strict_schema import strict_schema
from credit_intel.models import ExtractionResponse

SECRET = "sk-SECRETKEY-1234567890"
REQUEST_OBJ = httpx2.Request("POST", "https://example.invalid/v1/chat/completions")


def completion(text="{}", prompt=10, output=5, finish="stop", refusal=None, usage=True, choices=True):
    message = {"role": "assistant", "content": text, "refusal": refusal}
    body = {
        "id": "c1", "object": "chat.completion", "created": 1, "model": "m",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}] if choices else [],
    }  # fmt: skip
    if usage:
        body["usage"] = {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt + output}
    return ChatCompletion.model_validate(body)


class FakeClient:
    def __init__(self, *outcomes):
        self.outcomes, self.requests = list(outcomes), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def status_error(cls, code, message=f"provider says {SECRET} and a secret body"):
    return cls(message, response=httpx2.Response(code, request=REQUEST_OBJ), body={"error": {"message": message}})


def request(**kw):
    base = dict(system="SYSTEM TEXT", user="USER TEXT", model_id="gpt-test", max_output_tokens=321)
    return LLMRequest(**(base | kw))


def provider(*outcomes):
    client = FakeClient(*outcomes)
    return OpenAIProvider(SECRET, client=client), client


# --- the request ------------------------------------------------------------------------------------


def test_the_provider_satisfies_the_interface():
    instance, _ = provider()

    llm: LLMProvider = instance
    assert llm is instance


def test_the_request_sends_exactly_these_arguments():
    instance, client = provider(completion())

    instance.complete(request())

    (sent,) = client.requests
    assert set(sent) == {"model", "messages", "temperature", "max_completion_tokens", "response_format", "store"}
    assert sent["model"] == "gpt-test" and sent["temperature"] == 0 and sent["max_completion_tokens"] == 321
    assert sent["store"] is False  # SEC-10: the completion is not retained
    assert sent["messages"] == [{"role": "system", "content": "SYSTEM TEXT"}, {"role": "user", "content": "USER TEXT"}]


def test_the_response_format_is_the_strict_json_schema_of_the_response_model():
    instance, client = provider(completion())

    instance.complete(request())

    fmt = client.requests[0]["response_format"]
    assert fmt == response_format()
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["name"] == SCHEMA_NAME
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == strict_schema(ExtractionResponse.model_json_schema())


def test_the_prompt_is_sent_unchanged_and_nothing_else_is_added():
    instance, client = provider(completion())
    system, user = "S ₹ \n é", "page text\n=== PAGE 1 ===\n1,234.50"

    instance.complete(request(system=system, user=user))

    assert [m["content"] for m in client.requests[0]["messages"]] == [system, user]


def test_a_request_for_another_structured_output_mode_is_refused():
    instance, client = provider(completion())

    with pytest.raises(ValueError):
        instance.complete(request(structured_output_mode="json_object"))

    assert client.requests == []


def test_each_call_is_one_request():
    instance, client = provider(completion("a"), completion("b"))

    assert [instance.complete(request()).text, instance.complete(request()).text] == ["a", "b"]
    assert len(client.requests) == 2


# --- the reply ----------------------------------------------------------------------------------------


def test_the_reply_text_and_reported_usage_are_returned():
    instance, _ = provider(completion('{"x":1}', prompt=1200, output=34))

    reply = instance.complete(request())

    assert reply.text == '{"x":1}' and reply.usage == LLMUsage(1200, 34)


def test_when_no_usage_is_reported_a_conservative_estimate_is_used():
    instance, _ = provider(completion("abcd", usage=False))

    reply = instance.complete(request())

    assert reply.usage == LLMUsage(estimate_tokens("SYSTEM TEXTUSER TEXT"), estimate_tokens("abcd"))


def test_a_refusal_has_no_text():
    instance, _ = provider(completion(text=None, refusal="I cannot help with that"))

    assert instance.complete(request()).text == ""


def test_a_refusal_wins_over_any_content():
    instance, _ = provider(completion(text="partial", refusal="no"))

    assert instance.complete(request()).text == ""


def test_a_missing_content_is_empty_text_and_a_truncated_reply_is_passed_on():
    empty, _ = provider(completion(text=None))
    cut, _ = provider(completion('{"fields": [', finish="length"))

    assert empty.complete(request()).text == "" and cut.complete(request()).text == '{"fields": ['


def test_a_reply_with_no_choice_is_unusable():
    instance, _ = provider(completion(choices=False))

    with pytest.raises(LLMRequestError):
        instance.complete(request())


# --- failures that may succeed on another attempt (FR-011.3) -----------------------------------------------


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (openai.APITimeoutError(request=REQUEST_OBJ), "timeout"),
        (openai.APIConnectionError(request=REQUEST_OBJ), "connection"),
        (status_error(openai.RateLimitError, 429), "HTTP 429"),
        (status_error(openai.InternalServerError, 500), "HTTP 500"),
        (status_error(openai.InternalServerError, 502), "HTTP 502"),
        (status_error(openai.InternalServerError, 503), "HTTP 503"),
        (status_error(openai.APIStatusError, 504), "HTTP 504"),
        (status_error(openai.APIStatusError, 408), "HTTP 408"),
        (status_error(openai.ConflictError, 409), "HTTP 409"),
    ],
)
def test_timeouts_rate_limits_and_server_errors_are_transient(error, reason):
    instance, _ = provider(error)

    with pytest.raises(LLMTransientError) as excinfo:
        instance.complete(request())

    assert excinfo.value.reason == reason and SECRET not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


# --- authentication (E-LLM-AUTH, never retried) -------------------------------------------------------------


@pytest.mark.parametrize("error", [status_error(openai.AuthenticationError, 401), status_error(openai.PermissionDeniedError, 403)])
def test_authentication_and_permission_failures_are_e_llm_auth(error):
    instance, _ = provider(error)

    with pytest.raises(IngestionError) as excinfo:
        instance.complete(request())

    assert excinfo.value.code is ErrorCode.LLM_AUTH and excinfo.value.code.value == "E-LLM-AUTH"
    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_the_provider_error_text_which_can_quote_the_key_never_reaches_the_traceback():
    instance, _ = provider(status_error(openai.AuthenticationError, 401))

    with pytest.raises(IngestionError) as excinfo:
        instance.complete(request())

    text = "".join(traceback.format_exception(excinfo.value))
    assert SECRET not in text and "secret body" not in text
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_an_empty_key_is_an_authentication_failure_before_any_call():
    for key in ("", "   ", None):
        with pytest.raises(IngestionError) as excinfo:
            OpenAIProvider(key)  # type: ignore[arg-type]
        assert excinfo.value.code is ErrorCode.LLM_AUTH


# --- failures that cannot succeed (internal) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (status_error(openai.BadRequestError, 400), "HTTP 400"),
        (status_error(openai.NotFoundError, 404), "HTTP 404"),
        (status_error(openai.UnprocessableEntityError, 422), "HTTP 422"),
        (openai.OpenAIError("something else"), "client error"),
    ],
)
def test_other_refusals_are_internal_errors_with_a_safe_message(error, reason):
    instance, _ = provider(error)

    with pytest.raises(LLMRequestError) as excinfo:
        instance.complete(request())

    assert excinfo.value.reason == reason and SECRET not in str(excinfo.value) and "secret body" not in str(excinfo.value)
    assert not isinstance(excinfo.value, LLMTransientError)
    assert excinfo.value.__cause__ is None  # the provider's text can echo the request, so it is not kept
    assert "secret body" not in "".join(traceback.format_exception(excinfo.value))


# --- the key stays out of sight (SEC-03) ------------------------------------------------------------------------------


def test_the_key_is_not_in_the_providers_text_forms():
    instance = OpenAIProvider(SECRET)

    assert SECRET not in repr(instance) and SECRET not in str(instance)
    assert not any(SECRET == value for value in vars(instance).values())


def test_the_real_client_is_configured_without_its_own_retries():
    client = OpenAIProvider(SECRET, timeout_s=33.0)._client

    assert client.max_retries == 0 and client.timeout == 33.0


# --- through the gateway ---------------------------------------------------------------------------------------------------


def inputs():
    return CacheKeyInputs("d" * 64, (1,), "openai", "gpt-test", "p1", "s1", 0, 321, STRUCTURED_OUTPUT_MODE)


def gateway(tmp_path, instance):
    return LLMGateway(instance, ResponseCache(tmp_path / "c"), TokenBudget(100_000))


def test_a_transient_failure_passes_through_the_gateway_uncached_and_uncounted(tmp_path):
    instance, _ = provider(openai.APITimeoutError(request=REQUEST_OBJ))
    gw = gateway(tmp_path, instance)

    with pytest.raises(LLMTransientError):
        gw.complete(request(), inputs())

    assert gw.calls == 0 and not (tmp_path / "c").exists()


def test_a_reply_through_the_gateway_is_cached_and_its_tokens_counted(tmp_path):
    instance, client = provider(completion("{}", prompt=100, output=20))
    gw = gateway(tmp_path, instance)

    first = gw.complete(request(), inputs())
    again = gw.complete(request(), inputs())

    assert first == again and len(client.requests) == 1 and gw.calls == 1
