"""Assembling the memo (PRD FR-009, FR-010.2; Phase 5 step 5f onwards)."""

from typing import Any

from credit_intel.memo import limitations, questions, sections


def _head_parts(results: dict[str, Any], run_id: str, generated_at: str) -> list[str]:
    return [
        *sections.header(results, run_id, generated_at),
        *sections.section_1(results),
        *sections.section_2(results, generated_at),
        *sections.section_3(results),
        *sections.section_4(results),
    ]


def render_head(results: dict[str, Any], run_id: str, generated_at: str) -> str:
    """The header and sections 1 to 4."""
    return "\n".join(_head_parts(results, run_id, generated_at)).rstrip("\n") + "\n"


def render_memo(results: dict[str, Any], run_id: str, generated_at: str) -> str:
    """The whole memo: the header and the nine sections of K.1 to K.9, as CommonMark with one final newline."""
    parts = [
        *_head_parts(results, run_id, generated_at), "",
        *sections.section_5(results),
        *sections.section_6(results),
        *sections.section_7(results),
        *questions.section_8(results),
        *limitations.section_9(results),
    ]  # fmt: skip
    return "\n".join(parts).rstrip("\n") + "\n"
