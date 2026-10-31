"""Access control, response headers, request logging and the launcher of the API (PRD SEC-14 to SEC-16, FR-016 criteria 11 and 12; Phase 6 step 3).

Synthetic and offline, like ``test_api.py``, whose helpers it reuses.
"""

import json
import logging
import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api import __main__ as launcher
from credit_intel.api.app import create_app
from credit_intel.api.lockout import FailedAttempts
from credit_intel.api.security import SECURITY_HEADERS, check_exposure, is_loopback
from credit_intel.config import ENV_API_TOKEN, load_api_token
from credit_intel.ingestion.errors import ErrorCode, IngestionError

TOKEN = "t" * 12 + "OPEN-sesame-0123456789-abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PRD_CSP = ("default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")


def build(tmp_path, pdf, token=TOKEN, **kwargs):
    """The tests of this file make many wrong attempts on purpose; unless a test is about the limit, it is out of the way (the limit has its own tests in ``test_api_lockout.py``)."""
    env = {ENV_API_TOKEN: token} if token is not None else {}
    kwargs.setdefault("failed_attempts", FailedAttempts(max_failures=10**9))
    return base.build(tmp_path, pdf, env=env, **kwargs)


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


# --- the token ---------------------------------------------------------------------------------------------------------------------------


UNAUTH = {"code": None, "message": "A valid bearer token is required."}


@pytest.mark.parametrize("headers", [
    {}, {"Authorization": "Bearer wrong-" + TOKEN}, {"Authorization": "Bearer"}, {"Authorization": "Bearer "}, {"Authorization": f"Basic {TOKEN}"},
    {"Authorization": TOKEN}, {"Authorization": f"Bearer {TOKEN} "}, {"Authorization": f"Bearer  {TOKEN}"}, {"Authorization": f"Bearer {TOKEN[:-1]}"},
    {"Authorization": f"Bearer {TOKEN}x"}, {"X-Authorization": f"Bearer {TOKEN}"}], ids=range(11))  # fmt: skip
def test_every_endpoint_but_health_refuses_a_missing_or_wrong_token_with_a_fixed_401(pdf, tmp_path, headers):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        run_id = "20261030T101530.123456Z-abcdef12"
        for method, path in (("GET", "/runs"), ("GET", f"/runs/{run_id}"), ("GET", f"/runs/{run_id}/memo"), ("GET", f"/runs/{run_id}/report"), ("GET", "/nothing-here"),
                             ("DELETE", "/runs"), ("GET", "/")):  # fmt: skip
            answer = client.request(method, path, headers=headers)
            assert answer.status_code == 401 and answer.json() == UNAUTH and answer.headers["www-authenticate"] == "Bearer", (method, path)
        posted = base.post(client, pdf.read_bytes(), no_report=True) if not headers else client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, headers=headers)
        assert posted.status_code == 401 and posted.json() == UNAUTH
        assert client.get("/health", headers=headers).status_code == 200  # health asks for nothing
    assert not settings.output_dir.exists()


def test_the_right_token_is_accepted_case_insensitively_for_the_scheme_and_a_run_goes_through(pdf, tmp_path):
    app, settings = build(tmp_path, pdf)
    with TestClient(app) as client:
        answer = client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, data={"no_report": "true"}, headers=AUTH)
        assert answer.status_code == 202
        run_id = answer.json()["run_id"]
        for scheme in ("Bearer", "bearer", "BEARER"):
            assert client.get(f"/runs/{run_id}", headers={"Authorization": f"{scheme} {TOKEN}"}).status_code == 200
        end = __import__("time").monotonic() + 30
        while client.get(f"/runs/{run_id}", headers=AUTH).json()["state"] not in ("exported", "failed") and __import__("time").monotonic() < end:
            pass
        assert client.get(f"/runs/{run_id}/memo", headers=AUTH).status_code == 200
        assert client.get(f"/runs/{run_id}/memo").status_code == 401


def test_a_token_in_the_url_or_the_body_is_not_accepted(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        assert client.get(f"/runs?token={TOKEN}").status_code == 401
        assert client.get(f"/runs?access_token={TOKEN}&Authorization=Bearer%20{TOKEN}").status_code == 401
        assert client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, data={"token": TOKEN}).status_code == 401
        client.cookies.set("Authorization", f"Bearer {TOKEN}")
        assert client.get("/runs").status_code == 401


def test_the_comparison_is_constant_time(pdf, tmp_path, monkeypatch):
    import hmac

    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append((type(a), type(b))) or real(a, b))
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        client.get("/runs", headers=AUTH)
        client.get("/runs", headers={"Authorization": "Bearer nope"})
    assert calls == [(bytes, bytes), (bytes, bytes)]


