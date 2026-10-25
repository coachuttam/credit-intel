"""Jev + OpenAI against OpenAI-only on one tuning document, counts only (PRD v0.4.31, success criteria of section 10).

Two modes, one command each:

* ``estimate`` (the default, offline, free): the pages that would be read, the Jev tokens and cost, and the worst case of the extra
  OpenAI call. Nothing is sent and no key is needed.
* ``--live --max-spend USD``: runs both modes on the document with the same pages, assertion, prompt and limits, then compares them.
  It refuses before any call if the maximum spend is below the worst case, if the document is held out, is not a recorded tuning
  document, or is under ``private/`` without ``CREDIT_INTEL_PRIVATE_APPROVED=1``. The OpenAI-only mode is served from the response
  cache when an earlier identical run left its reply there.

The output is one line of numbers and enum names: tokens, costs, latency, statuses, counts of matches. It holds no page text, quote,
label text or figure. ``--reference`` adds the gate's match / mismatch / missing counts for each mode (the owner's reference file is
read by the gate's own loader and never printed).

    uv run --locked python -m credit_intel.evaluation.jev_eval <pdf> [--basis B] [--pages R] [--assert-basis B] [--reference FILE]
        [--all-pages] [--order forward|reversed] [--live --max-spend USD]
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from credit_intel.config import (
    DEFAULT_SETTINGS_PATH,
    ENV_TOKEN_CEILING,
    ENV_USE_JEV,
    JevSettings,
    LLMSettings,
    PricingSettings,
    load_jev_settings,
    load_llm_settings,
    load_pricing,
)
from credit_intel.evaluation.dry_run import dry_run
from credit_intel.evaluation.gate import GateReferenceError, Reference, compare, load_reference
from credit_intel.evaluation.guard import ASSIGNMENTS_PATH, SendRefused, check_may_send, check_private_path, file_sha256, refuse_if_held_out
from credit_intel.extraction.bases import page_basis
from credit_intel.extraction.pipeline import ExtractionRun, run_extraction
from credit_intel.extraction.prompt import DEFAULT_PROMPT, Prompt, load_prompt
from credit_intel.ingestion.errors import IngestionError
from credit_intel.ingestion.ingest import ingest
from credit_intel.llm.cache import DEFAULT_CACHE_DIR
from credit_intel.llm.cost import estimate_cost
from credit_intel.llm.provider import LLMProvider
from credit_intel.models import FieldName, PeriodRole, StatementBasis, Status
from credit_intel.pagefilter.classifier import PageClassifier
from credit_intel.pagefilter.filter import PageFilterSetup
from credit_intel.pagefilter.labels import ClassifierError, PageBasis, PageType

GATE_FIELDS = (FieldName.PROFIT_BEFORE_TAX, FieldName.INTEREST_EXPENSE, FieldName.TOTAL_BORROWINGS)
# Which locator statement type a Jev page type corresponds to, for the agreement counts (the locator is not ground truth).
LOCATOR_TYPE = {PageType.BALANCE_SHEET: "balance_sheet", PageType.PROFIT_LOSS: "income_statement"}


def _extracted(run: ExtractionRun) -> set[tuple[str, str]]:
    return {(f.field_name.value, f.period_role.value) for f in run.field_set.fields if f.status is Status.EXTRACTED}


def _mode(run: ExtractionRun, reference: Reference | None, pricing: PricingSettings | None) -> dict:
    stats = run.stats
    # A reply served from the cache stands for the call it came from, so a cached mode and a live mode compare like with like.
    tokens_in, tokens_out = stats.input_tokens + stats.cached_input_tokens, stats.output_tokens + stats.cached_output_tokens
    gate_fields = {}
    for name in GATE_FIELDS:
        gate_fields[name.value] = {
            role.value: (record.status.value if (record := run.field_set.get(name, role)) is not None else "not_found")
            for role in (PeriodRole.CURRENT, PeriodRole.COMPARATIVE)
        }
    out = {
        "pages_sent": sorted(c.page_number for c in run.located.candidates),
        "openai_calls": stats.llm_calls,
        "cache_hits": stats.cache_hits,
        "openai_input_tokens": tokens_in,
        "openai_output_tokens": tokens_out,
        "openai_billed_input_tokens": stats.input_tokens,
        "openai_cost_usd": None if pricing is None else format(estimate_cost(tokens_in, tokens_out, pricing), "f"),
        "fields_extracted": len(_extracted(run)),
        "field_counts": dict(run.field_set.counts),
        "gate_fields": gate_fields,
    }
    if reference is not None:
        out["gate_counts"] = compare(reference, run.field_set)["counts"]
    return out


def _page_agreement(run: ExtractionRun, locator_types: Mapping[int, tuple[str, ...]], page_texts: Mapping[int, str]) -> dict:
    """How often Jev's labels agree with the locator's statement types and with the page's own title (counts; neither is ground truth)."""
    outcome = run.page_filter
    types = locator_types
    type_total = type_agree = basis_total = basis_agree = 0
    if outcome is not None:
        for record in outcome.records:
            if record.model_id is None:
                continue
            wanted = LOCATOR_TYPE.get(PageType(record.page_type))
            if types.get(record.page_number):
                type_total += 1
                type_agree += int(wanted in types[record.page_number])
            own = page_basis(page_texts.get(record.page_number, ""))
            if own is not None and own is not StatementBasis.UNKNOWN:
                basis_total += 1
                basis_agree += int(PageBasis(record.basis).value == own.value)
    return {"type_compared": type_total, "type_agree": type_agree, "basis_compared": basis_total, "basis_agree": basis_agree}


