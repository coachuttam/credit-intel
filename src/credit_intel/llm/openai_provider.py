"""The OpenAI provider (PRD D-02), behind the ``LLMProvider`` interface.

One blocking chat-completions call per request: temperature 0, the configured output limit,
the strict JSON-schema structured-output mode (``strict_schema``), and ``store=False`` so
the completion is not retained by the provider (SEC-10). The SDK's own retries are off:
retry and backoff are FR-011.3's and live in ``retry.py``, so every attempt is counted and
checked against the token ceiling.

Failures are sorted so the caller never has to read the SDK's errors:
- a timeout, a connection failure, a rate limit, a 408, 409 or 5xx: ``LLMTransientError``;
- an authentication or permission failure: ``IngestionError`` ``E-LLM-AUTH``, never retried;
- anything else the provider refuses: ``LLMRequestError`` (internal, not retried).

The API key is handed to the SDK client and kept nowhere else: not on this object, not in
a message, a log line or the cache. An authentication error is raised without its cause,
because the provider's message can quote part of the key.
"""

from typing import Any

import openai

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.budget import estimate_tokens
from credit_intel.llm.errors import LLMRequestError, LLMTransientError
from credit_intel.llm.provider import STRUCTURED_OUTPUT_MODE, LLMRequest, LLMResponse, LLMUsage
from credit_intel.llm.strict_schema import strict_schema
from credit_intel.models import ExtractionResponse

SCHEMA_NAME = "extraction_response"
DEFAULT_TIMEOUT_S = 120.0
_TRANSIENT_STATUS = frozenset({408, 409, 429})


def response_format() -> dict[str, Any]:
    """The ``response_format`` sent with every request: the response schema, strict."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": SCHEMA_NAME,
            "strict": True,
            "schema": strict_schema(ExtractionResponse.model_json_schema()),
        },
    }


class OpenAIProvider:
    def __init__(
        self, api_key: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, client: Any | None = None
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise IngestionError(ErrorCode.LLM_AUTH)
        # max_retries=0: retries are ours (FR-011.3). A client may be injected for tests.
        self._client = client or openai.OpenAI(api_key=api_key, timeout=timeout_s, max_retries=0)

    def __repr__(self) -> str:
        return "OpenAIProvider()"

    def complete(self, request: LLMRequest) -> LLMResponse:
        if request.structured_output_mode != STRUCTURED_OUTPUT_MODE:
            raise ValueError("this provider supports only the strict JSON-schema mode")
        try:
            completion = self._client.chat.completions.create(
                model=request.model_id,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                temperature=request.temperature,
                max_completion_tokens=request.max_output_tokens,
                response_format=response_format(),
                store=False,
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise IngestionError(ErrorCode.LLM_AUTH) from None
        except openai.APIConnectionError as exc:  # includes timeouts
            raise LLMTransientError("timeout" if isinstance(exc, openai.APITimeoutError) else "connection") from None
        except openai.APIStatusError as exc:
            status = exc.status_code
            if status in _TRANSIENT_STATUS or status >= 500:
                raise LLMTransientError(f"HTTP {status}") from None
            raise LLMRequestError(f"HTTP {status}") from None
        except openai.OpenAIError:
            raise LLMRequestError("client error") from None
        return self._read(request, completion)

    @staticmethod
    def _read(request: LLMRequest, completion: Any) -> LLMResponse:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise LLMRequestError("no choice in the reply")
        message = choices[0].message
        # A refusal has no content; it is passed on as empty text and fails validation.
        text = "" if getattr(message, "refusal", None) else (message.content or "")
        usage = getattr(completion, "usage", None)
        if usage is None:  # the provider reported nothing: a conservative estimate (OD-8)
            return LLMResponse(text, LLMUsage(estimate_tokens(request.prompt_text), estimate_tokens(text)))
        return LLMResponse(text, LLMUsage(int(usage.prompt_tokens), int(usage.completion_tokens)))
