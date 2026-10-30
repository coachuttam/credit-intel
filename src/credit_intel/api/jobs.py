"""Running accepted uploads (PRD FR-016 criteria 4 and 10, OD-19 (a), OD-20 (a), v0.4.59).

A bounded pool of worker threads in the server process runs ``service.execute_run``, one run per thread. ``api.max_concurrent_runs`` run at
once and at most ``api.max_queued_runs`` wait; beyond that ``submit`` raises ``QueueFull``. State is held in memory while a run is going and in
the run folder afterwards; a restart loses the runs in flight, and a run folder is only ever complete or absent.

**The whole-run deadline is cooperative (FR-016 criterion 10a).** It is checked when the run enters a state and before each model call; past it the
run ends with ``E-RUN-TIMEOUT``. A stage that is already running is not interrupted, so a run can end later than the limit, bounded by that stage's own
limits, and it keeps its pool slot until its thread returns; the status says the deadline has passed.
"""

import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from credit_intel.api.errors import INTERNAL, message_of
from credit_intel.config import ApiSettings, LLMSettings
from credit_intel.export.manifest import run_id as make_run_id
from credit_intel.ingestion.errors import MESSAGES, ErrorCode, IngestionError
from credit_intel.llm.provider import LLMProvider, LLMRequest, LLMResponse
from credit_intel.service import RunProgress, RunRequest, RunServices, execute_run, record_failure
from credit_intel.states import Clock, Recorder

logger = logging.getLogger("credit_intel.api")
RUN_ID = r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}"
FILES = ("memo.md", "results.json", "manifest.json", "report.pdf")
KEEP_FINISHED = 200  # finished runs kept in memory for their status; the run folder is the record


class QueueFull(Exception):
    """More runs are waiting than ``api.max_queued_runs`` allows."""


class Closing(Exception):
    """The service is shutting down."""


class DeadlineRecorder(Recorder):
    """A recorder whose first event carries the time the upload was complete (so the run ID is known at once) and that enforces the deadline."""

    def __init__(self, started: datetime, clock: Clock, check: Callable[[], None]) -> None:
        super().__init__(self._tick)
        self._started, self._real, self._check = started, clock, check

    def _tick(self) -> datetime:
        return self._started if not self.events else self._real()

    def enter(self, state, counts=None):  # type: ignore[no-untyped-def]
        self._check()
        return super().enter(state, counts)


class DeadlineProvider:
    """Checks the deadline before each model call."""

    def __init__(self, inner: LLMProvider, check: Callable[[], None]) -> None:
        self._inner, self._check = inner, check

    def complete(self, request: LLMRequest) -> LLMResponse:
        self._check()
        return self._inner.complete(request)


@dataclass
class Job:
    run_id: str
    request: RunRequest
    upload_dir: Path
    started: datetime
    state: str = "queued"  # queued, running, done
    progress: RunProgress | None = None
    folder: Path | None = None
    error: tuple[str | None, str] | None = None  # (code or None for an internal error, message)
    deadline: float | None = None
    limit: float = 0.0
    now: Callable[[], float] = time.monotonic
    lock: threading.Lock = field(default_factory=threading.Lock)

    def check_deadline(self) -> None:
        if self.deadline is not None and self.now() > self.deadline:
            raise IngestionError(ErrorCode.RUN_TIMEOUT)

    @property
    def deadline_passed(self) -> bool:
        return self.state == "running" and self.deadline is not None and self.now() > self.deadline


def run_id_for(started: datetime, sha256: str) -> str:
    return make_run_id(started, sha256)