def _locator_misses(classifier: PageClassifier, pages: Mapping[int, str], candidates: set[int], settings: JevSettings) -> dict:
    """Classify the pages the locator did not select: how many Jev is sure are statements (the locator may have missed them)."""
    sure, errors = [], 0
    for number in sorted(set(pages) - candidates):
        if not pages[number].strip():
            continue
        try:
            label = classifier.classify(number, pages[number])
        except ClassifierError:
            errors += 1
            continue
        if label.page_type in LOCATOR_TYPE and label.type_confidence >= settings.threshold:
            sure.append(number)
    return {"classified_outside_candidates": len(set(pages) - candidates), "statement_pages_found": sure, "errors": errors}


def verdict(plain: dict, jev: dict, reference_given: bool) -> dict:
    """The five success criteria of the proposal, as booleans or numbers, from the two modes' numbers."""
    a, b = plain["openai"], jev["openai"]
    lost = sorted(set(map(tuple, plain["extracted_fields"])) - set(map(tuple, jev["extracted_fields"])))
    gained = sorted(set(map(tuple, jev["extracted_fields"])) - set(map(tuple, plain["extracted_fields"])))
    out = {
        "fields_not_lost": not lost,
        "fields_lost": len(lost),
        "fields_gained": len(gained),
        "openai_input_tokens_delta": b["openai_input_tokens"] - a["openai_input_tokens"],
        "openai_input_tokens_lower": b["openai_input_tokens"] < a["openai_input_tokens"],
        "pages_dropped": jev["page_filter"]["pages_dropped"],
        "fallbacks": jev["page_filter"]["fallbacks"],
    }
    if reference_given:
        ac, bc = a["gate_counts"], b["gate_counts"]
        out["matches_not_lost"] = bc["match"] >= ac["match"] and bc["mismatch"] <= ac["mismatch"]
    if a["openai_cost_usd"] is not None and b["openai_cost_usd"] is not None and jev["page_filter"]["jev_cost_usd"] is not None:
        total_a = Decimal(a["openai_cost_usd"])
        total_b = Decimal(b["openai_cost_usd"]) + Decimal(jev["page_filter"]["jev_cost_usd"])
        out["total_cost_usd_openai_only"] = format(total_a, "f")
        out["total_cost_usd_jev_plus_openai"] = format(total_b, "f")
        out["total_cost_lower"] = total_b < total_a
    out["latency_added_ms"] = jev["page_filter"]["latency_ms"]
    return out


def evaluate(
    path: Path,
    llm: LLMSettings,
    provider: LLMProvider,
    classifier: PageClassifier,
    jev: JevSettings,
    *,
    basis: StatementBasis = StatementBasis.CONSOLIDATED,
    page_range: str | None = None,
    assert_basis: StatementBasis | None = None,
    pricing: PricingSettings | None = None,
    reference: Reference | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    prompt: Prompt | None = None,
    env: Mapping[str, str] | None = None,
    all_pages: bool = False,
) -> dict:
    """Run OpenAI-only and Jev + OpenAI on a tuning document and compare them. Raises ``SendRefused`` before any call for a document that may not be sent."""
    env = os.environ if env is None else env
    sha256 = file_sha256(path)
    refuse_if_held_out(sha256, assignments)
    check_private_path(path, env)
    document_id = check_may_send(sha256, assignments)  # tuning documents only
    if reference is not None and (reference.sha256 != sha256 or reference.document_id != document_id):
        raise GateReferenceError("the reference was not written for this document")
    common = dict(basis=basis, page_range=page_range, cache_dir=cache_dir, prompt=prompt, assert_basis=assert_basis, pricing=pricing)
    plain_run = run_extraction(path, provider, llm, **common)
    setup = PageFilterSetup(jev, classifier, filter_page_ranges=True)  # a page range is filtered here only, to measure it
    jev_run = run_extraction(path, provider, llm, page_filter=setup, **common)
    page_texts = {p.page_number: p.text for p in ingest(path).pages}
    filter_part = jev_run.page_filter.to_manifest() if jev_run.page_filter is not None else {}
    plain = {"openai": _mode(plain_run, reference, pricing), "extracted_fields": sorted(_extracted(plain_run))}
    with_jev = {
        "openai": _mode(jev_run, reference, pricing),
        "extracted_fields": sorted(_extracted(jev_run)),
        "page_filter": {
            "model_ids": filter_part.get("model_ids", []), "calls": filter_part.get("calls", 0), "fallbacks": filter_part.get("fallbacks", 0),
            "jev_input_tokens": filter_part.get("input_tokens", 0), "jev_cost_usd": filter_part.get("estimated_cost_usd"),
            "latency_ms": filter_part.get("latency_ms", 0), "pages_dropped": filter_part.get("pages_dropped", []),
            "threshold": jev.threshold, "labels": [{k: p[k] for k in ("page", "decision", "fallback", "reason", "page_type", "type_confidence", "basis", "basis_confidence")} for p in filter_part.get("pages", [])],
        },
        "agreement": _page_agreement(jev_run, {c.page_number: c.statement_types for c in plain_run.located.candidates}, page_texts),
    }
    result = {
        "document_id": document_id,
        "configured_basis": basis.value,
        "pages_option": page_range,
        "asserted_basis": assert_basis.value if assert_basis else None,
        "prompt_version": plain_run.extraction.prompt_version,
        "openai_only": plain,
        "jev_plus_openai": with_jev,
        "verdict": verdict(plain, with_jev, reference is not None),
    }
    if all_pages:
        candidates = {c.page_number for c in jev_run.located.candidates} | {c.page_number for c in plain_run.located.candidates}
        result["locator_check"] = _locator_misses(classifier, page_texts, candidates, jev)
    return result


