"""Assembling the memo (PRD FR-009, FR-010.2; Phase 5 step 5f onwards)."""

from typing import Any

from credit_intel.memo import sections


def render_head(results: dict[str, Any], run_id: str, generated_at: str) -> str:
    """The header and sections 1 to 4. Sections 5 to 9 are added by the next steps of Phase 5."""
    parts = [
        *sections.header(results, run_id, generated_at),
        *sections.section_1(results),
        *sections.section_2(results, generated_at),
        *sections.section_3(results),
        *sections.section_4(results),
    ]  # fmt: skip
    return "\n".join(parts).rstrip("\n") + "\n"
