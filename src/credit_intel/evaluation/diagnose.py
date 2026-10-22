"""An offline diagnosis of a tuning run from its cached reply, counts only (PRD Phase 2 G5, O.2).

Replays a run whose model reply is already in the response cache, so nothing is sent: the
provider given to the pipeline refuses to be called, and a cache miss is reported, not
retried. It then explains, with counts, enum names and booleans only, why the verifier
accepted or refused what the model proposed: per candidate page its structure, per proposed
attribute which period check failed, per proposed field how far verification would have got.
It prints no page text, quote, label, value or date.

    uv run --locked python -m credit_intel.evaluation.diagnose <pdf> [--basis consolidated|standalone]

Use the same CREDIT_INTEL_MAX_OUTPUT_TOKENS and CREDIT_INTEL_PROMPT as the run being replayed (both are part of the cache key).
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from credit_intel.config import ENV_TOKEN_CEILING, LLMSettings, load_llm_settings
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, check_may_send, file_sha256
from credit_intel.extraction.assignment import ColumnClaim, check_column, link_quote
from credit_intel.extraction.attributes import _header_lines, _presence_reason
from credit_intel.extraction.columns import analyse_structure
from credit_intel.extraction.periods import classify, find_full_dates, page_period_resolver, resolve_anchor_texts
from credit_intel.extraction.pipeline import run_extraction
from credit_intel.extraction.prompt import DEFAULT_PROMPT, Prompt, load_prompt
from credit_intel.extraction.presence import check_presence, normalise_for_match
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.locator import is_figure_word, lines_of
from credit_intel.ingestion.ingest import ingest
from credit_intel.ingestion.pdfplumber_extractor import PdfplumberExtractor
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.provider import LLMRequest, LLMResponse
from credit_intel.models import DocumentAttributeName, PeriodRole, StatementBasis


class _NoCallProvider:
    """Stands in for the real provider: replaying must never make a request."""

    name = "openai"
    retries = 0

    def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover - guarded by a test
        raise RuntimeError("diagnose is offline: the reply was not in the cache")


def _page_report(number, page_text, words, run) -> dict:
    resolver = page_period_resolver(
        words, page_text, None, None, known_current=run.attributes.period_end(PeriodRole.CURRENT)
    )
    structure = analyse_structure(words, resolver)
    return {
        "page": number,
        "rotation": words.rotation,
        "word_count": len(words.words),
        "line_count": len(structure.lines),
        "header_lines": structure.header_last - structure.header_first,
        "header_lines_normalised_nonempty": sum(1 for line in _header_lines(page_text) if line),
        "full_dates_in_text": len(find_full_dates(page_text)),
        "anchors": [
            {"kind": a.kind, "form": classify(a.text).value, "validated": a.period_end is not None}
            for a in structure.anchors
        ],
        "columns": len(structure.columns),
        "problems": [p.value for p in structure.problems],
        "note_span": structure.note_span is not None,
    }, structure


def _char_class(char: str | None) -> str:
    if char is None:
        return "edge"
    if char.isdigit():
        return "digit"
    if char.isalpha():
        return "letter"
    return "space" if char.isspace() else "punctuation"


def _position_report(raw_text: str, page_text: str) -> dict:
    """Where the period text sits on the page, by line numbers and character classes only."""
    lines = lines_of(page_text)
    first_figure = next(
        (i for i, line in enumerate(lines) if any(is_figure_word(w) for w in line.split())), len(lines)
    )
    raw = normalise_for_match(raw_text)
    holding = [i for i, line in enumerate(lines) if raw in normalise_for_match(line)]
    flat = normalise_for_match(page_text)
    at = flat.find(raw)
    return {
        "page_line_count": len(lines),
        "first_figure_line": first_figure,
        "lines_holding_raw_text": holding,
        "raw_text_occurrences": flat.count(raw) if raw else 0,
        "char_before": _char_class(flat[at - 1] if at > 0 else None) if at >= 0 else None,
        "char_after": _char_class(flat[at + len(raw)] if 0 <= at and at + len(raw) < len(flat) else None),
        "page_scan_finds_the_date": any(d.isoformat() for d in find_full_dates(page_text)),
    }


def _quote_report(proposal, page_text: str) -> dict:
    """How far a quote that is not on its page agrees with it, by lengths only."""
    quote, raw, flat = (normalise_for_match(x) for x in (proposal.evidence_quote, proposal.raw_text, page_text))
    prefix = 0
    while prefix < len(quote) and quote[: prefix + 1] in flat:
        prefix += 1
    return {
        "quote_chars": len(quote),
        "quote_longest_prefix_on_page_chars": prefix,
        "quote_lines": len(proposal.evidence_quote.splitlines()),
        "raw_text_chars": len(raw),
        "raw_text_in_quote": raw in quote,
        "raw_text_on_page": raw in flat,
    }


def _attribute_report(proposal, pages, known_current) -> dict:
    report = {
        "attribute": proposal.attribute.value,
        "role": proposal.period_role.value if proposal.period_role else None,
        "page": proposal.page_number,
        "page_is_candidate": proposal.page_number in pages,
        "presence_reason": None,
    }
    reason = _presence_reason(proposal, pages)
    report["presence_reason"] = reason.value if reason else None
    if reason is not None and proposal.page_number in pages:
        report.update(_quote_report(proposal, pages[proposal.page_number]))
    if proposal.attribute is DocumentAttributeName.PERIOD_END:
        report["form"] = classify(proposal.raw_text).value
        if reason is None:
            page_text = pages[proposal.page_number]
            raw = normalise_for_match(proposal.raw_text)
            report["raw_text_in_header_lines"] = any(raw in line for line in _header_lines(page_text))
            report.update(_position_report(proposal.raw_text, page_text))
            found = resolve_anchor_texts([proposal.raw_text], page_text, known_current)[proposal.raw_text]
            report["resolved"] = found.evidence is not None
            report["resolution_reason"] = found.reason.value if found.reason else None
            report["resolution_method"] = found.evidence.method.value if found.evidence else None
            report["resolved_date_equals_proposed"] = (
                found.evidence is not None
                and found.evidence.period_end.isoformat() == (proposal.normalised_value or "").strip()
            )
    return report


def _field_report(proposed, pages, structures, run, columns_periods) -> dict:
    presence = check_presence(
        {n: t for n, t in pages.items()}, proposed.page_number, proposed.evidence_quote, proposed.raw_value
    )
    report = {
        "field": proposed.field_name.value,
        "role": proposed.period_role.value,
        "page": proposed.page_number,
        "page_is_candidate": proposed.page_number in pages,
        "evidence_verified": presence.evidence_verified,
        "value_in_evidence": presence.value_in_evidence,
    }
    structure = structures.get(proposed.page_number)
    if structure is None:
        report["structure"] = None
        return report
    report["structure_problems"] = [p.value for p in structure.problems]
    failure, line = link_quote(proposed.raw_value, proposed.evidence_quote, structure)
    report["link_failure"] = failure.value if failure else None
    # What-if: had the period attribute been accepted as proposed, how far would the column check get?
    attribute = (
        run.attributes.current_period_end
        if proposed.period_role is PeriodRole.CURRENT
        else run.attributes.comparative_period_end
    )
    try:
        claimed = date.fromisoformat((attribute.normalised_value or "").strip())
    except ValueError:
        claimed = None
    report["claimed_period_has_column_on_page"] = (
        claimed is not None and claimed in columns_periods.get(proposed.page_number, ())
    )
    if claimed is not None:  # how far each column's period-end is from the claimed one, in days
        report["column_day_offsets_from_claimed"] = sorted(
            (c - claimed).days for c in columns_periods.get(proposed.page_number, ())
        )
    if claimed is not None:
        check = check_column(structure, ColumnClaim(claimed, proposed.raw_value, proposed.evidence_quote, True))
        report["what_if_column_outcome"] = check.outcome.value
        report["what_if_column_failure"] = check.failure.value if check.failure else None
    return report


def diagnose(
    path: Path,
    basis: StatementBasis = StatementBasis.CONSOLIDATED,
    *,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    llm: LLMSettings | None = None,
    prompt: Prompt | None = None,
) -> dict:
    document_id = check_may_send(file_sha256(path), assignments)  # same rule as a send, though nothing is sent
    llm = llm or load_llm_settings(env={**os.environ, ENV_TOKEN_CEILING: os.environ.get(ENV_TOKEN_CEILING, "1000000")})
    try:
        run = run_extraction(path, _NoCallProvider(), llm, basis=basis, cache_dir=cache_dir, prompt=prompt)
    except RuntimeError:
        return {"document_id": document_id, "replayed": False, "cache_hits": 0}
    candidates = sorted(c.page_number for c in run.located.candidates)
    document = ingest(path)
    text = {p.page_number: p.text for p in document.pages if p.page_number in candidates}
    words = {w.page_number: w for w in PdfplumberExtractor().extract_words(path, candidates)}
    pages_out, structures, column_periods = [], {}, {}
    for number in candidates:
        if number in words:
            page_report, structure = _page_report(number, text[number], words[number], run)
            pages_out.append(page_report)
            structures[number] = structure
            column_periods[number] = {c.period_end for c in structure.columns}
    response = run.extraction.response
    known = run.attributes.period_end(PeriodRole.CURRENT)
    return {
        "document_id": document_id,
        "replayed": True,
        "cache_hits": run.stats.cache_hits,
        "candidate_pages": candidates,
        "pages": pages_out,
        "attribute_proposals": [_attribute_report(p, text, known) for p in response.attributes],
        "field_proposals": [_field_report(f, text, structures, run, column_periods) for f in response.fields],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--basis", choices=("consolidated", "standalone"), default="consolidated")
    args = parser.parse_args(argv)
    try:
        result = diagnose(args.pdf, StatementBasis(args.basis), prompt=load_prompt(os.environ.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT)))
    except IngestionError as error:
        print(f"diagnose: stopped {error.code.value}", file=sys.stderr)
        return 1
    print("diagnose: " + json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
