"""Local LLM response cache (PRD FR-003.5).

One file ``<key>.json`` per entry under ``.cache/llm/`` (git-ignored). The key is
the SHA-256 of the canonical JSON of every input that can affect the response.
The entry holds that input object, the raw response text, token usage and the
UTC creation time; it never holds credentials or request headers.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from credit_intel.llm.provider import LLMResponse, LLMUsage, canonical_json

DEFAULT_CACHE_DIR = Path(".cache/llm")


@dataclass(frozen=True)
class CacheKeyInputs:
    """Every input that can affect the response (FR-003.5)."""

    document_sha256: str
    candidate_pages: tuple[int, ...]  # in order: order is part of the prompt
    provider: str
    model_id: str
    prompt_version: str
    schema_version: str
    temperature: int
    max_output_tokens: int
    structured_output_mode: str
    # Not in the FR-003.5 list: a corrective retry (FR-004.1) sends the validation
    # error with the same pages, so without this it would collide with the first
    # call's key and replay the invalid response. None for the first attempt.
    corrective_feedback_sha256: str | None = None

    def to_object(self) -> dict[str, object]:
        return {
            "document_sha256": self.document_sha256,
            "candidate_pages": list(self.candidate_pages),
            "provider": self.provider,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "corrective_feedback_sha256": self.corrective_feedback_sha256,
            "generation": {
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
                "structured_output_mode": self.structured_output_mode,
            },
        }

    def key(self) -> str:
        return hashlib.sha256(canonical_json(self.to_object()).encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ResponseCache:
    def __init__(
        self, directory: Path = DEFAULT_CACHE_DIR, now: Callable[[], datetime] = _utc_now
    ) -> None:
        self.directory = directory
        self._now = now
        self.hits = 0
        self.misses = 0

    def _path(self, inputs: CacheKeyInputs) -> Path:
        return self.directory / f"{inputs.key()}.json"

    def get(self, inputs: CacheKeyInputs) -> LLMResponse | None:
        """A readable entry whose stored input object equals the current one is a hit.

        Anything else (no entry, unreadable, malformed, or differing inputs) is a miss.
        """
        response = self._read(inputs)
        if response is None:
            self.misses += 1
        else:
            self.hits += 1
        return response

    def _read(self, inputs: CacheKeyInputs) -> LLMResponse | None:
        try:
            entry = json.loads(self._path(inputs).read_text(encoding="utf-8"))
            if entry["inputs"] != inputs.to_object():
                return None
            text = entry["response_text"]
            usage = entry["usage"]
            input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
            return None
        valid_counts = all(
            isinstance(n, int) and not isinstance(n, bool) and n >= 0
            for n in (input_tokens, output_tokens)
        )
        if not isinstance(text, str) or not valid_counts:
            return None
        return LLMResponse(text, LLMUsage(input_tokens, output_tokens))

    def put(self, inputs: CacheKeyInputs, response: LLMResponse) -> None:
        """Write the entry atomically (temporary file, then rename), replacing any old one."""
        entry = {
            "inputs": inputs.to_object(),
            "response_text": response.text,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "created_at": self._now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self.directory, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(canonical_json(entry))
            os.replace(temp_name, self._path(inputs))
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