def test_without_a_token_on_a_loopback_host_nothing_asks_for_one(pdf, tmp_path):
    app, _ = build(tmp_path, pdf, token=None)
    with TestClient(app) as client:
        assert client.get("/runs").status_code == 200 and client.get("/health").status_code == 200


def test_the_token_never_appears_in_a_response_a_log_line_or_an_error(pdf, tmp_path, caplog):
    app, _ = build(tmp_path, pdf)
    caplog.set_level(logging.DEBUG)
    seen = []
    with TestClient(app) as client:
        for headers in ({}, AUTH, {"Authorization": f"Bearer {TOKEN}bad"}):
            for path in ("/runs", "/health", "/nope"):
                answer = client.get(path, headers=headers)
                seen.append(answer.text + json.dumps(dict(answer.headers)))
        seen.append(client.post("/runs", files={"file": ("a.pdf", b"nope")}, headers=AUTH).text)
    assert not [s for s in seen if TOKEN in s or TOKEN[:12] in s]
    assert TOKEN not in caplog.text and TOKEN[:12] not in caplog.text


# --- the token itself and where the service may listen ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "short", "x" * 31, "has space " + "x" * 30, "tab\t" + "x" * 30, "ünïcode" + "x" * 30, "new\nline" + "x" * 30])
def test_a_token_that_is_set_but_short_or_odd_is_config_invalid_naming_api_token_and_not_its_value(bad):
    with pytest.raises(IngestionError) as error:
        load_api_token({ENV_API_TOKEN: bad})
    assert error.value.code is ErrorCode.CONFIG_INVALID and "api.token" in str(error.value) and (bad.strip() == "" or bad not in str(error.value))


def test_a_good_token_loads_and_no_token_is_none():
    assert load_api_token({ENV_API_TOKEN: TOKEN}) == TOKEN and load_api_token({}) is None
    assert load_api_token({ENV_API_TOKEN: "x" * 32}) == "x" * 32


def test_the_token_cannot_be_set_in_the_settings_file(tmp_path):
    from credit_intel.config import load_api_settings

    path = tmp_path / "s.toml"
    path.write_text('[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 1\nrun_timeout_seconds = 5\noutput_dir = "/a"\ncache_dir = "/b"\ntoken = "' + TOKEN + '"\n', encoding="utf-8")
    with pytest.raises(IngestionError) as error:
        load_api_settings(path, {})
    assert "api.token" in str(error.value) and TOKEN not in str(error.value)


@pytest.mark.parametrize("host, loopback", [("127.0.0.1", True), ("127.0.0.2", True), ("::1", True), ("[::1]", True), ("localhost", True), ("0.0.0.0", False), ("::", False),
                                            ("192.168.1.5", False), ("10.0.0.1", False), ("example.com", False), ("localhost.example.com", False), ("127.0.0.1.example.com", False),
                                            ("", False)])  # fmt: skip
def test_only_a_loopback_host_may_serve_without_a_token(host, loopback):
    assert is_loopback(host) is loopback
    if loopback:
        check_exposure(host, None)
    else:
        with pytest.raises(IngestionError) as error:
            check_exposure(host, None)
        assert error.value.code is ErrorCode.CONFIG_INVALID and "api.token" in str(error.value)
    check_exposure(host, TOKEN)


def test_the_application_is_not_built_for_a_public_host_without_a_token_or_with_a_short_one(pdf, tmp_path):
    settings = base.settings_for(tmp_path)
    public = type(settings)(settings.max_concurrent_runs, settings.max_queued_runs, settings.run_timeout_seconds, settings.output_dir, settings.cache_dir, host="0.0.0.0")
    config = base.config_for(tmp_path)
    with pytest.raises(IngestionError) as error:
        create_app(public, config=config, env={})
    assert "api.token" in str(error.value)
    create_app(public, config=config, env={ENV_API_TOKEN: TOKEN})
    with pytest.raises(IngestionError):
        create_app(settings, config=config, env={ENV_API_TOKEN: "short"})  # a short token is refused on a loopback host too


def test_uploads_must_be_kept_outside_the_output_folder(pdf, tmp_path, monkeypatch):
    import tempfile

    inside = tmp_path / "out" / "tmp"
    inside.mkdir(parents=True)
    monkeypatch.setattr(tempfile, "tempdir", str(inside))
    with pytest.raises(IngestionError) as error:
        base.build(tmp_path, pdf)
    assert error.value.code is ErrorCode.CONFIG_INVALID and "api.output_dir" in str(error.value)


