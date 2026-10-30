"""A place is held before an upload is read, and an upload that goes quiet is cancelled (PRD OD-37, SEC-14; Phase 7 step 1, finding F-5).

Before this step the service read an upload to the end and only then asked the queue for room, so an authenticated caller could start many large uploads at once
and each would fill the disk before its ``429``. Now runs going, runs waiting and uploads arriving together stay within ``max_concurrent_runs + max_queued_runs``.
"""

import asyncio
import json
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api.app import create_app
from credit_intel.api.jobs import Closing, Job, QueueFull
from credit_intel.ingestion.errors import ErrorCode, IngestionError

BOUNDARY = "bnd"


def multipart(pdf_bytes, **fields):
    parts = b"".join(f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    head = f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'.encode()
    return head, pdf_bytes, f"\r\n--{BOUNDARY}--\r\n".encode() if not parts else b"\r\n" + parts + f"--{BOUNDARY}--\r\n".encode()


class Call:
    """One request made straight to the application, so that the test controls when each piece of the body arrives."""

    def __init__(self, app, chunks=(), *, then=None, headers=None):
        self.app, self.chunks, self.then = app, list(chunks), then
        self.reads = 0
        self.started: list[dict] = []
        self.body = b""
        self.headers = {"content-type": f"multipart/form-data; boundary={BOUNDARY}", "host": "testserver", **(headers or {})}

    async def receive(self):
        self.reads += 1
        if self.chunks:
            return {"type": "http.request", "body": self.chunks.pop(0), "more_body": True if self.chunks or self.then else False}
        if self.then is not None:
            return await self.then()
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(self, message):
        if message["type"] == "http.response.start":
            self.started.append(message)
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")

    async def run(self):
        scope = {"type": "http", "method": "POST", "path": "/runs", "raw_path": b"/runs", "query_string": b"", "http_version": "1.1", "scheme": "http",
                 "server": ("testserver", 80), "client": ("1.2.3.4", 1), "headers": [(k.lower().encode(), v.encode()) for k, v in self.headers.items()]}  # fmt: skip
        await self.app(scope, self.receive, self.send)
        return self

    @property
    def status(self):
        return self.started[0]["status"]

    @property
    def json(self):
        return json.loads(self.body)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def full_body(pdf, **fields):
    head, content, tail = multipart(pdf.read_bytes(), **fields)
    return [head + content + tail]


# --- the service is full: refused before the body is read ------------------------------------------------------------------------------------------


def test_a_full_service_answers_429_without_reading_a_byte_of_the_upload(pdf, tmp_path, private_temp):
    gate = base.Gate(pdf)
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=0, factory=gate)
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == 202
        assert gate.entered.acquire(timeout=30)  # one run is going: the one place is taken
        call = asyncio.run(Call(app, full_body(pdf)).run())
        assert call.status == 429 and call.reads == 0, "the body must not be read"
        assert call.json == {"code": None, "message": "Too many runs are waiting. Try again later."}
        assert dict(call.started[0]["headers"])[b"retry-after"] == b"60"
        gate.release.set()
        end = time.monotonic() + 30
        while app.state.jobs.counts["running"] and time.monotonic() < end:
            time.sleep(0.02)
    assert base.upload_leftovers(private_temp) == []


def test_the_form_post_of_the_page_is_also_refused_before_the_body_is_read(pdf, tmp_path):
    gate = base.Gate(pdf)
    app, _ = base.build(tmp_path, pdf, concurrent=1, queued=0, factory=gate)
    with TestClient(app) as client:
        base.post(client, pdf.read_bytes(), no_report=True)
        assert gate.entered.acquire(timeout=30)
        answer = client.post("/ui/submit", files={"file": ("a.pdf", pdf.read_bytes())}, follow_redirects=False)
        assert answer.status_code == 429 and "Too many runs are waiting" in answer.text
        gate.release.set()


def test_a_closing_service_answers_503_without_reading_the_body(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf)
    with TestClient(app):
        app.state.jobs.close()
        call = asyncio.run(Call(app, full_body(pdf)).run())
    assert call.status == 503 and call.reads == 0


# --- uploads in progress count against the same limits --------------------------------------------------------------------------------------------


