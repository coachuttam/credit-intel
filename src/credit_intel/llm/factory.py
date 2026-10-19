"""Building the configured provider (PRD D-02, SEC-02, SEC-03).

The provider and model are configuration (``LLMSettings``); the API key is read from the
process environment only (``OPENAI_API_KEY``), never from a file this project loads, never
logged and never stored. A missing or blank key is ``E-LLM-AUTH`` before any call. The
real provider is returned wrapped in the retry layer (FR-011.3). The fake provider needs a
script and belongs to tests, so it is not built from settings.
"""

import os
from collections.abc import Callable, Mapping

from credit_intel.config import ENV_OPENAI_API_KEY, LLMSettings
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.openai_provider import OpenAIProvider
from credit_intel.llm.provider import LLMProvider
from credit_intel.llm.retry import RetryingProvider


def build_provider(
    settings: LLMSettings,
    env: Mapping[str, str] | None = None,
    *,
    sleep: Callable[[float], None] | None = None,
) -> LLMProvider:
    env = os.environ if env is None else env
    if settings.provider == "openai":
        key = env.get(ENV_OPENAI_API_KEY, "")
        if not key.strip():
            raise IngestionError(ErrorCode.LLM_AUTH)
        return RetryingProvider(OpenAIProvider(key), sleep=sleep)
    if settings.provider == "fake":
        raise ValueError("the fake provider needs a script: construct FakeProvider in the test")
    raise ValueError(f"unknown provider {settings.provider!r}")
