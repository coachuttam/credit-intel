"""Cache and budget around a provider (PRD FR-003.5, NFR-09, OD-8)."""

from collections.abc import Callable

from credit_intel.llm.budget import TokenBudget, estimate_tokens
from credit_intel.llm.cache import CacheKeyInputs, ResponseCache
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse


class LLMGateway:
    """One call path: cache lookup, budget check, provider call, usage, cache write.

    A hit returns the stored response, counts zero tokens and makes no call. A
    miss checks the budget (estimate plus reservation) before calling, records the
    provider's reported usage afterwards, and stores the response. A corrective
    retry (FR-004.1) is simply another ``complete`` call with its own key inputs.

    Only a response that ``is_valid`` accepts is written to the cache, so a response
    that fails validation is never replayed on a later run. Its tokens still count.
    """

    def __init__(self, provider: LLMProvider, cache: ResponseCache, budget: TokenBudget) -> None:
        self._provider = provider
        self._cache = cache
        self._budget = budget
        self.calls = 0  # provider calls made (a cache hit or a refused call makes none)
        self.input_tokens = 0  # as reported by the provider, over the calls made
        self.output_tokens = 0
        self.cached_input_tokens = 0  # what the cache hits would have used (not billed; for comparing runs)
        self.cached_output_tokens = 0

    def complete(
        self,
        request: LLMRequest,
        inputs: CacheKeyInputs,
        is_valid: Callable[[str], bool] = lambda text: True,
    ) -> LLMResponse:
        cached = self._cache.get(inputs)
        if cached is not None:
            self.cached_input_tokens += cached.usage.input_tokens
            self.cached_output_tokens += cached.usage.output_tokens
            return cached
        self._budget.check(estimate_tokens(request.prompt_text), request.max_output_tokens)
        response = self._provider.complete(request)
        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self._budget.record(response.usage.total)
        if is_valid(response.text):
            self._cache.put(inputs, response)
        return response
