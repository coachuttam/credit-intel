"""The whole path over real sockets (PRD FR-016, FR-017, Definition of Phase 6; step 5).

A real uvicorn server serves the application on the loopback address, and a real HTTP client uses it: the form, the redirect, the polling, the
files, the token. A second group starts the launcher as a separate process, as a person would, and talks to it. The suite blocks network
connections, so these tests allow connections to ``127.0.0.1`` and nothing else.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)

REAL_CONNECT = socket.socket.connect  # saved at import, before the suite's fixture replaces it
ROOT = Path(__file__).resolve().parents[2]
STATES = ["received", "validated", "text_extracted", "statements_located", "fields_extracted", "validated_fields", "calculated", "rules_evaluated", "memo_generated", "exported"]


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    def connect(self, address):
        if not (isinstance(address, tuple) and address[0] in ("127.0.0.1", "localhost", "::1")):
            raise RuntimeError("network access is blocked in the default test suite (only the loopback address is allowed here)")
        return REAL_CONNECT(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, address: (_ for _ in ()).throw(RuntimeError("blocked")))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Served:
    def __init__(self, app):
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning", access_log=False))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        end = time.monotonic() + 20
        while not self.server.started and time.monotonic() < end:
            time.sleep(0.02)
        assert self.server.started, "the server did not start"
        return httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=30)

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(20)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def wait_for(client, run_id, headers=None, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        body = client.get(f"/runs/{run_id}", headers=headers).json()
        if body["state"] in ("exported", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(body)


def test_from_the_form_to_the_memo_over_a_real_socket(pdf, tmp_path, real_report):
    app, settings = base.build(tmp_path, pdf)
    with Served(app) as client:
        front = client.get("/")
        assert front.status_code == 200 and "text/html" in front.headers["content-type"]
        assert client.get("/static/app.js").status_code == 200 and client.get("/static/app.css").status_code == 200
        sent = client.post("/ui/submit", files={"file": ("statement.pdf", pdf.read_bytes(), "application/pdf")}, data={"basis": "consolidated"})
        assert sent.status_code == 303 and sent.headers["location"].startswith("/ui/runs/")
        run_id = sent.headers["location"].rsplit("/", 1)[1]
        status = wait_for(client, run_id)
        assert status["state"] == "exported" and [s["state"] for s in status["stages"]] == STATES
        assert status["files"] == ["memo.md", "results.json", "manifest.json", "report.pdf"]
        page = client.get(f"/ui/runs/{run_id}")
        assert page.status_code == 200 and 'data-final="true"' in page.text and "<h2>Memo</h2>" in page.text
        folder = settings.output_dir / run_id
        for name, filename in (("memo", "memo.md"), ("results", "results.json"), ("manifest", "manifest.json"), ("report", "report.pdf")):
            assert client.get(f"/runs/{run_id}/{name}").content == (folder / filename).read_bytes()
        assert client.get("/runs").json()["runs"][0] == {"run_id": run_id, "state": "exported"}
        assert client.get("/health").json() == {"status": "ok", "queued": 0, "running": 0}
        assert client.get(f"/runs/{run_id}").headers["content-security-policy"].startswith("default-src 'none'")


def test_the_api_path_over_a_real_socket_gives_the_command_lines_memo_and_results(pdf, tmp_path, monkeypatch):
    import io

    from credit_intel.cli import main
    from credit_intel.llm.provider import FakeProvider

    app, settings = base.build(tmp_path, pdf)
    with Served(app) as client:
        accepted = client.post("/runs", files={"file": ("statement.pdf", pdf.read_bytes())}, data={"no_report": "true"})
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        assert wait_for(client, run_id)["state"] == "exported"
        memo, results = client.get(f"/runs/{run_id}/memo").content, client.get(f"/runs/{run_id}/results").content
    (tmp_path / "cwd").mkdir()
    monkeypatch.chdir(tmp_path / "cwd")
    out = io.StringIO()
    code = main([str(pdf), "--config", str(base.config_for(tmp_path)), "--output-dir", str(tmp_path / "cli"), "--no-report"], stdout=out, stderr=io.StringIO(),
                provider_factory=lambda s, e: FakeProvider(script=[fx.good_response(pdf)]), clock=base.ticker(), assignments=tmp_path / "none.jsonl", env={})  # fmt: skip
    folder = Path(out.getvalue().strip())
    assert code == 0 and memo == (folder / "memo.md").read_bytes() and results == (folder / "results.json").read_bytes()


def test_a_run_that_fails_after_acceptance_and_a_refused_upload_over_a_real_socket(pdf, tmp_path):
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot really a pdf\n")
    app, settings = base.build(tmp_path, pdf, max_file_bytes=50_000)
    with Served(app) as client:
        refused = client.post("/runs", files={"file": ("a.pdf", b"%PDF-" + b"x" * 200_000)})
        assert refused.status_code == 413 and refused.json()["code"] == "E-INPUT-TOO-LARGE"
        not_pdf = client.post("/runs", files={"file": ("a.pdf", b"plain text")})
        assert not_pdf.status_code == 422 and not_pdf.json()["code"] == "E-INPUT-NOT-PDF"
        accepted = client.post("/runs", files={"file": ("bad.pdf", bad.read_bytes())})
        status = wait_for(client, accepted.json()["run_id"])
        assert status["state"] == "failed" and status["error"]["code"] == "E-INPUT-CORRUPT" and status["files"] == ["manifest.json"]
    assert sorted(p.name for p in settings.output_dir.iterdir()) == [accepted.json()["run_id"]]


def test_the_token_over_a_real_socket(pdf, tmp_path):
    token = "e2e-" + "k" * 40
    app, _ = base.build(tmp_path, pdf, env={"CREDIT_INTEL_API_TOKEN": token})
    auth = {"Authorization": f"Bearer {token}"}
    with Served(app) as client:
        assert client.get("/runs").status_code == 401 and client.get("/health").status_code == 200 and client.get("/").status_code == 401
        accepted = client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, data={"no_report": "true"}, headers=auth)
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        assert wait_for(client, run_id, auth)["state"] == "exported"
        assert client.get(f"/runs/{run_id}/memo").status_code == 401 and client.get(f"/runs/{run_id}/memo", headers=auth).status_code == 200


def test_a_cross_origin_post_over_a_real_socket_is_refused(pdf, tmp_path):
    app, settings = base.build(tmp_path, pdf)
    with Served(app) as client:
        answer = client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, headers={"Origin": "http://evil.example"})
        assert answer.status_code == 403
        assert client.get("/runs").json() == {"runs": []}


# --- the launcher, as a separate process ---------------------------------------------------------------------------------------------------------


def settings_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(base.LLM.format(provider="fake") + "[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 2\nrun_timeout_seconds = 60\n", encoding="utf-8")
    return path


def start(tmp_path, port, **extra):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "CREDIT_INTEL_API_OUTPUT_DIR": str(tmp_path / "out"), "CREDIT_INTEL_API_CACHE_DIR": str(tmp_path / "cache"),
           "CREDIT_INTEL_API_PORT": str(port), **extra}  # fmt: skip
    return subprocess.Popen([sys.executable, "-m", "credit_intel.api", "--config", str(settings_file(tmp_path))], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_the_launcher_serves_the_page_the_script_and_health_and_stops_on_a_signal(tmp_path):
    port = free_port()
    process = start(tmp_path, port)
    try:
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5)
        end = time.monotonic() + 30
        health = None
        while time.monotonic() < end and process.poll() is None:
            try:
                health = client.get("/health")
                break
            except httpx.TransportError:
                time.sleep(0.1)
        assert health is not None and health.json() == {"status": "ok", "queued": 0, "running": 0}, process.stderr.read() if process.poll() is not None else ""
        assert "upload" in client.get("/").text.lower() and client.get("/static/app.js").status_code == 200
        assert "server" not in client.get("/health").headers  # the server's own header is off
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(30)
        except subprocess.TimeoutExpired:
            process.kill()
    assert process.returncode in (0, -signal.SIGTERM)


def test_the_launcher_does_not_listen_without_its_folders_or_on_a_public_address_without_a_token(tmp_path):
    for extra, named in (({"CREDIT_INTEL_API_OUTPUT_DIR": ""}, "api.output_dir"), ({"CREDIT_INTEL_API_HOST": "0.0.0.0"}, "api.token"), ({"CREDIT_INTEL_API_TOKEN": "short"}, "api.token")):
        port = free_port()
        process = start(tmp_path, port, **extra)
        out, err = process.communicate(timeout=60)
        assert process.returncode == 6 and err.startswith("E-CONFIG-INVALID: ") and named in err and out == "", (extra, err)
        with socket.socket() as probe, pytest.raises(OSError):
            probe.settimeout(1)
            probe.connect(("127.0.0.1", port))  # nothing is listening
