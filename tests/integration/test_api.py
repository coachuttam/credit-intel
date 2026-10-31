"""The HTTP API core (PRD FR-016, v0.4.59; Phase 6 step 2): submission, the job pool, status, the files, the error mapping and the deadline.

All synthetic and offline: the fake provider, synthetic PDFs, FastAPI's test client. Uploads and exposure hardening (SEC-14, SEC-15) are step 3.
"""

import io
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
from credit_intel.api.app import create_app
from credit_intel.api.errors import HTTP_AT_SUBMISSION, error_body, status_of
from credit_intel.api.jobs import JobManager
from credit_intel.cli import main
from credit_intel.config import ApiSettings
from credit_intel.evaluation.guard import ENV_PRIVATE_APPROVED, MEMBERS
from credit_intel.ingestion.errors import CATALOGUE, ErrorCode, IngestionError
from credit_intel.llm.provider import FakeProvider
from credit_intel.service import RunServices

START = datetime(2026, 10, 30, 10, 15, 30, 123456, tzinfo=UTC)
LLM = '[llm]\nprovider = "{provider}"\nmodel_id = "m"\ntoken_ceiling = 1000000\nmax_output_tokens = 2000\n'
RUN_ID = r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{8}"


def ticker(start=START):
    lock, count = threading.Lock(), [0]

    def clock():
        with lock:
            count[0] += 1
            return start + timedelta(milliseconds=7 * count[0])

    return clock


@pytest.fixture(autouse=True)
def private_temp(tmp_path, monkeypatch):
    """Uploads go to the system temporary directory; point it at a folder of the test so that what is left behind can be seen."""
    import tempfile

    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def settings_for(tmp_path, concurrent=1, queued=4, timeout=1200):
    return ApiSettings(concurrent, queued, timeout, tmp_path / "out", tmp_path / "cache")


def config_for(tmp_path, provider="fake"):
    path = tmp_path / "settings.toml"
    path.write_text(LLM.format(provider=provider), encoding="utf-8")
    return path


