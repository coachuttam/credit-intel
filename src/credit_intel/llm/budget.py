"""Per-run token budget (PRD NFR-09, OD-8).

The ceiling counts the tokens of calls actually made, including corrective
retries; a cache hit counts zero. Before a call the input tokens are estimated
conservatively and the maximum output tokens are reserved; if used + estimate +
reservation would exceed the ceiling, the call is not made. After the call the
provider's reported usage replaces the estimate.
"""

from credit_intel.ingestion.errors import ErrorCode, IngestionError

# Deliberately pessimistic: English prose averages about four characters per token
# and digit-heavy financial text fewer. Two UTF-8 bytes per token overestimates, so
# the check errs towards refusing a call, never towards overspending. No tokenizer
# dependency (OD-8).
BYTES_PER_TOKEN = 2


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: UTF-8 bytes divided by two, rounded up."""
    return -(-len(text.encode("utf-8")) // BYTES_PER_TOKEN)


class TokenBudget:
    def __init__(self, ceiling: int) -> None:
        if isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling < 1:
            raise ValueError("the token ceiling must be a positive integer")
        self.ceiling = ceiling
        self.used = 0

    def check(self, estimated_input: int, max_output: int) -> None:
        """Raise ``E-LLM-BUDGET-EXCEEDED`` unless the call fits within the ceiling."""
        if self.used + estimated_input + max_output > self.ceiling:
            raise IngestionError(ErrorCode.LLM_BUDGET_EXCEEDED)

    def record(self, tokens: int) -> None:
        """Add the provider's reported usage for a call that was made."""
        self.used += tokens
