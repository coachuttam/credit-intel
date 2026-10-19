"""Failures of a hosted LLM call (PRD FR-011.3, G.1).

The messages are fixed and safe: they hold at most an HTTP status code, never the key, a
request, a reply or the provider's own error text.
"""


class LLMTransientError(Exception):
    """A timeout, rate limit or server error that may succeed if tried again (FR-011.3)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"The LLM request failed temporarily ({reason}).")
        self.reason = reason


class LLMRequestError(Exception):
    """The provider refused the request itself (a bad request, an unknown model, an
    unusable reply). Trying again cannot help; this is an internal error, not catalogued."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"The LLM request was refused or unusable ({reason}).")
        self.reason = reason