class JobManager:
    def __init__(self, settings: ApiSettings, config: Path, services: RunServices, env: Mapping[str, str], clock: Clock,
                 monotonic: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self.settings, self.config, self.services, self.env, self.clock, self.monotonic = settings, config, services, env, clock, monotonic
        self._pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_runs, thread_name_prefix="run")
        self._lock = threading.Lock()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._queued = 0
        self._running = 0
        self._uploading = 0
        self._closing = False

    # -- counts
    @property
    def counts(self) -> dict[str, int]:
        with self._lock:
            return {"queued": self._queued, "running": self._running}

    @property
    def uploading(self) -> int:
        with self._lock:
            return self._uploading

    # -- reserving a place before the upload is read (PRD OD-37, Phase 7 step 1)
    def reserve(self) -> None:
        """Hold a place for an upload that is about to be read: runs going, runs waiting and uploads arriving together stay within the two limits.

        Raises ``QueueFull`` or ``Closing`` **before a byte of the body is read**. The place is given up by ``release`` or turned into a queued run by ``submit(reserved=True)``.
        """
        with self._lock:
            if self._closing:
                raise Closing
            if self._queued + self._running + self._uploading >= self.settings.max_concurrent_runs + self.settings.max_queued_runs:
                raise QueueFull
            self._uploading += 1

    def release(self) -> None:
        with self._lock:
            self._uploading = max(0, self._uploading - 1)

    # -- submitting
    def submit(self, job: Job, *, reserved: bool = False) -> None:
        """Queue a run. With ``reserved`` the caller holds a place from ``reserve``; it is used up by this call, whether it queues the run or refuses it."""
        job.limit = float(self.settings.run_timeout_seconds)
        job.now = self.monotonic
        with self._lock:
            if reserved:
                self._uploading = max(0, self._uploading - 1)
            if self._closing:
                raise Closing
            if self._queued + self._running + self._uploading >= self.settings.max_concurrent_runs + self.settings.max_queued_runs:
                raise QueueFull  # the runs going, waiting and arriving are at the limits together (a reserved place was given up above, so it cannot trip this)
            if job.run_id in self._jobs:
                raise IngestionError(ErrorCode.API_REQUEST)  # the same document in the same microsecond: not a run to accept twice
            self._jobs[job.run_id] = job
            self._queued += 1
            self._trim()
        self._pool.submit(self._run, job)

    def _trim(self) -> None:
        finished = [key for key, job in self._jobs.items() if job.state == "done"]
        for key in finished[: max(0, len(finished) - KEEP_FINISHED)]:
            del self._jobs[key]

    def get(self, run_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(run_id)

    def jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    # -- running
    def _run(self, job: Job) -> None:
        with self._lock:
            self._queued -= 1
            self._running += 1
            job.state = "running"
        job.deadline = self.monotonic() + job.limit
        recorder = DeadlineRecorder(job.started, self.clock, job.check_deadline)
        job.progress = RunProgress(recorder)
        inner = self.services.provider_factory
        services = replace(self.services, provider_factory=lambda llm, env: DeadlineProvider(inner(llm, env), job.check_deadline))
        try:
            job.folder = execute_run(job.request, job.progress, services, self.env, lambda line: None)
        except IngestionError as error:
            job.error = (error.code.value, message_of(error))
            job.folder = record_failure(job.request, job.progress, error)
        except Exception as error:
            logger.debug("internal error", exc_info=True)  # the trace is for DEBUG only (FR-011.4)
            job.error = (None, INTERNAL)
            job.folder = record_failure(job.request, job.progress, error)
        finally:
            _remove(job.upload_dir)
            with self._lock:
                self._running -= 1
                job.state = "done"
            logger.info("run=%s state=%s", job.run_id, "failed" if job.error else "exported")

    def close(self) -> None:
        with self._lock:
            self._closing = True
        self._pool.shutdown(wait=False, cancel_futures=True)
        for job in self.jobs():
            if job.state == "queued":
                _remove(job.upload_dir)  # a queued run that will never start leaves nothing behind


def _remove(directory: Path) -> None:
    import shutil

    shutil.rmtree(directory, ignore_errors=True)


# --- status ----------------------------------------------------------------------------------------------------------------------------------


def files_of(folder: Path | None) -> list[str]:
    if folder is None or not folder.is_dir():
        return []
    return [name for name in FILES if (folder / name).is_file()]


def stages_of(job: Job) -> list[dict[str, object]]:
    if job.progress is None:
        return []
    return [{"state": event.state, "counts": dict(event.counts)} for event in job.progress.recorder.events]


def job_status(job: Job) -> dict[str, object]:
    body: dict[str, object] = {"run_id": job.run_id}
    if job.state == "queued":
        return {**body, "state": "queued"}
    recorder = job.progress.recorder if job.progress else None
    if job.state == "running":
        state = recorder.state if recorder and recorder.state else "received"
        if state == "exported":
            state = "memo_generated"  # `exported` is said only once the files are written and the run has returned
        return {**body, "state": state, "stages": stages_of(job), "deadline_passed": job.deadline_passed}
    if job.error is None:
        return {**body, "state": "exported", "stages": stages_of(job), "files": files_of(job.folder)}
    code, message = job.error
    return {**body, "state": "failed", "stage": recorder.failed_stage if recorder else None, "stages": stages_of(job),
            "error": {"code": code, "message": message}, "files": files_of(job.folder)}  # fmt: skip


def folder_status(run_id: str, folder: Path) -> dict[str, object] | None:
    """The status of a run that is no longer in memory, from its manifest. ``None`` if the folder holds no readable manifest."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        state = manifest["final_state"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    body: dict[str, object] = {"run_id": run_id, "state": state, "files": files_of(folder)}
    if state == "failed":
        code = manifest.get("error_code")
        try:
            message = MESSAGES[ErrorCode(code)] if code else INTERNAL
        except ValueError:
            code, message = None, INTERNAL
        body["stage"] = manifest.get("failed_stage")
        body["error"] = {"code": code, "message": message}
    return body