# --- another origin ------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("origin", ["http://evil.example", "https://testserver.evil.example", "null", "http://testserver:8080", "http://127.0.0.1:8000"])
def test_a_post_from_another_origin_is_403_and_starts_nothing(pdf, tmp_path, origin):
    app, settings = build(tmp_path, pdf, token=None)
    with TestClient(app) as client:
        answer = client.post("/runs", files={"file": ("a.pdf", pdf.read_bytes())}, headers={"Origin": origin})
        assert answer.status_code == 403 and answer.json() == {"code": None, "message": "The request came from another origin."}
        assert client.get("/runs").json() == {"runs": []}
    assert not settings.output_dir.exists()


def test_a_post_from_the_same_origin_or_with_no_origin_is_accepted(pdf, tmp_path):
    app, _ = build(tmp_path, pdf, token=None)
    with TestClient(app) as client:
        for headers in ({}, {"Origin": "http://testserver"}, {"Origin": "HTTP://TESTSERVER"}):
            files = {"file": ("a.pdf", pdf.read_bytes() + str(len(headers)).encode() + str(headers).encode())}
            assert client.post("/runs", files=files, data={"no_report": "true"}, headers=headers).status_code in (202, 422)


# --- headers ---------------------------------------------------------------------------------------------------------------------------------


def assert_headers(answer):
    for name, value in SECURITY_HEADERS.items():
        assert answer.headers[name] == value, name


def test_the_policy_is_the_one_in_sec_16():
    assert SECURITY_HEADERS == {"Content-Security-Policy": PRD_CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


def test_every_response_carries_the_policy_the_files_the_errors_and_the_refusals(pdf, tmp_path, real_report):
    app, settings = build(tmp_path, pdf, token=None, max_file_bytes=100_000)
    with TestClient(app) as client:
        accepted = base.post(client, pdf.read_bytes())
        assert accepted.status_code == 202
        run_id = accepted.json()["run_id"]
        base.wait(client, run_id)
        answers = [accepted, client.get("/health"), client.get("/runs"), client.get(f"/runs/{run_id}"), client.get("/runs/nope"), client.get("/elsewhere"), client.put("/runs"),
                   base.post(client, b"not a pdf"), base.post(client, b"%PDF-" + b"x" * 200_000), base.post(client, pdf.read_bytes(), basis="x"),
                   client.post("/runs", files={"file": ("a.pdf", b"%PDF-1")}, headers={"Origin": "http://evil.example"})]  # fmt: skip
        files = [client.get(f"/runs/{run_id}/{name}") for name in ("memo", "results", "manifest", "report")]
        assert [f.status_code for f in files] == [200, 200, 200, 200]
        for answer in (*answers, *files):
            assert_headers(answer)
        assert all("html" not in f.headers["content-type"] for f in files)
        assert files[0].headers["content-type"].startswith("text/markdown") and files[3].headers["content-type"] == "application/pdf"


def test_a_429_and_a_503_carry_the_policy_too(tmp_path):
    pdf = fx.balance_sheet_pdf(tmp_path / "base.pdf")
    gate = base.Gate(pdf)
    app, _ = build(tmp_path, pdf, token=None, concurrent=1, queued=0, factory=gate)
    with TestClient(app) as client:
        assert base.post(client, pdf.read_bytes(), no_report=True).status_code == 202
        assert gate.entered.acquire(timeout=30)
        busy = base.post(client, pdf.read_bytes() + b"\n%2", no_report=True)
        assert busy.status_code == 429
        assert_headers(busy)
        app.state.jobs.close()
        closing = base.post(client, pdf.read_bytes() + b"\n%3", no_report=True)
        assert closing.status_code == 503
        assert_headers(closing)
        gate.release.set()


# --- logging ------------------------------------------------------------------------------------------------------------------------------------


def test_the_request_log_has_the_method_the_service_s_own_path_and_the_status_and_nothing_the_client_sent(pdf, tmp_path, caplog):
    app, _ = build(tmp_path, pdf, token=None)
    caplog.set_level(logging.INFO, logger="credit_intel.api")
    with TestClient(app) as client:
        run_id = base.post(client, pdf.read_bytes(), name="SECRET-FILE-NAME.pdf", no_report=True, profile=json.dumps({"borrower_name": "SECRET BORROWER"})).json()["run_id"]
        base.wait(client, run_id)
        client.get("/runs/whatever-the-client-typed?token=SECRET-QUERY")
        client.get("/runs", headers={"Authorization": "Bearer SECRET-HEADER"})
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("request ")]
    assert "request method=POST path=/runs status=202" in lines and f"request method=GET path=/runs/{run_id} status=200" in lines
    assert "request method=GET path=- status=404" in lines
    for secret in ("SECRET-FILE-NAME", "SECRET BORROWER", "SECRET-QUERY", "SECRET-HEADER", "whatever-the-client-typed", "Acme"):
        assert secret not in caplog.text, secret


