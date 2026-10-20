"""An offline dry run: what a document would send, without sending anything (PRD G5, B1).

Ingests and locates a document and checks the configured basis, then works out, from the
real candidate pages, the conservative input estimate, the reservation per call, a suggested
token ceiling and the worst-case spend at the configured prices. It needs no network and no
key and calls no model. The output is counts only: page numbers and sizes, never text.

    uv run --locked python -m credit_intel.evaluation.dry_run <pdf> [--basis consolidated|standalone] [--pages 1-5]
"""

import argparse
import json
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

from credit_intel.config import ENV_TOKEN_CEILING, LLMSettings, PricingSettings, load_llm_settings, load_pricing
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, load_current_sets
from credit_intel.extraction.extract import render_pages
from credit_intel.extraction.prompt import load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import check_statement_basis, locate_statements
from credit_intel.llm.budget import estimate_tokens
from credit_intel.llm.cost import estimate_cost


def dry_run(
    path: Path,
    llm: LLMSettings,
    *,
    basis: str = "consolidated",
    page_range: str | None = None,
    pricing: PricingSettings | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
) -> dict:
    """Counts and estimates for one document. Raises ``IngestionError`` for an unreadable input."""
    document = ingest(path)  # validates the file and hashes it; an unreadable input is a catalogued error
    sha256 = document.file_info.sha256
    known = load_current_sets(assignments).get(sha256)
    located = locate_statements(document.pages, None, page_range)
    candidates = sorted(c.page_number for c in located.candidates)
    gate: dict = {"passes": None, "error_code": None, "detail": None}
    if candidates:
        try:
            check_statement_basis(document.pages, located, basis)
            gate["passes"] = True
        except IngestionError as error:
            gate.update(passes=False, error_code=error.code.value, detail=error.detail)
    else:
        gate.update(passes=False, error_code="E-EXTRACT-NO-STATEMENT-PAGES")

    by_number = {p.page_number: p for p in document.pages}
    page_chars = {n: len(by_number[n].text) for n in candidates}
    prompt = load_prompt()
    estimate = estimate_tokens(prompt.system + render_pages(document, tuple(candidates))) if candidates else None
    reservation = None if estimate is None else estimate + llm.max_output_tokens
    ceiling = None if reservation is None else math.ceil(2 * reservation / 10_000) * 10_000
    result = {
        "document_id": known[0] if known else None,
        "set": known[1] if known else None,
        "sha256_prefix": sha256[:12],
        "pages": document.file_info.page_count,
        "pages_with_text": sum(1 for p in document.pages if p.has_text),
        "locator": located.method,
        "candidate_pages": candidates,
        "candidate_chars": page_chars,
        "candidate_chars_total": sum(page_chars.values()),
        "excluded_candidates": len(located.excluded_candidates),
        "configured_basis": basis,
        "basis_gate": gate,
        "prompt_version": prompt.version,
        "max_output_tokens": llm.max_output_tokens,
        "input_estimate_tokens": estimate,
        "reservation_per_call": reservation,
        "reservation_two_calls": None if reservation is None else 2 * reservation,
        "suggested_ceiling": ceiling,
        "worst_case_usd_one_call": None,
        "worst_case_usd_two_calls": None,
        "ceiling_bound_usd": None,
    }
    if pricing is not None and estimate is not None:
        one = estimate_cost(estimate, llm.max_output_tokens, pricing)
        result["worst_case_usd_one_call"] = str(one)
        result["worst_case_usd_two_calls"] = str(one * 2)
        result["ceiling_bound_usd"] = str(Decimal(ceiling) * pricing.output_per_million / Decimal(1_000_000))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--basis", choices=("consolidated", "standalone"), default="consolidated")
    parser.add_argument("--pages", default=None)
    args = parser.parse_args(argv)
    try:
        # The dry run makes no call, so it needs no ceiling; a placeholder satisfies the loader.
        llm = load_llm_settings(env={**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1")})
        result = dry_run(args.pdf, llm, basis=args.basis, page_range=args.pages, pricing=load_pricing())
    except IngestionError as error:
        print(f"dry run: stopped {error.code.value}", file=sys.stderr)
        return 1
    print("dry run: " + json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
