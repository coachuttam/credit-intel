"""Retry with exponential backoff for transient LLM failures (PRD FR-011.3).

``RetryingProvider`` wraps any provider. A transient failure (a timeout, rate limit or
server error, raised as ``LLMTransientError``) is tried again, up to ``attempts`` attempts
in all (default 3) with waits of 1 s, then 2 s: exponential, with no random jitter so a
run's timing is reproducible. After the last attempt it raises ``E-LLM-UNAVAILABLE``.

Nothing else is retried. An authentication failure (``E-LLM-AUTH``), a request the
provider refuses, and every other error pass straight through on the first attempt.

The wrapper sits inside the gateway, so the token-ceiling check runs once for the
logical call (before its first attempt) and only the reply that finally arrives is
recorded and cached: an attempt that failed returned no usage and adds no tokens. The
number of retried attempts is counted in ``retries`` for the run statistics (FR-012.1).
Log lines carry the attempt number, the failure reason (an HTTP status or a word) and the
wait, never the request, the reply or the key.
"""

import logging
import time
from collections.abc import Callable

from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.llm.errors import LLMTransientError
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse

logger = logging.getLogger("credit_intel.llm")

DEFAULT_ATTEMPTS = 3  # FR-011.3
DEFAULT_BASE_DELAY_S = 1.0
DEFAULT_FACTOR = 2.0


class RetryingProvider:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        attempts: int = DEFAULT_ATTEMPTS,
        base_delay_s: float = DEFAULT_BASE_DELAY_S,
        factor: float = DEFAULT_FACTOR,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise ValueError("attempts must be a positive integer")
        if base_delay_s < 0 or factor < 1:
            raise ValueError("the first wait must be at least 0 and the factor at least 1")
        self._provider = provider
        self._attempts = attempts
        self._base = base_delay_s
        self._factor = factor
        self._sleep = sleep
        self.retries = 0  # attempts made again after a transient failure, over all calls

    def delay(self, failed_attempt: int) -> float:
        """The wait after the ``failed_attempt``-th failed attempt (1-based)."""
        return self._base * self._factor ** (failed_attempt - 1)

    def complete(self, request: LLMRequest) -> LLMResponse:
        failure: LLMTransientError | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                return self._provider.complete(request)
            except LLMTransientError as error:
                failure = error
                if attempt == self._attempts:
                    break
                wait = self.delay(attempt)
                self.retries += 1
                logger.warning(
                    "llm attempt=%d of %d failed reason=%s retry_in_s=%s", attempt, self._attempts, error.reason, wait
                )
                (self._sleep or time.sleep)(wait)
        assert failure is not None
        logger.warning("llm unavailable after attempts=%d reason=%s", self._attempts, failure.reason)
        raise IngestionError(ErrorCode.LLM_UNAVAILABLE, detail=failure.reason) from failure
