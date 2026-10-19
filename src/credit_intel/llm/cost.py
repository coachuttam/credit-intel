"""Estimated LLM cost (PRD NFR-09, SC-11, D-02).

A pure function of the provider's reported usage and the configured prices. It is exact
(``Decimal``, no rounding): rounding is for display only. A cache hit made no call and so
costs nothing; a failed attempt reported no usage and adds nothing.
"""

from decimal import Decimal

from credit_intel.config import PricingSettings

MILLION = Decimal(1_000_000)


def estimate_cost(input_tokens: int, output_tokens: int, pricing: PricingSettings) -> Decimal:
    """USD for ``input_tokens`` and ``output_tokens`` at the given prices per million tokens."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts are not negative")
    return (input_tokens * pricing.input_per_million + output_tokens * pricing.output_per_million) / MILLION
