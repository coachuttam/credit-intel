"""The memory a container needs, and a refusal to start in one that is too small (PRD FR-018 criterion 7, SEC-12; Phase 7 step 2).

One run can hold up to ``ingestion.parse_memory_mb`` in its worker, so the pool can hold ``api.max_concurrent_runs`` times that. Beside it come what the server
itself uses (about 1.5 GB with one run, ``docs/OD-25_run_timing_2026-10-30.md``) and **the uploads**: they sit in a ``tmpfs``, which is memory, and the service can hold
at most ``api.max_concurrent_runs + api.max_queued_runs`` of them at once, each up to the file-size limit. The uploads are counted by what the service can hold, not by
the size the operator gave the ``tmpfs`` (that size is only a cap). If the container's own limit is lower than the sum, the kernel ends the **whole container** (every
run, the queue and the server) before the parse limit can end one run cleanly. So the service reads the container's limit when it starts and refuses to start under
the sum: the limit that is checked is the one that will be enforced.

A host with no container limit (or none that can be read) is not refused: there is nothing to compare with.
"""

from pathlib import Path

from credit_intel.config import MEGABYTE as BYTES_PER_MB
from credit_intel.config import ApiSettings, IngestionSettings, ParseLimits
from credit_intel.ingestion.errors import ErrorCode, IngestionError

SERVER_ALLOWANCE_MB = 1536  # what the server process itself uses with one run (OD-25: about 1,458 MB for a 159-page run)
MEGABYTE = 1024 * 1024
UNLIMITED = 2**62  # cgroup v1 reports an unlimited memory as a number close to 2**63


def uploads_mb(api: ApiSettings, max_file_bytes: int) -> int:
    """The most the uploads can occupy at once: one place per running, waiting or arriving run (SEC-14), each up to the file-size limit."""
    return (api.max_concurrent_runs + api.max_queued_runs) * -(-max_file_bytes // BYTES_PER_MB)


def minimum_container_mb(api: ApiSettings, parse: ParseLimits, max_file_bytes: int | None = None) -> int:
    """The pool's workers, the uploads in the ``tmpfs`` and the server's own use."""
    limit = IngestionSettings().max_file_bytes if max_file_bytes is None else max_file_bytes
    return api.max_concurrent_runs * parse.memory_mb + uploads_mb(api, limit) + SERVER_ALLOWANCE_MB


def _bytes(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdigit() else None


def container_memory_limit_mb(root: Path = Path("/sys/fs/cgroup")) -> int | None:
    """The memory limit of the container in MB from the cgroup file system (version 2, then version 1), or ``None`` if there is none or it cannot be read."""
    for relative in ("memory.max", "memory/memory.limit_in_bytes"):
        try:
            value = _bytes((root / relative).read_text(encoding="ascii"))
        except (OSError, UnicodeDecodeError):
            continue
        if value is not None and value < UNLIMITED:
            return value // MEGABYTE
        return None  # "max" (version 2) or a number meaning no limit
    return None


def check_container_memory(api: ApiSettings, parse: ParseLimits, limit_mb: int | None, max_file_bytes: int | None = None) -> None:
    """Raise ``E-CONFIG-INVALID`` if the container's limit is below the sum above. The message carries the two numbers and nothing else."""
    needed = minimum_container_mb(api, parse, max_file_bytes)
    if limit_mb is not None and limit_mb < needed:
        raise IngestionError(
            ErrorCode.CONFIG_INVALID,
            detail=f"container memory {limit_mb} MB is below the {needed} MB that api.max_concurrent_runs times ingestion.parse_memory_mb, plus the uploads and the server's use, needs",
        )