def records(tmp_path, *rows):
    path = tmp_path / "assignments.jsonl"
    lines = [json.dumps(dict(zip(MEMBERS, (doc, sha, group, "2026-10-24", "assigned", None, None), strict=True))) for doc, sha, group in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def services_for(pdf, tmp_path, factory=None, **extra):
    return RunServices(provider_factory=factory or (lambda s, e: FakeProvider(script=[fx.good_response(pdf)])), assignments=tmp_path / "none.jsonl", **extra)


def build(tmp_path, pdf, *, provider="fake", concurrent=1, queued=4, timeout=1200, factory=None, assignments=None, env=None, monotonic=None, max_file_bytes=None,
          services=None, clock=None, failed_attempts=None):  # fmt: skip
    settings = settings_for(tmp_path, concurrent, queued, timeout)
    config = config_for(tmp_path, provider)
    services = services or services_for(pdf, tmp_path, factory)
    if assignments is not None:
        services = RunServices(services.provider_factory, services.classifier_factory, services.ocr_factory, services.extractor_factory, assignments)
    clock = clock or ticker()
    manager = None
    if monotonic is not None:
        manager = JobManager(settings, config, services, env or {}, clock, monotonic)
    return create_app(settings, config=config, services=services, env=env or {}, clock=clock, manager=manager, max_file_bytes=max_file_bytes, failed_attempts=failed_attempts), settings


def post(client, pdf_bytes, name="statement.pdf", **fields):
    return client.post("/runs", files={"file": (name, pdf_bytes, "application/pdf")}, data={k: str(v).lower() if isinstance(v, bool) else v for k, v in fields.items()})


def wait(client, run_id, until=("exported", "failed"), seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        body = client.get(f"/runs/{run_id}").json()
        if body["state"] in until:
            return body
        time.sleep(0.02)
    raise AssertionError(f"the run did not finish: {body}")


def upload_leftovers(private_temp):
    return [p.name for p in private_temp.iterdir()]


# --- a good run ----------------------------------------------------------------------------------------------------------------------------


def test_a_good_run_is_accepted_with_its_run_id_runs_and_serves_its_files_byte_for_byte(pdf, tmp_path, private_temp):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = post(client, pdf.read_bytes(), no_report=True)
        assert answer.status_code == 202 and set(answer.json()) == {"run_id", "state"} and answer.json()["state"] == "queued"
        run_id = answer.json()["run_id"]
        status = wait(client, run_id)
        assert status["state"] == "exported" and status["files"] == ["memo.md", "results.json", "manifest.json"]
        assert [s["state"] for s in status["stages"]][0] == "received" and status["stages"][-1]["state"] == "exported"
        folder = settings.output_dir / run_id
        assert folder.is_dir(), "the 202 carried the ID the folder has"
        for name, filename, media in (("memo", "memo.md", "text/markdown"), ("results", "results.json", "application/json"), ("manifest", "manifest.json", "application/json")):
            got = client.get(f"/runs/{run_id}/{name}")
            assert got.status_code == 200 and got.content == (folder / filename).read_bytes() and got.headers["content-type"].startswith(media)
        assert client.get(f"/runs/{run_id}/report").status_code == 404  # no_report: there is no report.pdf
    assert upload_leftovers(private_temp) == []


def test_the_report_is_served_when_the_run_wrote_one(pdf, tmp_path, real_report):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes()).json()["run_id"]
        assert wait(client, run_id)["files"] == ["memo.md", "results.json", "manifest.json", "report.pdf"]
        got = client.get(f"/runs/{run_id}/report")
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf" and got.content == (settings.output_dir / run_id / "report.pdf").read_bytes()


def test_the_api_writes_the_same_memo_and_results_as_the_command_line(pdf, tmp_path, monkeypatch):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), no_report=True, name="statement.pdf").json()["run_id"]
        wait(client, run_id)
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")
    out = io.StringIO()
    code = main([str(pdf), "--config", str(config_for(tmp_path)), "--output-dir", str(tmp_path / "cli"), "--no-report"], stdout=out, stderr=io.StringIO(),
                provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(pdf)]), clock=ticker(), assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    assert code == 0
    cli_folder = Path(out.getvalue().strip())
    for name in ("memo.md", "results.json"):
        assert (settings.output_dir / run_id / name).read_bytes() == (cli_folder / name).read_bytes()


