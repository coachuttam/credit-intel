"""Cache and budget around a provider (PRD FR-003.5, NFR-09, OD-8)."""

from credit_intel.llm.budget import TokenBudget, estimate_tokens
from credit_intel.llm.cache import CacheKeyInputs, ResponseCache
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse


class LLMGateway:
    """One call path: cache lookup, budget check, provider call, usage, cache write.

    A hit returns the stored response, counts zero tokens and makes no call. A
    miss checks the budget (estimate plus reservation) before calling, records the
    provider's reported usage afterwards, and stores the response. A corrective
    retry (FR-004.1) is simply another ``complete`` call with its own key inputs.
    """

    def __init__(self, provider: LLMProvider, cache: ResponseCache, budget: TokenBudget) -> None:
        self._provider = provider
        self._cache = cache
        self._budget = budget

    def complete(self, request: LLMRequest, inputs: CacheKeyInputs) -> LLMResponse:
        cached = self._cache.get(inputs)
        if cached is not None:
            return cached
        self._budget.check(estimate_tokens(request.prompt_text), request.max_output_tokens)
        response = self._provider.complete(request)
        self._budget.record(response.usage.total)
        self._cache.put(inputs, response)
        return response
