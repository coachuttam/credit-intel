"""Marker files: a run that was accepted but did not finish is not lost without a word (PRD FR-016 criterion 10, OD-32 (b), E-RUN-INTERRUPTED; Phase 7 step 3).

When a run is accepted a small marker is written to ``<output_dir>/.pending/<run_id>.json``, **before** the ``202`` is sent, and it is removed when the run has
ended (its run folder, complete or a failure record, is on disk by then). If the service stops while the run is queued or running, the marker is still there at the
next start; ``recover_interrupted`` then writes a manifest-only failure record with ``E-RUN-INTERRUPTED``, so that ``GET /runs/{id}`` says "failed: interrupted"
and not ``404``. Runs are reported, not resumed: the uploaded copy is gone.

A marker holds only what a failure record needs: the run ID, the time of acceptance, the input's name and SHA-256, the options that appear in a manifest and the
model settings. It holds no document text and no profile content (only the profile's file name). The hidden folder name keeps it out of the list of runs.

What the record says about a run it never saw end: ``started_at`` is the time of acceptance; ``finished_at`` is the same time (the service did not record when it
stopped); ``failed_stage`` is the first stage after ``received`` (the stage the run had reached is not recorded). The code version and package versions are those of
the process that wrote the record, which may not be the one that stopped.
"""

import contextlib
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from credit_intel.config import LLMSettings, load_llm_settings
from credit_intel.export.manifest import code_version, package_versions, run_id as make_run_id
from credit_intel.export.run_export import export_failure
from credit_intel.export.writer import RUN_ID
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.models import StatementBasis
from credit_intel.states import RECEIVED, Recorder

logger = logging.getLogger("credit_intel.api")
PENDING = ".pending"
MARKER_VERSION = 1
INVALID_SUFFIX = ".invalid"
_FIELDS = ("marker_version", "run_id", "started", "input_file_name", "input_sha256", "requested_basis", "asserted_basis", "profile_file_name", "llm")


def pending_dir(output_dir: Path) -> Path:
    return output_dir / PENDING


def marker_path(output_dir: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("a marker is named for a run ID of the fixed form")
    return pending_dir(output_dir) / f"{run_id}.json"


def write_marker(output_dir: Path, *, run_id: str, started: datetime, input_file_name: str, input_sha256: str, requested_basis: StatementBasis,
                 asserted_basis: StatementBasis | None, profile_file_name: str | None, llm: LLMSettings) -> Path:  # fmt: skip
    """Write the marker atomically (a temporary file, then a rename) and make it durable. Raises ``OSError`` if it cannot: the run is then not accepted."""
    body = {
        "marker_version": MARKER_VERSION, "run_id": run_id, "started": started.astimezone(UTC).isoformat(), "input_file_name": input_file_name,
        "input_sha256": input_sha256, "requested_basis": requested_basis.value, "asserted_basis": asserted_basis.value if asserted_basis else None,
        "profile_file_name": profile_file_name, "llm": asdict(llm),
    }  # fmt: skip
    folder = pending_dir(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    final = marker_path(output_dir, run_id)
    temporary = folder / f".{run_id}.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(body, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, final)
    with contextlib.suppress(OSError):  # the marker is already in place; this only makes its name durable
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return final


def remove_marker(output_dir: Path, run_id: str) -> None:
    """Remove the marker of a run that has ended. A marker that is already gone is not an error; one that cannot be removed is logged and left for the next start."""
    try:
        marker_path(output_dir, run_id).unlink(missing_ok=True)
    except OSError:
        logger.warning("run=%s marker could not be removed", run_id)


def _read(path: Path) -> dict[str, Any] | None:
    """The marker, or ``None`` if it is not a marker of this version (anything else is not trusted)."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(body, dict) or set(body) != set(_FIELDS) or body["marker_version"] != MARKER_VERSION:
            return None
        if body["run_id"] != path.stem or not RUN_ID.fullmatch(body["run_id"]) or not re.fullmatch(r"[0-9a-f]{64}", body["input_sha256"]):
            return None
        if not isinstance(body["input_file_name"], str) or not isinstance(body["started"], str):
            return None
        StatementBasis(body["requested_basis"])
        if body["asserted_basis"] is not None:
            StatementBasis(body["asserted_basis"])
        started = datetime.fromisoformat(body["started"])
        if started.tzinfo is None or make_run_id(started.astimezone(UTC), body["input_sha256"]) != body["run_id"]:
            return None  # the run ID is a function of the time and the hash: a marker that disagrees with itself is not trusted
        body["llm_settings"] = LLMSettings(**body["llm"])
        body["started_at"] = started.astimezone(UTC)
        return body
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
        return None


def recover_interrupted(output_dir: Path, *, now: Callable[[], datetime] | None = None) -> list[str]:
    """Record every run that was accepted and did not end as ``E-RUN-INTERRUPTED``, and remove its marker. Returns the run IDs recorded.

    A marker whose run folder exists (the run ended and only the removal was missed) is just removed. A marker that is not valid is renamed ``<name>.invalid`` and
    logged, never trusted and never retried for ever. A record that cannot be written leaves its marker for the next start.
    """
    folder = pending_dir(output_dir)
    if not folder.is_dir():
        return []
    recorded: list[str] = []
    for path in sorted(folder.glob("*.json")):
        if path.is_symlink() or not RUN_ID.fullmatch(path.stem):
            continue
        marker = _read(path)
        if marker is None:
            logger.warning("run=%s marker is not valid; set aside", path.stem)
            with contextlib.suppress(OSError):
                path.rename(path.with_name(path.name + INVALID_SUFFIX))
            continue
        run_id = marker["run_id"]
        if (output_dir / run_id).exists() or (output_dir / run_id).is_symlink():
            remove_marker(output_dir, run_id)  # the run ended
            continue
        started = marker["started_at"]
        recorder = Recorder(lambda: started)
        recorder.enter(RECEIVED)
        recorder.fail(ErrorCode.RUN_INTERRUPTED.value)
        try:
            export_failure(output_dir, recorder, marker["llm_settings"], requested_basis=StatementBasis(marker["requested_basis"]), version=code_version(),
                           packages=package_versions(), input_file_name=marker["input_file_name"], input_sha256=marker["input_sha256"],
                           profile_file_name=marker["profile_file_name"],
                           asserted_basis=StatementBasis(marker["asserted_basis"]) if marker["asserted_basis"] else None)  # fmt: skip
        except (IngestionError, OSError):
            logger.warning("run=%s interrupted run could not be recorded; it will be tried at the next start", run_id)
            continue
        remove_marker(output_dir, run_id)
        recorded.append(run_id)
        logger.info("run=%s recorded as interrupted", run_id)
    return recorded
