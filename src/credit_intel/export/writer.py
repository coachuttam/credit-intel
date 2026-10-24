"""Writing a run's files so that a failed run never leaves anything that looks complete (PRD FR-010.1, FR-010.3, FR-010.4; step 5j).

``write_run`` puts the files of one run into ``<output_dir>/<run_id>/``:

* If that folder already exists, nothing is written and nothing is touched (FR-010.4).
* The files are first written into a hidden staging folder in the same directory, each through a temporary
  name and a rename, and flushed to disk. The staging folder has a name that is not a run ID (it starts with a
  dot and ends in ``.partial``), so a reader looking for runs never takes it for one.
* Only when every file is written is the staging folder renamed to the run folder, in one step. A crash, a full
  disk or a permission error before that step leaves no run folder (the flush of the parent directory after it is best effort); the staging folder is removed if the process
  survives to do so, and is recognisable and harmless if it does not.
* Every operating-system failure becomes ``E-EXPORT-FAILED``, with the original error as ``__cause__`` and no
  path or text in the message.
"""

import contextlib
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from credit_intel.ingestion.errors import ErrorCode, IngestionError

RUN_ID = re.compile(r"\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}")
FILE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
STAGING_SUFFIX = ".partial"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_file(directory: Path, name: str, text: str) -> None:
    """Write ``text`` as UTF-8 bytes (no byte-order mark, newlines as given) through a temporary name, then rename."""
    temporary = directory / f"{name}.tmp"
    with open(temporary, "xb") as handle:
        handle.write(text.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, directory / name)


def write_run(output_dir: Path, run_id: str, files: Mapping[str, str]) -> Path:
    """Write ``files`` (name to text) as the run folder ``<output_dir>/<run_id>``, or raise ``E-EXPORT-FAILED``."""
    if not RUN_ID.fullmatch(run_id) or not files or not all(FILE_NAME.fullmatch(name) for name in files):
        raise ValueError("a run needs a run ID of the FR-010.1 form and plain file names")
    final = output_dir / run_id
    staging: Path | None = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if final.exists() or final.is_symlink():
            raise FileExistsError("the run directory already exists")
        staging = Path(tempfile.mkdtemp(prefix=f".{run_id}.", suffix=STAGING_SUFFIX, dir=output_dir))
        for name, text in files.items():
            _write_file(staging, name, text)
        _fsync_directory(staging)
        os.rename(staging, final)
        staging = None
        with contextlib.suppress(OSError):  # the run is already complete and visible; this only makes the name durable
            _fsync_directory(output_dir)
    except BaseException as error:
        if staging is not None:
            with contextlib.suppress(OSError):
                shutil.rmtree(staging)
        if isinstance(error, OSError):
            raise IngestionError(ErrorCode.EXPORT_FAILED) from error
        raise
    return final
