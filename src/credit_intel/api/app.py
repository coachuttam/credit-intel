"""The HTTP API (PRD FR-016, v0.4.59): five endpoints over ``credit_intel.service`` and nothing else.

``POST /runs`` receives one upload and, **in the request**, does the checks that need no parsing (size while streaming, the ``%PDF-`` signature, the
option values, the profile, the page-range syntax, the OCR engine when OCR is asked for, the send rule and the confirmation), with the functions the
command line uses; a failure there is a catalogued 4xx/5xx and creates no run. A run that passes is queued and answers ``202`` with its run ID; every
later failure is reported in the run's status. The files of a run folder are served byte for byte.
"""

import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from collections.abc import Mapping
from datetime import UTC
from pathlib import Path

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from credit_intel.api.errors import BUSY, CLOSING, METHOD, NOT_FOUND, REFUSED, error_body, status_of, transport_body
from credit_intel.api.jobs import RUN_ID, Closing, Job, JobManager, QueueFull, folder_status, job_status, run_id_for
from credit_intel.api.pages import add_pages
from credit_intel.api.security import Security, check_exposure
from credit_intel.api.uploads import Upload, receive_upload
from credit_intel.config import DEFAULT_SETTINGS_PATH, ApiSettings, IngestionSettings, LocatorSettings, load_api_token, load_llm_settings
from credit_intel.evaluation.guard import ENV_PRIVATE_APPROVED
from credit_intel.ingestion.errors import ErrorCode, IngestionError
from credit_intel.ingestion.locator import parse_page_range
from credit_intel.models import StatementBasis
from credit_intel.profile import load_profile
from credit_intel.service import RunRequest, RunServices, check_send_rule, page_filter
from credit_intel.states import Clock, utc_now

logger = logging.getLogger("credit_intel.api")
BASES = (StatementBasis.CONSOLIDATED.value, StatementBasis.STANDALONE.value)
FIELDS = ("basis", "pages", "assert_basis", "profile", "ocr", "no_report", "confirm_public_document")
MEDIA = {"memo": ("memo.md", "text/markdown; charset=utf-8"), "results": ("results.json", "application/json"),
         "manifest": ("manifest.json", "application/json"), "report": ("report.pdf", "application/pdf")}  # fmt: skip
MAX_LISTED = 100
_RUN_ID = re.compile(RUN_ID)


def _flag(fields: Mapping[str, str], name: str) -> bool:
    value = fields.get(name, "false")
    if value not in ("true", "false"):
        raise IngestionError(ErrorCode.API_REQUEST)
    return value == "true"


def _choice(fields: Mapping[str, str], name: str) -> StatementBasis | None:
    value = fields.get(name, "")
    if value == "":
        return None
    if value not in BASES:
        raise IngestionError(ErrorCode.API_REQUEST)
    return StatementBasis(value)


def _check_request(upload: Upload, config: Path, services: RunServices, env: Mapping[str, str], settings: ApiSettings) -> RunRequest:
    """Every check of the request that needs no parsing of the document. Raises ``IngestionError``."""
    fields = upload.fields
    if not set(fields) <= set(FIELDS):
        raise IngestionError(ErrorCode.API_REQUEST)
    basis = _choice(fields, "basis") or StatementBasis.CONSOLIDATED
    asserted = _choice(fields, "assert_basis")
    ocr, no_report, confirmed = _flag(fields, "ocr"), _flag(fields, "no_report"), _flag(fields, "confirm_public_document")
    pages = fields.get("pages", "") or None
    if asserted is not None and pages is None:
        raise IngestionError(ErrorCode.API_REQUEST)  # `--assert-basis` requires `--pages` (FR-014.4)
    if pages is not None:
        if len(pages) > 200:
            raise IngestionError(ErrorCode.API_REQUEST)
        parse_page_range(pages, IngestionSettings().max_pages, LocatorSettings().max_candidates)  # E-INPUT-PAGE-RANGE
    profile: Path | None = None
    if fields.get("profile", ""):
        profile = upload.directory / "profile.json"
        profile.write_text(fields["profile"], encoding="utf-8")
        load_profile(profile)  # E-INPUT-PROFILE-INVALID, with the rules of FR-014.7
    request = RunRequest(upload.file, basis=basis, pages=pages, assert_basis=asserted, profile=profile, output_dir=settings.output_dir,
                         cache_dir=settings.cache_dir, config=config, ocr=ocr, confirm_public_document=confirmed, no_report=no_report)  # fmt: skip
    if ocr:
        probe = getattr(services.ocr_factory(), "check_available", None)
        if probe is not None:
            probe()  # E-INPUT-OCR-UNAVAILABLE
    llm = load_llm_settings(config, env)  # E-CONFIG-INVALID
    setup = page_filter(request, llm, env, services.classifier_factory)
    check_send_rule(request, upload.sha256, llm, setup, services.assignments, env, lambda line: None)  # E-INPUT-SEND-REFUSED
    return request


