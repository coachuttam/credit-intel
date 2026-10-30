"""``manifest.json``: what a run was and how it went (PRD FR-012.1; step 5e).

Unlike ``results.json`` this file holds what changes between runs: the run ID, the timestamps, the code
version and the cost. It is built from explicit values, so a test passes a fixed clock, a fixed code version
and fixed package versions; ``code_version`` and ``package_versions`` read the real ones. A failed run has a
manifest too: what was not reached (page count, candidate pages, tokens before the failure) is ``null``, never
a guess, and the final state is ``failed`` with the stage it failed in and its error code. Only counts,
identifiers and configuration are written: no document text, quote or financial value (FR-012.3). The
analyst profile's values are not written, only the file name.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from credit_intel.config import LLMSettings
from credit_intel.export.results import SCHEMA_VERSION as RESULTS_SCHEMA_VERSION, to_jsonable
from credit_intel.models import StatementBasis
from credit_intel.run import RunResult
from credit_intel.states import Recorder

MANIFEST_SCHEMA_VERSION = "1"
PACKAGES = ("openai", "pdfplumber", "pydantic")  # the runtime dependencies (pyproject.toml)
REPOSITORY = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class CodeVersion:
    git_commit: str | None  # None when the code is not a git checkout or git is unavailable
    dirty: bool | None


def code_version(repository: Path = REPOSITORY, env: Mapping[str, str] | None = None) -> CodeVersion:
    """The commit the code was run from and whether the working tree differs from it (FR-012.1)."""

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(["git", *args], cwd=repository, capture_output=True, text=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    if commit is None or status is None:
        return CodeVersion(_built_commit(os.environ if env is None else env), None)  # not a checkout: an image, which is told its commit when it is built
    return CodeVersion(commit.strip(), bool(status.strip()))


ENV_BUILD_COMMIT = "CREDIT_INTEL_BUILD_COMMIT"


def _built_commit(env: Mapping[str, str]) -> str | None:
    """The commit an image was built from (a build argument set as this variable), or ``None`` if it is absent or not a full lower-case SHA-1."""
    value = env.get(ENV_BUILD_COMMIT, "")
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def package_versions(names: tuple[str, ...] = PACKAGES) -> dict[str, str | None]:
    """Installed versions of the runtime dependencies, and of Python itself."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    versions["python"] = ".".join(str(part) for part in sys.version_info[:3])
    return versions


def timestamp(moment: datetime) -> str:
    """UTC to the microsecond, as in the run ID: ``20261013T101530.123456Z``."""
    if moment.tzinfo is None or moment.utcoffset() != UTC.utcoffset(None):
        raise ValueError("a run timestamp must be in UTC")
    return moment.strftime("%Y%m%dT%H%M%S.%fZ")


def run_id(started: datetime, input_sha256: str) -> str:
    """``<UTC timestamp to the microsecond>-<first 8 hex of the input SHA-256>`` (FR-010.1)."""
    return f"{timestamp(started)}-{input_sha256[:8]}"


