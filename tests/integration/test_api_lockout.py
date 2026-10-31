"""The limit on failed token attempts and the rotation of the token, through the service (PRD SEC-15, OD-34 (a); Phase 7 step 4)."""

import asyncio
import json
import re
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api.lockout import LOCKOUT_SECONDS, MAX_FAILURES, WINDOW_SECONDS, FailedAttempts
from credit_intel.api.security import SECURITY_HEADERS
from credit_intel.config import ENV_API_TOKEN, MIN_TOKEN_LENGTH, load_api_token

TOKEN = "z" * 8 + "ROTATE-me-0123456789-abcdefghij"
NEW = "n" * 8 + "ROTATED-0123456789-ABCDEFGHIJ-xyz"
GOOD = {"Authorization": f"Bearer {TOKEN}"}
ROOT = Path(__file__).resolve().parents[2]
LOCKED = {"code": None, "message": "Too many failed attempts. Try again later."}


class Clock:
    def __init__(self):
        self.now = 5000.0

    def __call__(self):
        return self.now


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def service(tmp_path, pdf, clock=None, token=TOKEN, **limits):
    clock = clock or Clock()
    attempts = FailedAttempts(clock=clock, **limits)
    app, settings = base.build(tmp_path, pdf, env={ENV_API_TOKEN: token}, failed_attempts=attempts)
    return app, settings, clock


def wrong(client, n=1, header="Bearer not-the-token"):
    return [client.get("/runs", headers={"Authorization": header}).status_code for _ in range(n)]


# --- the limit -----------------------------------------------------------------------------------------------------------------------------------


