"""Finishing a run: the memo, the three files and the last two states (PRD FR-009, FR-010, FR-011, FR-012; step 5j).

``export_run`` takes the result of ``run_pipeline`` and its recorder. It builds ``results.json`` once, makes the
memo from that same data, enters ``memo_generated``, enters ``exported``, builds the manifest (which therefore
records ``exported`` as its final state) and writes all three files with ``write_run``. If the writing fails,
the run is recorded as failed in ``exported`` with ``E-EXPORT-FAILED`` and the error is re-raised; nothing is left
behind that looks complete.

``export_failure`` writes a run folder with only ``manifest.json`` for a run that failed after its input was read,
so the final state and error code of a failed run are on record (FR-012.1). It has no memo and no results, so it
does not look like a finished run.
"""

import logging
from pathlib import Path

from credit_intel.config import LLMSettings
from credit_intel.export.manifest import CodeVersion, build_manifest, render_manifest, run_id, timestamp
from credit_intel.export.results import build_results, render_data
from credit_intel.export.writer import write_run
from credit_intel.memo.render import render_memo
from credit_intel.memo.trace import MemoCheckFailed, problems
from credit_intel.models import StatementBasis
from credit_intel.run import RunResult
from credit_intel.states import EXPORTED, MEMO_GENERATED, Recorder

logger = logging.getLogger("credit_intel.export")


def export_run(
    output_dir: Path,
    result: RunResult,
    recorder: Recorder,
    llm: LLMSettings,
    *,
    requested_basis: StatementBasis,
    version: CodeVersion,
    packages: dict[str, str | None],
    profile_file_name: str | None = None,
) -> Path:
    """Write ``memo.md``, ``results.json`` and ``manifest.json`` to ``<output_dir>/<run_id>/`` and return that path."""
    sha = result.extraction.source_document.sha256
    identifier = run_id(recorder.events[0].at, sha)
    try:
        data = build_results(result.extraction, result.metrics, result.rules, result.profile)
        memo = render_memo(data, identifier, timestamp(recorder.now()))
        found = problems(memo, data)  # FR-010 criterion 5: the K.10 rules, on every memo, before anything is written
        logger.info("stage=memo_checked run=%s problems=%d", identifier, len(found))  # a count, never the text
        if found:
            raise MemoCheckFailed(len(found))  # an internal error: a defect in the template or the data, recorded as failed in memo_generated
        recorder.enter(MEMO_GENERATED, {"memo_lines": memo.count("\n")})
        recorder.enter(EXPORTED, {"files": 3})
        manifest = build_manifest(recorder=recorder, llm=llm, requested_basis=requested_basis, version=version, packages=packages,
                                  result=result, profile_file_name=profile_file_name)  # fmt: skip
        path = write_run(output_dir, identifier, {"memo.md": memo, "results.json": render_data(data), "manifest.json": render_manifest(manifest)})
    except Exception as error:
        recorder.fail(getattr(getattr(error, "code", None), "value", None))
        raise
    logger.info("stage=%s run=%s files=3", EXPORTED, identifier)
    return path


def export_failure(
    output_dir: Path,
    recorder: Recorder,
    llm: LLMSettings,
    *,
    requested_basis: StatementBasis,
    version: CodeVersion,
    packages: dict[str, str | None],
    input_file_name: str,
    input_sha256: str,
    profile_file_name: str | None = None,
    asserted_basis: StatementBasis | None = None,
) -> Path:
    """Write a run folder holding only the manifest of a run that failed (its ``final_state`` is ``failed``)."""
    if not recorder.failed:
        raise ValueError("export_failure is for a run that failed")
    manifest = build_manifest(recorder=recorder, llm=llm, requested_basis=requested_basis, version=version, packages=packages,
                              input_file_name=input_file_name, input_sha256=input_sha256, profile_file_name=profile_file_name,
                              asserted_basis=asserted_basis)  # fmt: skip
    return write_run(output_dir, run_id(recorder.events[0].at, input_sha256), {"manifest.json": render_manifest(manifest)})
