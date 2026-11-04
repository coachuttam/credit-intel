"""An offline dry run: what a document would send, without sending anything (PRD G5, B1).

Ingests and locates a document and checks the configured basis, then works out, from the
real candidate pages, the conservative input estimate, the reservation per call, a suggested
token ceiling and the worst-case spend at the configured prices. It needs no network and no
key and calls no model. The output is counts only: page numbers and sizes, never text.

    uv run --locked python -m credit_intel.evaluation.dry_run <pdf> [--basis consolidated|standalone] [--pages 1-5] [--assert-basis consolidated|standalone]
"""

import argparse
import json
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

from credit_intel.config import ENV_TOKEN_CEILING, ENV_USE_JEV, JevSettings, LLMSettings, PricingSettings, load_jev_settings, load_llm_settings, load_pricing
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, file_sha256, load_current_sets, refuse_if_held_out
from credit_intel.extraction.assertion import apply_assertion
from credit_intel.extraction.extract import render_pages
from credit_intel.extraction.bases import drop_unknown_basis_pages
from credit_intel.extraction.prompt import load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.locator import check_statement_basis, locate_statements
from credit_intel.llm.budget import estimate_tokens
from credit_intel.llm.cost import estimate_cost
from credit_intel.models import StatementBasis
from credit_intel.pagefilter.jev import page_state, question_text


def dry_run(
    path: Path,
    llm: LLMSettings,
    *,
    basis: str = "consolidated",
    page_range: str | None = None,
    pricing: PricingSettings | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    assert_basis: str | None = None,
    jev: JevSettings | None = None,
    jev_all_pages: bool = False,
    allow_unused_held_out: bool = False,
) -> dict:
    """Counts and estimates for one document. Raises ``IngestionError`` for an unreadable input.

    ``jev`` adds the estimate for the optional page classifier (PRD v0.4.31): how many pages it would read (the candidates, or every
    page with text if ``jev_all_pages``), the conservative input tokens and, if a price is set, the cost. Nothing is called.

    ``assert_basis`` is the analyst's assertion for the pages of ``page_range`` (H.4.6, v0.4.24); it needs a page range. A page whose
    title names the other basis stops the gate here, as it would stop the run, and the result says which pages the assertion covers.

    ``allow_unused_held_out`` skips the refusal of a held-out document; it is for the setup check alone (``setupcheck``, owner's decision
    of 2026-11-05), which makes its own check that the document is held out and unused. The command line of this module never sets it.
    """
    if assert_basis is not None and page_range is None:
        raise ValueError("an assertion of the basis needs a page range")
    try:
        if not allow_unused_held_out:  # only the setup check (S-4) sets this, and only after its own guard has shown the document is unused
            refuse_if_held_out(file_sha256(path), assignments)  # before any page is read (PRD O.2)
    except OSError:
        pass  # an unreadable file is reported by ingest below, as a catalogued error
    document = ingest(path)  # validates the file and hashes it; an unreadable input is a catalogued error
    sha256 = document.file_info.sha256
    known = load_current_sets(assignments).get(sha256)
    located = locate_statements(document.pages, None, page_range)
    candidates = sorted(c.page_number for c in located.candidates)
    removed: list[int] = []
    gate: dict = {"passes": None, "error_code": None, "detail": None}
    assertion = None
    if candidates:
        try:
            if assert_basis is not None:
                assertion = apply_assertion({p.page_number: p for p in document.pages}, located, StatementBasis(assert_basis))
            check_statement_basis(
                document.pages, located, basis,
                asserted_basis=assertion.basis.value if assertion is not None and assertion.applied_pages else None,
            )  # fmt: skip
            gate["passes"] = True
            before = candidates
            located = drop_unknown_basis_pages({p.page_number: p for p in document.pages}, located)  # H.4.6, v0.4.21
            candidates = sorted(c.page_number for c in located.candidates)
            removed = [n for n in before if n not in candidates]
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
        "removed_for_unknown_basis": removed,
        "configured_basis": basis,
        "basis_gate": gate,
        "basis_assertion": None if assertion is None else {"basis": assertion.basis.value, "pages": list(assertion.pages), "applied_pages": list(assertion.applied_pages)},
        "asserted_basis": assert_basis,
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
    if jev is not None:
        read = [p for p in document.pages if p.has_text] if jev_all_pages else [by_number[n] for n in candidates]
        overhead = estimate_tokens(question_text())
        tokens = sum(estimate_tokens(page_state(p.text, jev.state_lines)) + overhead for p in read)
        result["jev"] = {
            "model": jev.model,
            "pages_read": len(read),
            "all_pages": jev_all_pages,
            "state_lines": jev.state_lines,
            "estimated_input_tokens": tokens,
            "estimated_cost_usd": None if jev.price_input_per_million is None else format(Decimal(tokens) * jev.price_input_per_million / Decimal(1_000_000), "f"),
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
    parser.add_argument("--assert-basis", choices=("consolidated", "standalone"), default=None, help="the analyst's assertion for the pages of --pages (needs --pages)")
    parser.add_argument("--jev", action="store_true", help="also estimate the optional Jev page classifier (reads the candidate pages)")
    parser.add_argument("--jev-all-pages", action="store_true", help="with --jev: estimate reading every page with text")
    args = parser.parse_args(argv)
    if args.assert_basis and not args.pages:
        parser.error("--assert-basis requires --pages")
    try:
        # The dry run makes no call, so it needs no ceiling; a placeholder satisfies the loader.
        llm = load_llm_settings(env={**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1")})
        jev = load_jev_settings(env={**os.environ, ENV_USE_JEV: "true"}) if args.jev or args.jev_all_pages else None
        result = dry_run(args.pdf, llm, basis=args.basis, page_range=args.pages, pricing=load_pricing(), assert_basis=args.assert_basis,
                         jev=jev, jev_all_pages=args.jev_all_pages)  # fmt: skip
    except SendRefused as refusal:
        print(f"dry run: refused ({refusal})", file=sys.stderr)
        return 1
    except IngestionError as error:
        print(f"dry run: stopped {error.code.value}", file=sys.stderr)
        return 1
    print("dry run: " + json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