def test_the_recorded_input_name_is_the_sanitised_client_name_and_nothing_of_the_path(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), name="../../etc/pass wd<1>.pdf", no_report=True).json()["run_id"]
        wait(client, run_id)
    manifest = json.loads((settings.output_dir / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert "pass wd_1_.pdf" in json.dumps(manifest) and "etc" not in json.dumps(manifest) and ".." not in json.dumps(manifest)
    assert [p.name for p in tmp_path.rglob("etc")] == []


# --- the checks made in the request (point 1) --------------------------------------------------------------------------------------------------


def body_of(answer):
    return answer.status_code, answer.json()["code"]


def test_a_file_without_the_pdf_signature_is_422_not_pdf_and_no_run_is_made(pdf, tmp_path, private_temp):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = post(client, b"hello, not a pdf at all")
        assert body_of(answer) == (422, "E-INPUT-NOT-PDF") and set(answer.json()) == {"code", "message"}
        assert post(client, b"").status_code == 422 and post(client, b"%PD").json()["code"] == "E-INPUT-NOT-PDF"
        assert client.get("/runs").json() == {"runs": []}
    assert not settings.output_dir.exists() and upload_leftovers(private_temp) == []


def test_an_upload_over_the_limit_is_413_from_the_header_and_while_streaming(pdf, tmp_path, private_temp):
    app, settings = build(tmp_path, pdf, max_file_bytes=2000)
    boundary = "xBOUNDARYx"
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n%PDF-1.4\n'.encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    with TestClient(app) as client:
        assert post(client, b"%PDF-" + b"x" * 5000).json()["code"] == "E-INPUT-TOO-LARGE"
        chunked = client.post("/runs", content=iter([head, b"x" * 1500, b"x" * 1500, tail]), headers={"content-type": f"multipart/form-data; boundary={boundary}"})
        assert body_of(chunked) == (413, "E-INPUT-TOO-LARGE")  # no Content-Length at all: cut off while streaming
        huge = client.post("/runs", content=b"x", headers={"content-type": f"multipart/form-data; boundary={boundary}", "content-length": str(10_000_000)})
        assert body_of(huge) == (413, "E-INPUT-TOO-LARGE")
    assert upload_leftovers(private_temp) == [] and not settings.output_dir.exists()


@pytest.mark.parametrize("fields", [
    {"basis": "neither"}, {"ocr": "maybe"}, {"no_report": "1"}, {"confirm_public_document": "yes"}, {"assert_basis": "standalone"},
    {"assert_basis": "sideways", "pages": "1"}, {"surprise": "1"}, {"pages": "1" * 300},
], ids=lambda f: next(iter(f)))  # fmt: skip
def test_a_malformed_request_is_422_api_request(pdf, tmp_path, fields):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert body_of(post(client, pdf.read_bytes(), **fields)) == (422, "E-API-REQUEST")


def test_a_request_with_no_file_or_not_multipart_is_422_api_request(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert body_of(client.post("/runs", data={"basis": "consolidated"}, files={"x": ("x", b"y")})) == (422, "E-API-REQUEST")
        assert body_of(client.post("/runs", json={"a": 1})) == (422, "E-API-REQUEST")
        assert body_of(client.post("/runs", content=b"garbage", headers={"content-type": "multipart/form-data; boundary=zz"})) == (422, "E-API-REQUEST")


def test_a_bad_profile_or_page_range_is_422_with_its_catalogued_code(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert body_of(post(client, pdf.read_bytes(), profile="{not json")) == (422, "E-INPUT-PROFILE-INVALID")
        assert body_of(post(client, pdf.read_bytes(), profile=json.dumps({"surprise": "x"}))) == (422, "E-INPUT-PROFILE-INVALID")
        assert body_of(post(client, pdf.read_bytes(), pages="9-1")) == (422, "E-INPUT-PAGE-RANGE")
        assert body_of(post(client, pdf.read_bytes(), pages="abc")) == (422, "E-INPUT-PAGE-RANGE")
        assert body_of(post(client, pdf.read_bytes(), pages="1-100000")) == (422, "E-INPUT-PAGE-RANGE")


def test_a_good_profile_and_options_reach_the_run(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    profile = json.dumps({"borrower_name": "Acme Industries Limited"})
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), profile=profile, pages="1", assert_basis="consolidated", no_report=True).json()["run_id"]
        assert wait(client, run_id)["state"] == "exported"
    assert "Acme Industries Limited" in (settings.output_dir / run_id / "memo.md").read_text(encoding="utf-8")


def test_the_send_rule_applies_to_an_upload_a_held_out_document_is_403_and_a_public_one_needs_the_confirmation(pdf, tmp_path):
    sha = fx_sha(pdf)
    held = records(tmp_path, ("doc", sha, "held_out"))
    app, settings = build(tmp_path, pdf, provider="openai", assignments=held)
    with TestClient(app) as client:
        answer = post(client, pdf.read_bytes(), confirm_public_document=True)
        assert body_of(answer) == (403, "E-INPUT-SEND-REFUSED") and "held_out" in answer.json()["message"]
    assert not settings.output_dir.exists()
    app, settings = build(tmp_path, pdf, provider="openai")
    with TestClient(app) as client:
        answer = post(client, pdf.read_bytes())
        assert body_of(answer) == (403, "E-INPUT-SEND-REFUSED") and "not_recorded" in answer.json()["message"]
        accepted = post(client, pdf.read_bytes(), confirm_public_document=True, no_report=True)
        assert accepted.status_code == 202 and wait(client, accepted.json()["run_id"])["state"] == "exported"


def fx_sha(path):
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_private_approval_variable_is_never_honoured_by_the_api(pdf, tmp_path):
    app, _ = build(tmp_path, pdf, env={ENV_PRIVATE_APPROVED: "1", "KEEP": "me"})
    assert app.state.jobs.env == {"KEEP": "me"}


def test_an_ocr_request_with_no_engine_installed_is_503_before_a_run_exists(pdf, tmp_path):
    class Missing:
        def check_available(self):
            raise IngestionError(ErrorCode.OCR_UNAVAILABLE)

    services = services_for(pdf, tmp_path, ocr_factory=Missing)
    app, settings = build(tmp_path, pdf, services=services)
    with TestClient(app) as client:
        assert body_of(post(client, pdf.read_bytes(), ocr=True, pages="1")) == (503, "E-INPUT-OCR-UNAVAILABLE")
    assert not settings.output_dir.exists()


def test_bad_settings_for_the_run_are_500_config_invalid_in_the_request(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    (tmp_path / "settings.toml").write_text("[llm]\nprovider = 'fake'\n", encoding="utf-8")  # no token ceiling
    with TestClient(app) as client:
        assert body_of(post(client, pdf.read_bytes())) == (500, "E-CONFIG-INVALID")


# --- after acceptance: the status ----------------------------------------------------------------------------------------------------------------


def test_a_failure_after_acceptance_is_in_the_status_with_its_code_and_a_manifest_only_folder(tmp_path, private_temp):
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"%PDF-1.4\nthis is not a real pdf\n")
    app, settings = build(tmp_path, fx.balance_sheet_pdf(tmp_path / "other.pdf"))
    with TestClient(app) as client:
        answer = post(client, pdf.read_bytes())
        assert answer.status_code == 202
        run_id = answer.json()["run_id"]
        status = wait(client, run_id)
        assert client.get(f"/runs/{run_id}").status_code == 200  # the answer is 200; the failure is in the body
        assert status["state"] == "failed" and status["error"]["code"] == "E-INPUT-CORRUPT" and "Re-download" in status["error"]["message"]
        assert status["files"] == ["manifest.json"] and client.get(f"/runs/{run_id}/memo").status_code == 404
        assert client.get(f"/runs/{run_id}/manifest").status_code == 200
    assert upload_leftovers(private_temp) == []


def test_an_internal_error_has_no_code_and_a_fixed_message_and_no_trace(pdf, tmp_path):
    def boom(settings, env):
        raise RuntimeError("secret detail /Users/x key sk-abc")

    app, _ = build(tmp_path, pdf, factory=boom)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes()).json()["run_id"]
        status = wait(client, run_id)
    assert status["state"] == "failed" and status["error"] == {"code": None, "message": "Internal error. Re-run, and report it if it persists."}
    assert "secret" not in json.dumps(status) and "sk-" not in json.dumps(status)


def test_a_finished_run_is_still_answered_after_a_restart_from_its_manifest(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        wait(client, run_id)
    again, _ = build(tmp_path, pdf)  # a new process: nothing in memory
    with TestClient(again) as client:
        status = client.get(f"/runs/{run_id}").json()
        assert status == {"run_id": run_id, "state": "exported", "files": ["memo.md", "results.json", "manifest.json"]}
        assert client.get(f"/runs/{run_id}/memo").status_code == 200


# --- run IDs, listing, health, the endpoint set --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["%2e%2e", "x", "20261030T101530.123456Z-ABCDEF12", "20261030T101530.123456Z-abcdef1", "20261030T101530.123456Z-abcdef123",
                                 "..%2f..%2fprivate", "20261030T101530.123456Z-abcdef12%00", "private", "20261030T101530.123456Z-abcdef12%2f%2e%2e"])  # fmt: skip
def test_a_string_that_is_not_a_run_id_is_404_before_the_disk_is_touched(pdf, tmp_path, bad):
    app, settings = build(tmp_path, pdf)
    settings.output_dir.mkdir()
    (settings.output_dir.parent / "private").mkdir()
    with TestClient(app) as client:
        for path in (f"/runs/{bad}", f"/runs/{bad}/memo", f"/runs/{bad}/manifest"):
            assert client.get(path).status_code == 404
        assert client.get(f"/runs/{bad}").json() == {"code": None, "message": "There is no such run or file."}


def test_an_unknown_run_with_the_right_form_is_404(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert client.get("/runs/20261030T101530.123456Z-abcdef12").status_code == 404
        assert client.get("/runs/20261030T101530.123456Z-abcdef12/report").status_code == 404


def test_a_symlinked_run_folder_or_file_is_never_followed(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    settings.output_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "memo.md").write_text("secret", encoding="utf-8")
    (outside / "manifest.json").write_text(json.dumps({"final_state": "exported"}), encoding="utf-8")
    run_id = "20261030T101530.123456Z-abcdef12"
    (settings.output_dir / run_id).symlink_to(outside)
    with TestClient(app) as client:
        assert client.get(f"/runs/{run_id}").status_code == 404 and client.get(f"/runs/{run_id}/memo").status_code == 404
    (settings.output_dir / run_id).unlink()
    (settings.output_dir / run_id).mkdir()
    (settings.output_dir / run_id / "manifest.json").write_text(json.dumps({"final_state": "exported"}), encoding="utf-8")
    (settings.output_dir / run_id / "memo.md").symlink_to(outside / "memo.md")
    with TestClient(app) as client:
        assert client.get(f"/runs/{run_id}/memo").status_code == 404


def test_the_list_is_newest_first_capped_at_100_and_includes_runs_from_before_a_restart(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    settings.output_dir.mkdir()
    ids = sorted(f"{(START + timedelta(minutes=m)).strftime('%Y%m%dT%H%M%S.%fZ')}-abcdef12" for m in range(130))
    for run_id in ids:
        (settings.output_dir / run_id).mkdir()
        (settings.output_dir / run_id / "manifest.json").write_text(json.dumps({"final_state": "exported"}), encoding="utf-8")
    (settings.output_dir / "not-a-run").mkdir()
    (settings.output_dir / ".20261030T101530.123456Z-abcdef12.partial").mkdir()
    with TestClient(app) as client:
        listed = client.get("/runs").json()["runs"]
    assert len(ids) > 100 and len(listed) == 100
    assert [r["run_id"] for r in listed] == sorted(ids, reverse=True)[:100] and {r["state"] for r in listed} == {"exported"}


def test_health_shows_only_the_queue_and_needs_nothing_else(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "queued": 0, "running": 0}


def test_the_openapi_document_lists_exactly_the_endpoints_and_serves_no_docs_pages(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    paths = {path: sorted(methods) for path, methods in app.openapi()["paths"].items()}
    assert paths == {"/runs": ["get", "post"], "/runs/{run_id}": ["get"], "/runs/{run_id}/memo": ["get"], "/runs/{run_id}/results": ["get"],
                     "/runs/{run_id}/manifest": ["get"], "/runs/{run_id}/report": ["get"], "/health": ["get"]}  # fmt: skip
    with TestClient(app) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.delete("/runs/20261030T101530.123456Z-abcdef12").status_code == 405
        assert client.put("/runs").status_code == 405


# --- the error mapping ---------------------------------------------------------------------------------------------------------------------------


def test_every_catalogued_code_has_an_http_mapping_and_the_status_follows_it():
    assert set(HTTP_AT_SUBMISSION) == set(ErrorCode) == set(CATALOGUE)
    for code, status in HTTP_AT_SUBMISSION.items():
        assert status is None or status in (403, 413, 422, 500, 503)
        assert status_of(IngestionError(code)) == (status or 500)
    assert {c.value: s for c, s in HTTP_AT_SUBMISSION.items() if s} == {
        "E-INPUT-TOO-LARGE": 413, "E-INPUT-NOT-PDF": 422, "E-INPUT-SEND-REFUSED": 403, "E-INPUT-PROFILE-INVALID": 422, "E-INPUT-PAGE-RANGE": 422,
        "E-API-REQUEST": 422, "E-CONFIG-INVALID": 500, "E-INPUT-NOT-FOUND": 500, "E-INPUT-OCR-UNAVAILABLE": 503}  # fmt: skip


def test_an_error_body_is_the_code_and_the_fixed_message_only():
    body = error_body(IngestionError(ErrorCode.SEND_REFUSED, detail="held_out"))
    assert set(body) == {"code", "message"} and body["code"] == "E-INPUT-SEND-REFUSED" and body["message"].endswith("(held_out)")
    assert not body["message"].startswith("E-")


# --- the queue and the limits ------------------------------------------------------------------------------------------------------------------


class Gate:
    """A provider that waits for the test before it answers, so that runs can be held in the pool."""

    def __init__(self, pdf):
        self.pdf, self.release, self.entered = pdf, threading.Event(), threading.Semaphore(0)

    def __call__(self, settings, env):
        gate = self

        class Provider:
            def complete(self, request):
                gate.entered.release()
                assert gate.release.wait(30)
                return FakeProvider(script=[fx.good_response(gate.pdf)]).complete(request)

        return Provider()


def distinct_pdfs(tmp_path, n):
    paths = []
    for i in range(n):
        path = fx.balance_sheet_pdf(tmp_path / f"s{i}.pdf", title="Consolidated Balance Sheet")
        path.write_bytes(path.read_bytes() + b"\n%" + str(i).encode() * 8)  # a different document (and hash) each time
        paths.append(path)
    return paths


def test_runs_beyond_the_pool_and_the_queue_are_429_with_retry_after_and_all_accepted_runs_finish(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    gate = Gate(pdf)
    app, _ = build(tmp_path, pdf, concurrent=1, queued=1, factory=gate)
    with TestClient(app) as client:
        first = post(client, pdf.read_bytes(), no_report=True)
        assert first.status_code == 202
        assert gate.entered.acquire(timeout=30)  # the first run is in the model call: it holds the one slot
        second = post(client, pdf.read_bytes() + b"\n%2", no_report=True)
        assert second.status_code == 202 and client.get(f"/runs/{second.json()['run_id']}").json()["state"] == "queued"
        assert client.get("/health").json() == {"status": "ok", "queued": 1, "running": 1}
        third = post(client, pdf.read_bytes() + b"\n%3", no_report=True)
        assert third.status_code == 429 and third.headers["retry-after"] and third.json() == {"code": None, "message": "Too many runs are waiting. Try again later."}
        gate.release.set()
        assert wait(client, first.json()["run_id"])["state"] in ("exported", "failed")
        assert wait(client, second.json()["run_id"])["state"] in ("exported", "failed")
        assert client.get("/health").json() == {"status": "ok", "queued": 0, "running": 0}


def test_two_runs_never_run_at_once_when_the_limit_is_one(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    gate = Gate(pdf)
    app, _ = build(tmp_path, pdf, concurrent=1, queued=2, factory=gate)
    with TestClient(app) as client:
        ids = [post(client, pdf.read_bytes() + f"\n%{i}".encode(), no_report=True).json()["run_id"] for i in range(2)]
        assert gate.entered.acquire(timeout=30)
        assert not gate.entered.acquire(timeout=0.5), "the second run must wait for the one slot"
        assert client.get("/health").json()["running"] == 1
        gate.release.set()
        for run_id in ids:
            wait(client, run_id)


def test_the_same_document_in_the_same_microsecond_is_not_accepted_twice(pdf, tmp_path):
    frozen = lambda: START  # noqa: E731
    app, _ = build(tmp_path, pdf, clock=frozen)
    with TestClient(app) as client:
        assert post(client, pdf.read_bytes(), no_report=True).status_code == 202
        assert body_of(post(client, pdf.read_bytes(), no_report=True)) == (422, "E-API-REQUEST")


# --- the whole-run deadline (cooperative; FR-016 criterion 10 and 10a) ------------------------------------------------------------------------------


class Time:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_a_run_past_its_deadline_ends_with_run_timeout_at_the_next_check_and_leaves_a_failure_record(pdf, tmp_path, private_temp):
    time_ = Time()
    inside = threading.Event()
    go = threading.Event()

    def factory(settings, env):
        class Provider:
            def complete(self, request):
                time_.now += 5000  # the model call outlasts the limit
                inside.set()
                assert go.wait(30)
                return FakeProvider(script=[fx.good_response(pdf)]).complete(request)

        return Provider()

    app, settings = build(tmp_path, pdf, timeout=1200, factory=factory, monotonic=time_)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        assert inside.wait(30)
        running = client.get(f"/runs/{run_id}").json()
        assert running["deadline_passed"] is True and running["state"] != "failed"  # the stage is not interrupted: the status says the deadline has passed
        assert client.get("/health").json()["running"] == 1  # and the slot is still held
        go.set()
        status = wait(client, run_id)
    assert status["state"] == "failed" and status["error"]["code"] == "E-RUN-TIMEOUT" and "limit" in status["error"]["message"]
    assert status["files"] == ["manifest.json"]
    manifest = json.loads((settings.output_dir / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["final_state"] == "failed" and manifest["error_code"] == "E-RUN-TIMEOUT"
    assert upload_leftovers(private_temp) == []


def test_a_run_inside_its_deadline_is_not_stopped(pdf, tmp_path):
    time_ = Time()
    app, _ = build(tmp_path, pdf, timeout=1200, monotonic=time_)
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        assert wait(client, run_id)["state"] == "exported"


def test_the_deadline_is_checked_before_a_model_call(pdf, tmp_path):
    time_ = Time()
    calls = []

    def factory(settings, env):
        class Provider:
            def complete(self, request):
                calls.append(1)
                return FakeProvider(script=[fx.good_response(pdf)]).complete(request)

        return Provider()

    app, _ = build(tmp_path, pdf, timeout=1, factory=factory, monotonic=time_)

    def tick_on_enter():  # the clock passes the limit as soon as the run has started
        time_.now += 10

    original = app.state.jobs.clock
    app.state.jobs.clock = lambda: (tick_on_enter(), original())[1]
    with TestClient(app) as client:
        run_id = post(client, pdf.read_bytes(), no_report=True).json()["run_id"]
        status = wait(client, run_id)
    assert status["state"] == "failed" and status["error"]["code"] == "E-RUN-TIMEOUT" and calls == []  # stopped before the model was called


def test_closing_removes_the_uploads_of_runs_that_never_started_and_the_running_one_cleans_up_when_it_ends(pdf, tmp_path, private_temp):
    gate = Gate(pdf)
    app, _ = build(tmp_path, pdf, concurrent=1, queued=2, factory=gate)
    with TestClient(app) as client:
        post(client, pdf.read_bytes(), no_report=True)
        assert gate.entered.acquire(timeout=30)
        post(client, pdf.read_bytes() + b"\n%2", no_report=True)
        assert len(upload_leftovers(private_temp)) == 2  # one running, one waiting
    assert len(upload_leftovers(private_temp)) == 1  # shut down: the waiting run will never start, so its upload is gone
    gate.release.set()
    end = time.monotonic() + 30
    while app.state.jobs.counts["running"] and time.monotonic() < end:
        time.sleep(0.02)
    assert upload_leftovers(private_temp) == []
    with pytest.raises(Exception):
        app.state.jobs.submit(None)  # a closed manager accepts nothing


def test_a_submission_while_closing_is_503(pdf, tmp_path, private_temp):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        app.state.jobs.close()
        answer = post(client, pdf.read_bytes(), no_report=True)
        assert answer.status_code == 503 and answer.json() == {"code": None, "message": "The service is shutting down. Try again later."}
    assert upload_leftovers(private_temp) == []


def test_the_deadline_is_checked_before_a_corrective_retry_of_the_model_which_changes_no_state(pdf, tmp_path):
    time_ = Time()
    calls = []

    def factory(settings, env):
        inner = FakeProvider(script=["this is not json", fx.good_response(pdf)])

        class Provider:
            def complete(self, request):
                calls.append(1)
                if len(calls) == 1:
                    time_.now += 5000  # the first call outlasts the limit; the retry would be the second
                return inner.complete(request)

        return Provider()

    app, _ = build(tmp_path, pdf, timeout=1200, factory=factory, monotonic=time_)
    with TestClient(app) as client:
        status = wait(client, post(client, pdf.read_bytes(), no_report=True).json()["run_id"])
    assert status["error"]["code"] == "E-RUN-TIMEOUT" and len(calls) == 1


# --- an upload, part by part (SEC-14 groundwork; the rest is step 3) ------------------------------------------------------------------------------------


def raw(client, parts, boundary="bnd"):
    body = b"".join(f"--{boundary}\r\n".encode() + head.encode() + b"\r\n\r\n" + content + b"\r\n" for head, content in parts) + f"--{boundary}--\r\n".encode()
    return client.post("/runs", content=body, headers={"content-type": f"multipart/form-data; boundary={boundary}"})


FILE = 'Content-Disposition: form-data; name="file"; filename="a.pdf"'


def field(name):
    return f'Content-Disposition: form-data; name="{name}"'


def test_a_second_file_a_file_part_without_a_name_a_repeated_field_and_too_many_or_too_large_fields_are_422_api_request(pdf, tmp_path, private_temp):
    app, _ = build(tmp_path, pdf)
    data = pdf.read_bytes()
    with TestClient(app) as client:
        assert body_of(raw(client, [(FILE, data), (FILE, data)])) == (422, "E-API-REQUEST")
        assert body_of(raw(client, [(field("file"), data)])) == (422, "E-API-REQUEST")  # `file` must be a file part
        assert body_of(raw(client, [(FILE, data), (field("basis"), b"consolidated"), (field("basis"), b"consolidated")])) == (422, "E-API-REQUEST")
        assert body_of(raw(client, [(FILE, data), ('Content-Disposition: form-data; name="pages"; filename="x"', b"1")])) == (422, "E-API-REQUEST")
        many = [(FILE, data)] + [(field(f"f{i}"), b"x") for i in range(17)]
        assert body_of(raw(client, many)) == (422, "E-API-REQUEST")
        assert body_of(raw(client, [(FILE, data), (field("profile"), b"x" * 20_000)])) == (422, "E-API-REQUEST")
        assert body_of(raw(client, [(FILE, data), (field("pages"), b"\xff\xfe")])) == (422, "E-API-REQUEST")  # a field that is not UTF-8
    assert upload_leftovers(private_temp) == []


def test_a_file_that_is_not_a_pdf_is_refused_at_its_first_bytes_even_if_it_is_also_too_large(pdf, tmp_path):
    app, _ = build(tmp_path, pdf, max_file_bytes=2000)
    with TestClient(app) as client:
        chunked = client.post("/runs", content=iter([b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\nhello', b"x" * 5000, b"\r\n--b--\r\n"]),
                              headers={"content-type": "multipart/form-data; boundary=b"})  # fmt: skip
        assert body_of(chunked) == (422, "E-INPUT-NOT-PDF")


@pytest.mark.parametrize("given, expected", [
    ("..", "upload.pdf"), (".hidden.pdf", "hidden.pdf"), ("../../etc/passwd", "passwd"), ("C:\\x\\y.pdf", "y.pdf"), ("a b<c>.pdf", "a b_c_.pdf"), ("", "upload.pdf"),
    (None, "upload.pdf"), ("é.pdf", "_.pdf"), ("x" * 300 + ".pdf", "x" * 100), ("   ", "upload.pdf"), ("a/", "upload.pdf"), ("...", "upload.pdf")])  # fmt: skip
def test_the_client_name_is_reduced_to_a_safe_base_name(given, expected):
    from credit_intel.api.uploads import safe_name

    assert safe_name(given) == expected


def test_a_request_the_checks_refuse_leaves_no_upload_behind(pdf, tmp_path, private_temp):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert post(client, pdf.read_bytes(), pages="abc").status_code == 422
        assert post(client, pdf.read_bytes(), profile="{bad").status_code == 422
        assert post(client, pdf.read_bytes(), basis="x").status_code == 422
    assert upload_leftovers(private_temp) == []