def create_app(settings: ApiSettings, *, config: Path = DEFAULT_SETTINGS_PATH, services: RunServices | None = None,
               env: Mapping[str, str] | None = None, clock: Clock = utc_now, manager: JobManager | None = None,
               max_file_bytes: int | None = None) -> FastAPI:  # fmt: skip
    """The application. ``env`` is the process environment without the owner's ``private/`` approval, which the API never honours (FR-016 criterion 8)."""
    base = dict(os.environ if env is None else env)
    base.pop(ENV_PRIVATE_APPROVED, None)
    token = load_api_token(base)  # E-CONFIG-INVALID for a short or odd token
    check_exposure(settings.host, token)  # and for a host that is not a loopback address with no token (SEC-15)
    if Path(tempfile.gettempdir()).resolve().is_relative_to(settings.output_dir.resolve()):
        raise IngestionError(ErrorCode.CONFIG_INVALID, "api.output_dir")  # uploads are kept outside the output folder (SEC-14)
    services = services or RunServices()
    jobs = manager or JobManager(settings, config, services, base, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        yield
        jobs.close()

    app = FastAPI(title="AI Credit Intelligence", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)  # nothing is served beside the endpoints
    app.state.jobs, app.state.settings = jobs, settings
    app.add_middleware(Security, token=token)
    max_bytes = max_file_bytes if max_file_bytes is not None else IngestionSettings().max_file_bytes  # FR-001.2; a parameter so a test can use a small one

    @app.exception_handler(StarletteHTTPException)
    async def transport_error(_: Request, error: StarletteHTTPException) -> JSONResponse:  # a path with no route, a method not allowed: the same fixed shape
        message = NOT_FOUND if error.status_code == 404 else METHOD if error.status_code == 405 else REFUSED
        return JSONResponse(transport_body(message), status_code=error.status_code)

    def refuse(error: IngestionError) -> JSONResponse:
        return JSONResponse(error_body(error), status_code=status_of(error))

    async def accept(request: Request) -> JSONResponse:
        """Receive an upload, make the checks of the request and queue the run: the one path for `POST /runs` and the page's form."""
        try:
            upload = await receive_upload(request, max_bytes)
        except IngestionError as error:
            return refuse(error)
        try:
            started = clock().astimezone(UTC)
            try:
                run_request = await run_in_threadpool(_check_request, upload, config, services, base, settings)
            except IngestionError as error:
                upload.remove()
                return refuse(error)
            run_id = run_id_for(started, upload.sha256)
            try:
                jobs.submit(Job(run_id, run_request, upload.directory, started))
            except QueueFull:
                upload.remove()
                return JSONResponse(transport_body(BUSY), status_code=429, headers={"Retry-After": "60"})
            except Closing:
                upload.remove()
                return JSONResponse(transport_body(CLOSING), status_code=503)
            except IngestionError as error:
                upload.remove()
                return refuse(error)
        except BaseException:
            upload.remove()  # anything unexpected: nothing of the upload stays behind
            raise
        return JSONResponse({"run_id": run_id, "state": "queued"}, status_code=202)

    app.add_api_route("/runs", accept, methods=["POST"], status_code=202)

    def unknown() -> JSONResponse:
        return JSONResponse(transport_body(NOT_FOUND), status_code=404)

    def folder_of(run_id: str) -> Path | None:
        if not _RUN_ID.fullmatch(run_id):
            return None
        folder = settings.output_dir / run_id
        return folder if folder.is_dir() and not folder.is_symlink() else None

    def run_status(run_id: str) -> dict[str, object] | None:
        job = jobs.get(run_id)  # a dictionary lookup: any string is safe here
        if job is not None:
            return job_status(job)
        folder = folder_of(run_id)
        return folder_status(run_id, folder) if folder is not None else None

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> JSONResponse:
        status = run_status(run_id)
        return JSONResponse(status) if status is not None else unknown()

    def file_route(name: str):  # type: ignore[no-untyped-def]
        filename, media_type = MEDIA[name]

        async def get_file(run_id: str) -> Response:
            folder = folder_of(run_id)
            path = folder / filename if folder is not None else None
            if path is None or not path.is_file() or path.is_symlink():
                return unknown()
            return Response(await anyio.to_thread.run_sync(path.read_bytes), media_type=media_type)

        return get_file

    for file_name in MEDIA:  # /runs/{run_id}/memo, /results, /manifest, /report
        app.add_api_route(f"/runs/{{run_id}}/{file_name}", file_route(file_name), methods=["GET"])

    def listing() -> list[dict[str, object]]:
        listed: list[dict[str, object]] = []
        seen: set[str] = set()
        for job in reversed(jobs.jobs()):
            if job.state != "done":
                listed.append({"run_id": job.run_id, "state": job_status(job)["state"]})
                seen.add(job.run_id)
        on_disk = sorted((p for p in settings.output_dir.iterdir() if _RUN_ID.fullmatch(p.name)), reverse=True) if settings.output_dir.is_dir() else []
        for folder in on_disk:
            if len(listed) >= MAX_LISTED:
                break
            if folder.name in seen or folder.is_symlink():
                continue
            status = folder_status(folder.name, folder)
            if status is not None:
                listed.append({"run_id": folder.name, "state": status["state"]})
        return listed

    @app.get("/runs")
    async def list_runs() -> JSONResponse:
        return JSONResponse({"runs": listing()})

    def read_memo(run_id: str) -> str | None:
        folder = folder_of(run_id)
        path = folder / "memo.md" if folder is not None else None
        return path.read_text(encoding="utf-8") if path is not None and path.is_file() and not path.is_symlink() else None

    add_pages(app, config=config, listing=listing, status_of=run_status, read_memo=read_memo, accept=accept)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", **jobs.counts})

    return app
