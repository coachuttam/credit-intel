"""Provider interface and the offline fake provider (PRD FR-003, D-02, FR-003.6).

The interface is deliberately small: one blocking call that takes a prepared
request and returns the raw response text with the provider's reported usage.
Prompt construction, parsing and validation live elsewhere.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from credit_intel.llm.budget import estimate_tokens

# Generation settings that are fixed rather than configurable. Temperature 0 gives
# the most repeatable output, and both values are part of the cache key (FR-003.5).
TEMPERATURE = 0
STRUCTURED_OUTPUT_MODE = "json_schema"


@dataclass(frozen=True)
class LLMRequest:
    """One prepared call. ``system`` and ``user`` are the full prompt texts."""

    system: str
    user: str
    model_id: str
    max_output_tokens: int
    temperature: int = TEMPERATURE
    structured_output_mode: str = STRUCTURED_OUTPUT_MODE

    @property
    def prompt_text(self) -> str:
        return self.system + self.user

    def fingerprint(self) -> str:
        """SHA-256 of the canonical JSON of every field; keys recorded fake replies."""
        payload = {
            "system": self.system,
            "user": self.user,
            "model_id": self.model_id,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "structured_output_mode": self.structured_output_mode,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: LLMUsage


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...


def canonical_json(value: object) -> str:
    """Keys sorted, no insignificant whitespace, UTF-8 characters kept (FR-003.5)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class FakeReply:
    """A scripted reply; usage defaults to the deterministic character estimate."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class FakeProviderError(Exception):
    """A fake provider was asked for a reply it does not have (a test-setup error)."""


class FakeProvider:
    """Deterministic provider for tests; makes no network access.

    Replies come from a recorded mapping (request fingerprint to reply) when the
    request is in it, otherwise from the script in order. Every request is kept in
    ``calls``. A request with neither a recording nor a scripted reply left raises
    ``FakeProviderError``, so a test never silently gets a default.
    """

    def __init__(
        self,
        script: Sequence[FakeReply | str] = (),
        recorded: Mapping[str, FakeReply | str] | None = None,
    ) -> None:
        self._script = [self._reply(item) for item in script]
        self._recorded = {key: self._reply(item) for key, item in (recorded or {}).items()}
        self.calls: list[LLMRequest] = []

    @staticmethod
    def _reply(item: FakeReply | str) -> FakeReply:
        return FakeReply(item) if isinstance(item, str) else item

    @classmethod
    def from_recording(cls, path: Path) -> "FakeProvider":
        """Load ``{fingerprint: response text}`` recorded from earlier runs."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(recorded=data)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        reply = self._recorded.get(request.fingerprint())
        if reply is None:
            if not self._script:
                raise FakeProviderError("no recorded or scripted reply for this request")
            reply = self._script.pop(0)
        input_tokens = reply.input_tokens
        if input_tokens is None:
            input_tokens = estimate_tokens(request.prompt_text)
        output_tokens = reply.output_tokens
        if output_tokens is None:
            output_tokens = estimate_tokens(reply.text)
        return LLMResponse(reply.text, LLMUsage(input_tokens, output_tokens))
