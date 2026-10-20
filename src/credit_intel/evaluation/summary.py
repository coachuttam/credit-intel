"""Counts-only summaries of a run (PRD Phase 2 exit: "counts, not claims").

A summary holds page numbers, statuses, reason codes, field names, token counts and cost.
It never holds document text, quotes, labels or values, so it can be printed and pasted
without disclosing the document. A run that stops on a catalogued error is a result too.
"""

import json
from collections import Counter
from decimal import Decimal

from credit_intel.extraction.pipeline import ExtractionRun
from credit_intel.ingestion.errors import IngestionError
from credit_intel.models import Status


def _name(attribute) -> str:
    role = f".{attribute.period_role.value}" if attribute.period_role else ""
    return f"{attribute.attribute.value}{role}"


def summarise_run(run: ExtractionRun, document_id: str) -> dict:
    records = run.field_set.fields
    present = [r for r in records if r.status is not Status.NOT_FOUND]
    stats = run.stats
    return {
        "outcome": "completed",
        "document_id": document_id,
        "sha256_prefix": run.source_document.sha256[:12],
        "pages": run.page_count,
        "locator": run.located.method,
        "candidate_pages": sorted(c.page_number for c in run.located.candidates),
        "excluded_candidates": len(run.located.excluded_candidates),
        "excluded_by_reason": dict(sorted(Counter(e.reason for e in run.located.excluded_candidates).items())),
        "configured_basis": run.configured_basis.value,
        "fields": {
            "counts": run.field_set.counts,
            "reasons": dict(sorted(Counter(r.status_reason.value for r in records if r.status_reason).items())),
            "by_basis": dict(sorted(Counter(r.statement_basis.value for r in present).items())),
            "ignored_other_basis": len(run.field_set.ignored),
            "unplaced": len(run.field_set.unplaced),
            "proposed": len(run.extraction.response.fields),
            "outcomes": sorted(
                f"{r.field_name.value}/{r.period_role.value}/{r.statement_basis.value}: {r.status.value}"
                + (f" ({r.status_reason.value})" if r.status_reason else "")
                for r in present
            ),
        },
        "attributes": {
            _name(a): a.status.value + (f" ({a.status_reason.value})" if a.status_reason else "")
            for a in run.attributes.all
        },
        "attribute_basis_differs": run.attribute_basis_differs,
        "attempts": run.extraction.attempts,
        "prompt_version": run.extraction.prompt_version,
        "llm_calls": stats.llm_calls,
        "llm_retries": stats.llm_retries,
        "cache_hits": stats.cache_hits,
        "tokens_in": stats.input_tokens,
        "tokens_out": stats.output_tokens,
        "cost_usd": None if stats.estimated_cost is None else str(stats.estimated_cost),
    }


def summarise_stop(error: IngestionError, document_id: str, sha256: str) -> dict:
    """A run that stopped on a catalogued error, before or during the model call."""
    return {
        "outcome": "stopped",
        "document_id": document_id,
        "sha256_prefix": sha256[:12],
        "error_code": error.code.value,
        "detail": error.detail,  # setting names, bases found, counts: never document content
    }


def to_line(label: str, summary: dict) -> str:
    """One ASCII line, keys sorted, safe to paste."""

    def default(value):
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(type(value).__name__)

    return f"{label}: " + json.dumps(summary, sort_keys=True, ensure_ascii=True, default=default)
