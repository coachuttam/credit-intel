"""Versioned extraction prompt (PRD FR-003.2).

Prompts are files under ``prompts/``. A file starts with a ``prompt-version: <id>``
line and a ``---`` line; the rest is the system prompt, with two placeholders that
are filled from the code so the prompt cannot drift from the schema: the JSON
schema of the response and the field list.
"""

from dataclasses import dataclass
from pathlib import Path

from credit_intel.llm.provider import canonical_json
from credit_intel.models import ExtractionResponse

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"
# The prompt a run uses unless the caller passes another. extraction_v2 became the default on
# 2026-10-20 at the owner's word, after the first live run showed the model shortening evidence
# quotes under v1 (see PROGRESS.md, G4); v1 stays on disk and is a different cache key.
DEFAULT_PROMPT = "extraction_v2"

# One line per extractable field (H.3). The label phrases that verification accepts
# are configuration and are deliberately not listed here.
FIELD_DESCRIPTIONS: dict[str, str] = {
    "revenue": "revenue from operations; excludes other income; total income is not revenue",
    "net_profit": "profit or loss for the period after tax, before attribution to non-controlling interests",
    "operating_profit": "operating profit, only if the statement reports it",
    "profit_before_tax": "profit or loss before tax",
    "interest_expense": "finance costs or interest expense",
    "current_assets": "total current assets",
    "current_liabilities": "total current liabilities",
    "total_borrowings": "a reported total of interest-bearing borrowings, excluding lease liabilities, only if the statement shows one",
    "borrowings_non_current": "borrowings under the non-current liabilities heading",
    "borrowings_current": "borrowings under the current liabilities heading",
    "current_maturities_long_term_borrowings": "current maturities of long-term borrowings, only when shown as its own row",
    "total_equity": "total equity",
}


class PromptError(Exception):
    """A prompt file is missing or malformed (a packaging error, not a user error)."""


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str


def render_fields() -> str:
    return "\n".join(f"- {name}: {text}" for name, text in FIELD_DESCRIPTIONS.items())


def load_prompt(name: str = DEFAULT_PROMPT, directory: Path = PROMPT_DIR) -> Prompt:
    try:
        text = (directory / f"{name}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromptError(f"cannot read prompt {name}") from exc
    header, separator, body = text.partition("\n---\n")
    prefix = "prompt-version:"
    if not separator or not header.startswith(prefix) or not header[len(prefix) :].strip():
        raise PromptError(f"prompt {name} has no version header")
    for placeholder in ("{{schema}}", "{{fields}}"):
        if body.count(placeholder) != 1:
            raise PromptError(f"prompt {name} must contain {placeholder} exactly once")
    schema = canonical_json(ExtractionResponse.model_json_schema())
    system = body.strip().replace("{{schema}}", schema).replace("{{fields}}", render_fields())
    return Prompt(version=header[len(prefix) :].strip(), system=system)