def build_manifest(
    *,
    recorder: Recorder,
    llm: LLMSettings,
    requested_basis: StatementBasis,
    version: CodeVersion,
    packages: dict[str, str | None],
    input_file_name: str | None = None,
    input_sha256: str | None = None,
    result: RunResult | None = None,
    profile_file_name: str | None = None,
    rules_sha256: str | None = None,
    asserted_basis: StatementBasis | None = None,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The contents of ``manifest.json``. ``result`` is ``None`` for a run that failed before it finished.

    ``asserted_basis`` is the basis the analyst asked to assert (H.4.6, v0.4.24). A finished run records the assertion
    itself (basis, pages, applied pages); a run that failed before the pages were known records the basis only.
    """
    events = recorder.events
    if not events:
        raise ValueError("a manifest needs at least one recorded state")
    extraction = result.extraction if result is not None else None
    stats = extraction.stats if extraction is not None else None
    located = extraction.located if extraction is not None else None
    assertion = extraction.basis_assertion if extraction is not None else None
    if assertion is not None:
        recorded_assertion: dict[str, Any] | None = to_jsonable(assertion)
    elif asserted_basis is not None:
        recorded_assertion = {"basis": asserted_basis.value, "pages": None, "applied_pages": None}
    else:
        recorded_assertion = None
    sha = input_sha256 if input_sha256 is not None else (extraction.source_document.sha256 if extraction else None)
    name = input_file_name if input_file_name is not None else (extraction.source_document.file_name if extraction else None)
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "results_schema_version": RESULTS_SCHEMA_VERSION,
        "run_id": run_id(events[0].at, sha) if sha is not None else None,
        "started_at": timestamp(events[0].at),
        "finished_at": timestamp(events[-1].at),
        "stage_events": [{"state": e.state, "at": timestamp(e.at), "counts": to_jsonable(dict(e.counts))} for e in events],
        "final_state": recorder.final_state,
        "failed_stage": recorder.failed_stage,
        "error_code": recorder.error_code,
        "input": {"file_name": name, "sha256": sha, "page_count": extraction.page_count if extraction else None},
        "profile_file_name": profile_file_name,
        "locator_method": located.method if located else None,
        "candidate_pages": sorted(c.page_number for c in located.candidates) if located else None,
        "range_pages_without_text": list(located.range_pages_without_text) if located else None,
        "excluded_candidate_count": len(located.excluded_candidates) if located else None,
        "requested_basis": requested_basis.value,
        "basis_assertion": recorded_assertion,
        "bases_found": list(extraction.field_set.bases_present) if extraction else None,
        "code_version": {"git_commit": version.git_commit, "dirty": version.dirty},
        "package_versions": dict(sorted(packages.items())),
        "llm": {"provider": llm.provider, "model_id": llm.model_id, "token_ceiling": llm.token_ceiling,
                "max_output_tokens": llm.max_output_tokens},  # fmt: skip
        "prompt_version": extraction.extraction.prompt_version if extraction else None,
        "extraction_schema_version": extraction.extraction.schema_version if extraction else None,
        "rules_config_sha256": rules_sha256 if rules_sha256 is not None else (result.rules_sha256 if result else None),
        "cache": {"hits": stats.cache_hits, "misses": stats.cache_misses} if stats else None,
        "tokens": {"input": stats.input_tokens, "output": stats.output_tokens, "counted": stats.tokens_used,
                   "llm_calls": stats.llm_calls, "retries": stats.llm_retries} if stats else None,  # fmt: skip
        "estimated_cost_usd": to_jsonable(stats.estimated_cost) if stats else None,
    }
    if report is not None:  # PRD v0.4.56 (FR-015 criterion 8): what became of the PDF report; a failure record has none, no report was tried
        manifest["report"] = report
    derivations = extraction.attributes.derivations if extraction is not None else ()
    if derivations:  # PRD v0.4.37: a currency or scale the code read from the pages because the model gave none that was usable
        manifest["attribute_derivations"] = [{"attribute": d.attribute, "page": d.page, "why": d.why} for d in derivations]
    refilings = getattr(extraction, "field_refilings", ())
    if refilings:  # PRD v0.4.38: a total_borrowings proposal that was verified as a borrowings component
        manifest["field_refilings"] = [{"proposed": r.proposed, "used": r.used, "page": r.page, "period": r.period} for r in refilings]
    scans = getattr(extraction, "field_scans", ())
    if scans:  # PRD v0.4.39: a borrowings component row the code read from the page because the model proposed none
        manifest["field_scans"] = [{"field": s.field, "page": s.page, "period": s.period, "label": s.label} for s in scans]
    ocr = getattr(extraction, "ocr", None)
    if ocr is not None:  # PRD v0.4.44: only when OCR was used (engine, DPI, language, and per page the source of its text)
        manifest["ocr"] = ocr.to_manifest()
    repairs = extraction.attributes.page_repairs if extraction is not None else ()
    if repairs:  # PRD v0.4.36: each currency or scale declaration verified on another page than the one the model cited
        manifest["attribute_page_repairs"] = [{"attribute": r.attribute, "cited_page": r.cited_page, "page_used": r.page_used} for r in repairs]
    page_filter = getattr(extraction, "page_filter", None)
    if page_filter is not None:  # only when the optional page classifier was switched on (PRD v0.4.31): per-page labels, latency, cost
        manifest["page_filter"] = page_filter.to_manifest()
    return manifest


def render_manifest(manifest: dict[str, Any]) -> str:
    """Sorted keys, two-space indent, one final newline, like ``results.json``."""
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
