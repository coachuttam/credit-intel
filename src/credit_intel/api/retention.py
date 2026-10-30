"""Clearing out what a run leaves behind: the start-up sweep of orphaned uploads and ``prune`` (PRD SEC-14, SEC-18, OD-40; Phase 7 step 3).

* **The sweep** runs once when the service starts. An upload directory is named for the process that made it
  (``credit-intel-upload-<pid>-<random>``). One that belongs to a process that is no longer running, or to this process's own number (nothing of this process exists
  yet, so it is left by an earlier life that had the same number), is a crash's leftover and is removed. One that belongs to another process that is still running is
  left alone. A directory from before the name carried a number is removed once it is a day old. Only directories this user owns, never a link, are touched.
* **``prune --older-than DAYS``** removes, and only when asked, **whole** run folders, the hidden staging folders that a crash during the writing of a run folder leaves
  (``.<run_id>.<random>.partial``), response-cache entries and upload directories older than DAYS, and nothing else.
  DAYS is required and has no default. ``--dry-run`` lists and removes nothing. The service never calls it: the operator or a scheduler does.
  A run folder's and a staging folder's age is the time in the run ID in its name (when the run was accepted); a cache entry's or upload directory's age is its modification time.
  Removing a run folder ends the traceability of that run to its stored files; removing cache entries means an old run cannot be reproduced without a model call.
"""

import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from credit_intel.config import ApiSettings
from credit_intel.export.writer import RUN_ID

logger = logging.getLogger("credit_intel.api")
UPLOAD_PREFIX = "credit-intel-upload-"
_UPLOAD = re.compile(rf"{re.escape(UPLOAD_PREFIX)}(?:(\d+)-)?[^/]+")
_CACHE_ENTRY = re.compile(r"[0-9a-f]{64}\.json")
_STAGING = re.compile(r"\.(\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8})\.[A-Za-z0-9_]+\.partial")  # the name `export.writer.write_run` gives its staging folder
LEGACY_UPLOAD_AGE = timedelta(days=1)


def upload_prefix(pid: int | None = None) -> str:
    return f"{UPLOAD_PREFIX}{os.getpid() if pid is None else pid}-"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists and is another user's
    except OSError:
        return False
    return True


def _ours(path: Path) -> bool:
    """A real directory (not a link) owned by the user running this process."""
    try:
        status = path.lstat()
    except OSError:
        return False
    return path.is_dir() and not path.is_symlink() and (not hasattr(os, "getuid") or status.st_uid == os.getuid())


def sweep_stale_uploads(temp_root: Path | None = None, *, pid: int | None = None, alive: Callable[[int], bool] = _alive,
                        now: Callable[[], datetime] | None = None) -> list[str]:  # fmt: skip
    """Remove the upload directories that a crash left behind. Returns the names removed (no document text in them)."""
    root = temp_root if temp_root is not None else Path(tempfile.gettempdir())
    own = os.getpid() if pid is None else pid
    moment = (now or (lambda: datetime.now(UTC)))()
    removed: list[str] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return removed
    for path in entries:
        match = _UPLOAD.fullmatch(path.name)
        if match is None or not _ours(path):
            continue
        owner = match.group(1)
        if owner is None:
            try:
                old = moment - datetime.fromtimestamp(path.stat().st_mtime, UTC) >= LEGACY_UPLOAD_AGE
            except OSError:
                continue
            stale = old
        else:
            stale = int(owner) == own or not alive(int(owner))
        if stale:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    if removed:
        logger.info("swept %d orphaned upload directories", len(removed))
    return removed


# --- prune ---------------------------------------------------------------------------------------------------------------------------------------


@dataclass
class PruneReport:
    days: int
    dry_run: bool
    runs: list[str] = field(default_factory=list)
    staging: list[str] = field(default_factory=list)
    cache_entries: int = 0
    uploads: int = 0


def _run_started(name: str) -> datetime | None:
    try:
        return datetime.strptime(name.split("-")[0], "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def prune(settings: ApiSettings, days: int, *, dry_run: bool, now: Callable[[], datetime] | None = None, temp_root: Path | None = None) -> PruneReport:
    """Remove (or, with ``dry_run``, list) whole run folders, cache entries and upload directories at least ``days`` days old. Nothing else is touched."""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be a whole number of at least 1")
    moment = (now or (lambda: datetime.now(UTC)))()
    cutoff = moment - timedelta(days=days)
    report = PruneReport(days, dry_run)

    output = settings.output_dir
    if output.is_dir():
        for folder in sorted(output.iterdir()):
            if folder.is_symlink() or not folder.is_dir():
                continue
            staging = _STAGING.fullmatch(folder.name)
            if not RUN_ID.fullmatch(folder.name) and staging is None:
                continue
            started = _run_started(staging.group(1) if staging else folder.name)
            if started is None or started > cutoff:
                continue
            (report.staging if staging else report.runs).append(folder.name)
            if not dry_run:
                shutil.rmtree(folder)

    cache = settings.cache_dir
    if cache.is_dir():
        for entry in sorted(cache.iterdir()):
            if not _CACHE_ENTRY.fullmatch(entry.name) or entry.is_symlink() or not entry.is_file():
                continue
            if datetime.fromtimestamp(entry.stat().st_mtime, UTC) > cutoff:
                continue
            report.cache_entries += 1
            if not dry_run:
                entry.unlink()

    root = temp_root if temp_root is not None else Path(tempfile.gettempdir())
    try:
        candidates = sorted(root.iterdir())
    except OSError:
        candidates = []
    for path in candidates:
        if _UPLOAD.fullmatch(path.name) is None or not _ours(path):
            continue
        if datetime.fromtimestamp(path.stat().st_mtime, UTC) > cutoff:
            continue
        report.uploads += 1
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
    return report


def render(report: PruneReport) -> list[str]:
    """The lines ``prune`` prints: run IDs (identifiers, not document text), and counts."""
    verb = "would remove" if report.dry_run else "removed"
    lines = [f"{verb} run {run_id}" for run_id in report.runs]
    lines += [f"{verb} staging folder {name}" for name in report.staging]
    lines.append(f"{verb} {len(report.runs)} run folders, {len(report.staging)} staging folders, {report.cache_entries} cache entries and {report.uploads} upload directories "
                 f"older than {report.days} days")
    if report.cache_entries:
        lines.append("note: without its cache entries a run cannot be reproduced without calling the model again")
    if report.runs:
        lines.append("note: a removed run folder can no longer be checked against its stored files; the SHA-256 in a kept manifest still names the input")
    if report.dry_run:
        lines.append("dry run: nothing was removed")
    return lines