def test_four_wrong_tokens_are_401_the_fifth_is_401_and_locks_and_then_everything_that_needs_the_token_is_429(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        assert wrong(client, MAX_FAILURES) == [401] * MAX_FAILURES
        locked = client.get("/runs", headers={"Authorization": "Bearer another-wrong"})
        assert locked.status_code == 429 and locked.json() == LOCKED and locked.headers["retry-after"] == str(int(LOCKOUT_SECONDS))
        for name, path in (("GET", "/runs"), ("GET", "/runs/20261030T101530.123456Z-abcdef12"), ("GET", "/nothing"), ("DELETE", "/runs"), ("GET", "/")):
            assert client.request(name, path).status_code == 429, path  # even without any credential at all: the address is locked


def test_the_right_token_is_refused_too_while_the_address_is_locked_and_works_when_the_lock_is_over(pdf, tmp_path):
    app, _, clock = service(tmp_path, pdf)
    with TestClient(app) as client:
        wrong(client, MAX_FAILURES)
        assert client.get("/runs", headers=GOOD).status_code == 429  # the token is not looked at, so a guess that happened to be right cannot get in
        clock.now += LOCKOUT_SECONDS - 1
        assert client.get("/runs", headers=GOOD).status_code == 429
        clock.now += 1
        assert client.get("/runs", headers=GOOD).status_code == 200


def test_a_lock_out_does_not_touch_health_which_needs_no_token(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        wrong(client, MAX_FAILURES)
        assert client.get("/health").status_code == 200 and client.get("/health", headers={"Authorization": "Bearer junk"}).status_code == 200
        assert client.get("/runs", headers=GOOD).status_code == 429


def test_a_request_with_no_credential_at_all_is_challenged_and_never_counted(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        assert [client.get("/runs").status_code for _ in range(50)] == [401] * 50
        assert client.get("/runs", headers=GOOD).status_code == 200


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic abc", "Token abc", "abc", "Bearer wrong", f"Bearer {TOKEN}x", f"bearer {TOKEN[:-1]}"])
def test_any_credential_that_was_presented_and_is_not_the_token_counts(pdf, tmp_path, header):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        assert wrong(client, MAX_FAILURES, header) == [401] * MAX_FAILURES
        assert client.get("/runs").status_code == 429


def test_a_right_token_before_the_limit_is_reached_clears_the_count(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        wrong(client, MAX_FAILURES - 1)
        assert client.get("/runs", headers=GOOD).status_code == 200
        assert wrong(client, MAX_FAILURES - 1) == [401] * (MAX_FAILURES - 1)
        assert client.get("/runs", headers=GOOD).status_code == 200


def test_failures_spread_over_more_than_the_window_never_lock(pdf, tmp_path):
    app, _, clock = service(tmp_path, pdf)
    with TestClient(app) as client:
        for _ in range(3 * MAX_FAILURES):
            assert wrong(client) == [401]
            clock.now += WINDOW_SECONDS / (MAX_FAILURES - 1) + 1
        assert client.get("/runs", headers=GOOD).status_code == 200


def test_the_429_carries_the_policy_headers_and_a_wrong_origin_is_not_counted(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    with TestClient(app) as client:
        for _ in range(MAX_FAILURES * 2):
            assert client.post("/runs", files={"file": ("a.pdf", b"%PDF-")}, headers={**GOOD, "Origin": "http://evil.example"}).status_code == 403  # right token, wrong origin
        assert client.get("/runs", headers=GOOD).status_code == 200
        wrong(client, MAX_FAILURES)
        answer = client.get("/runs", headers=GOOD)
    assert answer.status_code == 429 and all(answer.headers[name] == value for name, value in SECURITY_HEADERS.items())


def test_a_locked_upload_is_refused_without_reading_a_byte_of_the_body(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    reads = []

    async def refused_upload():
        sent = []

        async def receive():
            reads.append(1)
            return {"type": "http.request", "body": b"x", "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/runs", "raw_path": b"/runs", "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("testserver", 80),
                 "client": ("203.0.113.9", 4000), "headers": [(b"host", b"testserver"), (b"content-type", b"multipart/form-data; boundary=b"), (b"authorization", b"Bearer wrong")]}  # fmt: skip
        for _ in range(MAX_FAILURES):
            await app(scope, receive, send)
        sent.clear()
        reads.clear()
        await app(scope, receive, send)
        return sent[0]["status"]

    assert asyncio.run(refused_upload()) == 429 and reads == []


def test_addresses_are_told_apart_by_the_connection_they_came_from(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    results = {}

    async def call(address, token):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "GET", "path": "/runs", "raw_path": b"/runs", "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("testserver", 80),
                 "client": (address, 4000) if address else None, "headers": [(b"host", b"testserver"), (b"authorization", f"Bearer {token}".encode())]}  # fmt: skip
        await app(scope, receive, send)
        return sent[0]["status"]

    async def run():
        for _ in range(MAX_FAILURES):
            await call("198.51.100.1", "wrong")
        results["a-locked"] = await call("198.51.100.1", TOKEN)
        results["b-fine"] = await call("198.51.100.2", TOKEN)
        results["ipv6-fine"] = await call("2001:db8::1", TOKEN)
        for _ in range(MAX_FAILURES):
            await call(None, "wrong")  # no client information: all such connections share one name, "unknown"
        results["unknown-locked"] = await call(None, TOKEN)
        results["b-still-fine"] = await call("198.51.100.2", TOKEN)

    asyncio.run(run())
    assert results == {"a-locked": 429, "b-fine": 200, "ipv6-fine": 200, "unknown-locked": 429, "b-still-fine": 200}


def test_the_lock_is_logged_with_the_address_and_never_with_what_was_guessed(pdf, tmp_path, caplog):
    app, _, _ = service(tmp_path, pdf)
    caplog.set_level("INFO", logger="credit_intel.api")
    with TestClient(app) as client:
        for n in range(MAX_FAILURES):
            client.get("/runs", headers={"Authorization": f"Bearer SECRET-GUESS-{n}"})
        client.get("/runs", headers=GOOD)
    text = caplog.text
    assert "too many failed token attempts; address testclient is locked out for 900 seconds" in text
    assert "SECRET-GUESS" not in text and TOKEN not in text and text.count("too many failed token attempts") == 1
    assert "request method=GET path=/runs status=429" in text


def test_nothing_is_limited_when_no_token_is_set_because_nothing_is_asked_for(pdf, tmp_path):
    app, _ = base.build(tmp_path, pdf, env={}, failed_attempts=FailedAttempts(clock=Clock()))
    with TestClient(app) as client:
        assert [client.get("/runs", headers={"Authorization": "Bearer whatever"}).status_code for _ in range(20)] == [200] * 20


def test_each_service_has_its_own_count_and_a_default_limiter_is_made_when_none_is_given(pdf, tmp_path):
    (tmp_path / "other").mkdir()
    (tmp_path / "third").mkdir()
    first, _, _ = service(tmp_path, pdf)
    second, _, _ = service(tmp_path / "other", pdf)
    with TestClient(first) as one, TestClient(second) as two:
        wrong(one, MAX_FAILURES)
        assert one.get("/runs", headers=GOOD).status_code == 429 and two.get("/runs", headers=GOOD).status_code == 200
    plain, _ = base.build(tmp_path / "third", pdf, env={ENV_API_TOKEN: TOKEN})
    with TestClient(plain) as client:
        wrong(client, MAX_FAILURES)
        assert client.get("/runs", headers=GOOD).status_code == 429  # the real limiter, with the real values


# --- rotation ----------------------------------------------------------------------------------------------------------------------------------


def test_the_command_in_the_runbook_makes_a_token_the_service_accepts_every_time():
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    assert "python3 -c 'import secrets; print(secrets.token_urlsafe(48))'" in runbook
    assert "python3 -c 'import secrets; print(secrets.token_urlsafe(48))'" in (ROOT / "deploy" / "credit-intel.env.example").read_text(encoding="utf-8")
    for _ in range(300):
        token = secrets.token_urlsafe(48)
        assert len(token) == 64 and load_api_token({ENV_API_TOKEN: token}) == token
    assert MIN_TOKEN_LENGTH == 32


def test_a_service_started_with_the_new_token_refuses_the_old_one_and_accepts_the_new(pdf, tmp_path):
    (tmp_path / "second").mkdir()
    old, _, _ = service(tmp_path, pdf, token=TOKEN)
    new, _, _ = service(tmp_path / "second", pdf, token=NEW)
    with TestClient(old) as client:
        assert client.get("/runs", headers=GOOD).status_code == 200
    with TestClient(new) as client:
        assert client.get("/runs", headers=GOOD).status_code == 401
        assert client.get("/runs", headers={"Authorization": f"Bearer {NEW}"}).status_code == 200


def test_the_runbook_has_the_rotation_procedure_with_its_traps_and_the_limits_it_states_are_the_codes():
    runbook = (ROOT / "docs" / "RUNBOOK_container.md").read_text(encoding="utf-8")
    section = re.search(r"## 5a\. Rotating the token \(SEC-15\)\n(.*?)\n## 6\.", runbook, re.S).group(1)
    for needed in ("every client stops working at the same moment", "no overlap period", "Make a new token", "Replace the value", "CREDIT_INTEL_ENV_FILE", "docker compose up -d --force-recreate",
                   "**Not `docker compose restart`:**", "Give the new token to every client", "401", "200", "OPENAI_API_KEY", "too many failed token attempts", "E-RUN-INTERRUPTED",
                   "`GET /health` still answers", "restarting the service clears it"):  # fmt: skip
        assert needed in section, needed
    steps = re.findall(r"^\d\. \*\*", section, re.M)
    assert len(steps) == 7
    assert f"After {MAX_FAILURES} requests" in section and f"within {int(WINDOW_SECONDS // 60)} minutes" in section and f"locked out for {int(LOCKOUT_SECONDS // 60)} minutes" in section


def test_compose_recreates_from_the_env_file_so_the_runbook_command_does_what_it_says():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert re.search(r"env_file:\s*\n\s*-\s*\$\{CREDIT_INTEL_ENV_FILE:\?", compose)  # read when the container is created, hence --force-recreate and not restart


def test_a_wrong_token_from_another_origin_is_a_401_and_a_locked_address_from_another_origin_is_a_429_the_token_comes_first(pdf, tmp_path):
    app, _, _ = service(tmp_path, pdf)
    foreign = {"Origin": "http://evil.example"}
    with TestClient(app) as client:
        refused = client.post("/runs", files={"file": ("a.pdf", b"%PDF-")}, headers={"Authorization": "Bearer wrong", **foreign})
        assert refused.status_code == 401
        wrong(client, MAX_FAILURES - 1)  # the foreign one counted as the first
        again = client.post("/runs", files={"file": ("a.pdf", b"%PDF-")}, headers={**GOOD, **foreign})
        assert again.status_code == 429


def test_a_connection_with_no_client_information_is_named_unknown_in_the_log(pdf, tmp_path, caplog):
    app, _, _ = service(tmp_path, pdf)
    caplog.set_level("WARNING", logger="credit_intel.api")

    async def anonymous():
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            pass

        scope = {"type": "http", "method": "GET", "path": "/runs", "raw_path": b"/runs", "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("testserver", 80),
                 "client": None, "headers": [(b"host", b"testserver"), (b"authorization", b"Bearer wrong")]}  # fmt: skip
        for _ in range(MAX_FAILURES):
            await app(scope, receive, send)

    asyncio.run(anonymous())
    assert "address unknown is locked out" in caplog.text