def worst_case_usd(estimate: dict) -> Decimal | None:
    """The most a live evaluation can cost: the Jev tokens plus one OpenAI call at its worst case (the OpenAI-only mode may be a cache hit)."""
    jev, one_call = estimate.get("jev", {}), estimate.get("worst_case_usd_one_call")
    if jev.get("estimated_cost_usd") is None or one_call is None:
        return None
    return Decimal(jev["estimated_cost_usd"]) + 2 * Decimal(one_call)  # both modes, if neither is cached


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    provider: LLMProvider | None = None,
    classifier: PageClassifier | None = None,
    assignments: Path = ASSIGNMENTS_PATH,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> int:
    env = dict(os.environ if env is None else env)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--basis", choices=("consolidated", "standalone"), default="consolidated")
    parser.add_argument("--pages", default=None)
    parser.add_argument("--assert-basis", choices=("consolidated", "standalone"), default=None)
    parser.add_argument("--reference", type=Path, default=None, help="the gate's reference file for this document (read, never printed)")
    parser.add_argument("--all-pages", action="store_true", help="also classify the pages the locator did not select (extra Jev cost)")
    parser.add_argument("--order", choices=("forward", "reversed"), default="forward")
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument("--live", action="store_true", help="make the calls (costs money); without it only the estimate is printed")
    parser.add_argument("--max-spend", default=None, help="USD ceiling for the whole evaluation; required with --live and must cover the worst case")
    args = parser.parse_args(argv)
    if args.assert_basis and not args.pages:
        parser.error("--assert-basis requires --pages")
    try:
        llm = load_llm_settings(args.config, {**env, ENV_TOKEN_CEILING: env.get(ENV_TOKEN_CEILING, "1")})  # an estimate makes no call: a placeholder ceiling
        jev = load_jev_settings(args.config, {**env, ENV_USE_JEV: "true"})
        pricing = load_pricing(args.config, env)
        estimate = dry_run(args.pdf, llm, basis=args.basis, page_range=args.pages, pricing=pricing, assert_basis=args.assert_basis, jev=jev, jev_all_pages=args.all_pages, assignments=assignments)
        if not args.live:
            print("jev eval estimate: " + json.dumps({**estimate, "worst_case_usd_evaluation": None if worst_case_usd(estimate) is None else format(worst_case_usd(estimate), "f")}, sort_keys=True))
            return 0
        worst = worst_case_usd(estimate)
        if worst is None:
            print("jev eval: refused (set both prices so the worst case can be bounded)", file=sys.stderr)
            return 1
        if args.max_spend is None or Decimal(args.max_spend) < worst:
            print(f"jev eval: refused (--max-spend must be at least the worst case, {format(worst, 'f')} USD)", file=sys.stderr)
            return 1
        reference = load_reference(args.reference) if args.reference else None
        llm = load_llm_settings(args.config, env)  # a live run needs the owner's real token ceiling (OD-8: no default)
        if provider is None:
            from credit_intel.llm.factory import build_provider

            provider = build_provider(llm, env)
        if classifier is None:
            from credit_intel.pagefilter.jev import JevClassifier

            classifier = JevClassifier(jev, env, order=args.order)
        result = evaluate(args.pdf, llm, provider, classifier, jev, basis=StatementBasis(args.basis), page_range=args.pages,
                          assert_basis=StatementBasis(args.assert_basis) if args.assert_basis else None, pricing=pricing, reference=reference,
                          assignments=assignments, cache_dir=cache_dir, prompt=load_prompt(env.get("CREDIT_INTEL_PROMPT", DEFAULT_PROMPT)), env=env, all_pages=args.all_pages)  # fmt: skip
    except SendRefused as refusal:
        print(f"jev eval: refused ({refusal})", file=sys.stderr)
        return 1
    except GateReferenceError as error:
        print(f"jev eval: reference problem ({error})", file=sys.stderr)
        return 1
    except IngestionError as error:
        print(f"jev eval: stopped {error.code.value}", file=sys.stderr)
        return 1
    print("jev eval: " + json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