def test_an_upload_still_arriving_holds_a_place_so_a_second_one_is_refused_at_once_and_the_first_is_then_accepted(pdf, tmp_path, private_temp):
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=0)
    data = full_body(pdf, no_report="true")[0]
    release = asyncio.Event

    async def scenario():
        hold = release()

        async def rest():
            await hold.wait()
            return {"type": "http.request", "body": data[len(data) // 2 :], "more_body": False}

        first = Call(app, [data[: len(data) // 2]], then=rest)
        task = asyncio.create_task(first.run())
        for _ in range(100):
            await asyncio.sleep(0.01)
            if app.state.jobs.uploading == 1:
                break
        assert app.state.jobs.uploading == 1  # the first upload holds the one place
        second = await Call(app, full_body(pdf)).run()
        assert second.status == 429 and second.reads == 0
        hold.set()
        await task
        return first

    with TestClient(app) as client:
        first = asyncio.run(scenario())
        assert first.status == 202, first.body
        base.wait(client, first.json["run_id"])
        assert app.state.jobs.uploading == 0
    assert base.upload_leftovers(private_temp) == []


def test_a_run_that_is_accepted_gives_up_only_its_own_place_and_not_that_of_an_upload_still_arriving(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf, concurrent=1, queued=2)
    data = full_body(pdf, no_report="true")[0]

    async def scenario():
        hold = asyncio.Event()

        async def rest():
            await hold.wait()
            return {"type": "http.request", "body": data[len(data) // 2 :], "more_body": False}

        slow = Call(app, [data[: len(data) // 2]], then=rest)
        task = asyncio.create_task(slow.run())
        for _ in range(100):
            await asyncio.sleep(0.01)
            if app.state.jobs.uploading == 1:
                break
        quick = await Call(app, [pdf_with(1)]).run()
        assert quick.status == 202 and app.state.jobs.uploading == 1  # the quick one is queued; the slow one still holds its place
        hold.set()
        await task
        assert slow.status == 202 and app.state.jobs.uploading == 0

    def pdf_with(n):
        head, content, tail = multipart(pdf.read_bytes() + f"\n%{n}".encode(), no_report="true")
        return head + content + tail

    with TestClient(app):
        asyncio.run(scenario())


def test_every_way_an_upload_can_end_gives_its_place_back(pdf, tmp_path, private_temp):
    """Capacity is two. More than two failures in a row, then a good request: it is accepted only if every failure released its place."""
    app, settings = base.build(tmp_path, pdf, concurrent=1, queued=1, max_file_bytes=200_000)
    good = pdf.read_bytes()
    with TestClient(app) as client:
        failures = [
            lambda: base.post(client, b"not a pdf"),                                       # E-INPUT-NOT-PDF while streaming
            lambda: base.post(client, b"%PDF-" + b"x" * 300_000),                           # E-INPUT-TOO-LARGE while streaming
            lambda: base.post(client, good, basis="neither"),                               # E-API-REQUEST in the checks
            lambda: base.post(client, good, pages="abc"),                                   # E-INPUT-PAGE-RANGE in the checks
            lambda: base.post(client, good, profile="{bad"),                                # E-INPUT-PROFILE-INVALID in the checks
            lambda: client.post("/runs", json={"a": 1}),                                    # not multipart
            lambda: client.post("/runs", content=b"junk", headers={"content-type": f"multipart/form-data; boundary={BOUNDARY}"}),  # a broken body
        ]  # fmt: skip
        for attempt in failures * 2:
            assert attempt().status_code in (413, 422)
            assert app.state.jobs.uploading == 0
        assert base.post(client, good, no_report=True).status_code == 202
    assert app.state.jobs.uploading == 0


def test_a_client_that_disconnects_mid_upload_gives_its_place_back(pdf, tmp_path, private_temp):
    app, _ = base.build(tmp_path, pdf, concurrent=1, queued=0)

    async def gone():
        return {"type": "http.disconnect"}

    data = full_body(pdf)[0]
    call = asyncio.run(Call(app, [data[:2000]], then=gone).run())
    assert app.state.jobs.uploading == 0 and call.status == 422
    assert base.upload_leftovers(private_temp) == []
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == 202


def test_a_duplicate_run_id_uses_up_the_place_it_held(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf, concurrent=1, queued=2, clock=lambda: datetime(2026, 10, 30, tzinfo=UTC))
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == 202
        assert base.post(client, pdf.read_bytes(), no_report=True).json()["code"] == "E-API-REQUEST"
        assert app.state.jobs.uploading == 0


# --- an upload that goes quiet --------------------------------------------------------------------------------------------------------------------


def test_an_upload_that_sends_nothing_for_the_idle_time_is_cancelled_with_408_and_leaves_nothing(pdf, tmp_path, private_temp):
    settings = base.settings_for(tmp_path, 1, 1)
    config = base.config_for(tmp_path)
    app = create_app(settings, config=config, services=base.services_for(pdf, tmp_path), env={}, clock=base.ticker(), upload_idle_seconds=0.3)

    async def silence():
        await asyncio.Event().wait()  # the client has stopped sending but has not disconnected

    data = full_body(pdf)[0]
    begun = time.monotonic()
    call = asyncio.run(Call(app, [data[:1500]], then=silence).run())
    assert call.status == 408 and call.json == {"code": None, "message": "The upload stopped arriving and was cancelled."}
    assert time.monotonic() - begun < 5
    assert app.state.jobs.uploading == 0 and base.upload_leftovers(private_temp) == [] and not settings.output_dir.exists()
    assert dict(call.started[0]["headers"])[b"cache-control"] == b"no-store"  # it still carries the policy


def test_a_steady_upload_that_takes_longer_than_the_idle_time_in_all_is_not_cancelled(pdf, tmp_path):
    settings = base.settings_for(tmp_path, 1, 1)
    app = create_app(settings, config=base.config_for(tmp_path), services=base.services_for(pdf, tmp_path), env={}, clock=base.ticker(), upload_idle_seconds=0.5)
    data = full_body(pdf, no_report="true")[0]
    pieces = [data[i : i + 400] for i in range(0, len(data), 400)]
    assert len(pieces) >= 4  # at 0.2 s each, longer than the idle time of 0.5 s in all

    async def trickle():
        await asyncio.sleep(0.2)  # less than the idle time, three or more times: slower than the idle time as a whole
        return {"type": "http.request", "body": pieces.pop(0), "more_body": bool(pieces)} if pieces else {"type": "http.request", "body": b"", "more_body": False}

    first = pieces.pop(0)
    with TestClient(app) as client:
        call = asyncio.run(Call(app, [first], then=trickle).run())
        assert call.status == 202, call.body
        base.wait(client, call.json["run_id"])


# --- the manager's accounting -------------------------------------------------------------------------------------------------------------------


def manager(tmp_path, concurrent=1, queued=1):
    from credit_intel.api.jobs import JobManager
    from credit_intel.service import RunServices

    return JobManager(base.settings_for(tmp_path, concurrent, queued), base.config_for(tmp_path), RunServices(), {}, base.ticker())


def test_reservations_stop_at_the_total_of_both_limits_and_a_release_makes_room(tmp_path):
    jobs = manager(tmp_path, 1, 2)
    for _ in range(3):
        jobs.reserve()
    assert jobs.uploading == 3
    with pytest.raises(QueueFull):
        jobs.reserve()
    jobs.release()
    jobs.reserve()
    with pytest.raises(QueueFull):
        jobs.reserve()
    jobs.close()
    with pytest.raises(Closing):
        jobs.reserve()


def test_release_never_goes_below_zero(tmp_path):
    jobs = manager(tmp_path)
    jobs.release()
    jobs.release()
    assert jobs.uploading == 0
    jobs.reserve()
    assert jobs.uploading == 1


def test_an_unreserved_submit_still_counts_uploads_against_the_limits(tmp_path, pdf):
    jobs = manager(tmp_path, 1, 0)
    jobs.reserve()
    job = Job("20261030T101530.123456Z-abcdef12", None, tmp_path / "u", datetime(2026, 10, 30, tzinfo=UTC))
    with pytest.raises(QueueFull):
        jobs.submit(job)  # the one place is held by the upload that is still arriving
    assert jobs.uploading == 1


def test_a_reserved_submit_uses_its_place_up_even_when_it_is_refused(tmp_path):
    jobs = manager(tmp_path, 1, 1)
    jobs.close()
    jobs.reserve  # noqa: B018
    jobs._uploading = 1  # a place that was held before the service began to close
    with pytest.raises(Closing):
        jobs.submit(Job("20261030T101530.123456Z-abcdef12", None, tmp_path / "u", datetime(2026, 10, 30, tzinfo=UTC)), reserved=True)
    assert jobs.uploading == 0