# --- a client that goes away -------------------------------------------------------------------------------------------------------------------


async def post_then_disconnect(app, chunks, headers):
    sent = iter(chunks)
    out = []

    async def receive():
        try:
            return {"type": "http.request", "body": next(sent), "more_body": True}
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message):
        out.append(message)

    scope = {"type": "http", "method": "POST", "path": "/runs", "raw_path": b"/runs", "query_string": b"", "http_version": "1.1", "scheme": "http",
             "server": ("testserver", 80), "client": ("1.2.3.4", 1), "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}  # fmt: skip
    await app(scope, receive, send)
    return out


def test_a_client_that_disconnects_during_an_upload_leaves_nothing_and_starts_nothing(pdf, tmp_path, private_temp):
    import asyncio

    app, settings = build(tmp_path, pdf, token=None)
    boundary = "bnd"
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n'.encode() + pdf.read_bytes()[:2000]
    asyncio.run(post_then_disconnect(app, [head, b"more bytes of the file"], {"content-type": f"multipart/form-data; boundary={boundary}", "host": "testserver"}))
    assert base.upload_leftovers(private_temp) == []
    assert app.state.jobs.counts == {"queued": 0, "running": 0} and not settings.output_dir.exists()


# --- the launcher ----------------------------------------------------------------------------------------------------------------------------------


def settings_file(tmp_path, extra=""):
    path = tmp_path / "settings.toml"
    path.write_text(base.LLM.format(provider="fake") + "[ingestion]\nparse_timeout_seconds = 700\nparse_memory_mb = 1024\n" + "[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\n" + extra, encoding="utf-8")
    return path


FOLDERS = lambda tmp_path: {"CREDIT_INTEL_API_OUTPUT_DIR": str(tmp_path / "out"), "CREDIT_INTEL_API_CACHE_DIR": str(tmp_path / "cache")}  # noqa: E731


def test_the_launcher_serves_the_application_on_the_configured_host_and_port(tmp_path):
    served = []
    code = launcher.main(["--config", str(settings_file(tmp_path, 'port = 8123\n'))], env=FOLDERS(tmp_path), serve=lambda app, host, port: served.append((host, port, type(app).__name__)))
    assert code == 0 and served == [("127.0.0.1", 8123, "FastAPI")]


@pytest.mark.parametrize("env_extra, extra, named", [
    ({}, "", None), ({"CREDIT_INTEL_API_HOST": "0.0.0.0"}, "", "api.token"), ({ENV_API_TOKEN: "short"}, "", "api.token")])  # fmt: skip
def test_the_launcher_refuses_to_start_with_the_catalogued_config_error_and_does_not_listen(tmp_path, capsys, env_extra, extra, named):
    served = []
    env = {**FOLDERS(tmp_path), **env_extra}
    if named is None:
        env = {}  # no folders set: the shipped state
    import io

    err = io.StringIO()
    code = launcher.main(["--config", str(settings_file(tmp_path, extra))], env=env, stderr=err, serve=lambda *a: served.append(a))
    assert code == 6 and served == [] and err.getvalue().startswith("E-CONFIG-INVALID: ") and (named or "api.output_dir") in err.getvalue()
    assert "short" not in err.getvalue().replace("shortest", "")


def test_the_launcher_serves_a_public_host_when_a_token_is_set_and_never_prints_it(tmp_path):
    import io

    served, err = [], io.StringIO()
    env = {**FOLDERS(tmp_path), "CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN}
    code = launcher.main(["--config", str(settings_file(tmp_path))], env=env, stderr=err, serve=lambda app, host, port: served.append((host, port)))
    assert code == 0 and served == [("0.0.0.0", 8000)] and TOKEN not in err.getvalue()


def test_the_console_script_is_declared():
    scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["credit-intel-api"] == "credit_intel.api.__main__:run" and scripts["credit-intel"] == "credit_intel.cli:run"


def test_only_get_of_exactly_health_needs_no_token(pdf, tmp_path):
    app, _ = build(tmp_path, pdf)
    with TestClient(app) as client:
        for path in ("/hello", "/healthz", "/health/", "/health/x", "/health%20", "/Health", "/h"):
            assert client.get(path).status_code == 401, path
        assert client.post("/health").status_code == 401 and client.delete("/health").status_code == 401
        assert client.get("/health").status_code == 200 and client.head("/health").status_code == 401  # only GET is exempt


def test_the_server_is_started_without_its_own_access_log_or_server_header(monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    launcher._serve("the-app", "127.0.0.1", 9999)
    assert calls == [("the-app", {"host": "127.0.0.1", "port": 9999, "access_log": False, "server_header": False})]
