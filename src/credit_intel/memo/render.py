"""Assembling the memo (PRD FR-009, FR-010.2; Phase 5 step 5f onwards)."""

from typing import Any

from credit_intel.memo import sections


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


def render_body(results: dict[str, Any], run_id: str, generated_at: str) -> str:
    """The header and sections 1 to 7. Sections 8 and 9 and the assembled memo are step 5h."""
    parts = [
        *_head_parts(results, run_id, generated_at), "",
        *sections.section_5(results),
        *sections.section_6(results),
        *sections.section_7(results),
    ]  # fmt: skip
    return "\n".join(parts).rstrip("\n") + "\n"
