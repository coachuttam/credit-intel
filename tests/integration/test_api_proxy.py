"""The service behind a TLS proxy: the start-up rule, the origin, the client address and Strict-Transport-Security (PRD SEC-15, SEC-16, OD-35, OD-36; Phase 7 step 5)."""

import asyncio
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pipeline_fixture as fx
import test_api as base
from test_api import private_temp  # noqa: F401  (the autouse fixture that points uploads at a folder of the test)
from credit_intel.api import __main__ as launcher
from credit_intel.api.app import create_app
from credit_intel.api.lockout import MAX_FAILURES, FailedAttempts
from credit_intel.api.security import SECURITY_HEADERS, STRICT_TRANSPORT_SECURITY
from credit_intel.config import ENV_API_TOKEN
from credit_intel.ingestion.errors import ErrorCode, IngestionError

TOKEN = "p" * 8 + "PROXIED-0123456789-abcdefghijklmn"
GOOD = {"Authorization": f"Bearer {TOKEN}"}
PROXY = "172.30.60.10"
SUBNET = "172.30.60.0/24"
HSTS = "strict-transport-security"


@pytest.fixture
def pdf(tmp_path):
    return fx.balance_sheet_pdf(tmp_path / "statement.pdf")


def service(tmp_path, pdf, *, token=TOKEN, clock=None, attempts=None, **settings_changes):
    config = base.config_for(tmp_path)
    settings = replace(base.settings_for(tmp_path), **settings_changes)
    return create_app(settings, config=config, services=base.services_for(pdf, tmp_path), env={ENV_API_TOKEN: token} if token else {}, clock=clock or base.ticker(),
                      failed_attempts=attempts or FailedAttempts(clock=lambda: 1000.0))  # fmt: skip


async def asgi(app, method, path, *, peer="198.51.100.1", headers=None, body=b""):
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"", "http_version": "1.1", "scheme": "http", "server": ("service", 8000),
             "client": (peer, 5000) if peer else None, "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}  # fmt: skip
    await app(scope, receive, send)
    start = sent[0]
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


def call(app, *args, **kwargs):
    return asyncio.run(asgi(app, *args, **kwargs))


# --- Strict-Transport-Security --------------------------------------------------------------------------------------------------------------------


def test_the_value_is_a_year_and_does_not_reach_other_sites_of_the_domain():
    assert STRICT_TRANSPORT_SECURITY == "max-age=31536000" and "includeSubDomains" not in STRICT_TRANSPORT_SECURITY


def test_with_behind_tls_every_response_carries_it_and_without_none_does(pdf, tmp_path):
    tls = service(tmp_path, pdf, behind_tls=True)
    (tmp_path / "plain").mkdir()
    plain = service(tmp_path / "plain", pdf)
    with TestClient(tls) as client:
        answers = [client.get("/health"), client.get("/runs", headers=GOOD), client.get("/runs"), client.get("/nothing", headers=GOOD), client.put("/runs", headers=GOOD),
                   client.post("/runs", files={"file": ("a.pdf", b"nope")}, headers=GOOD), client.get("/", headers=GOOD), client.get("/static/app.js", headers=GOOD)]  # fmt: skip
        assert {a.status_code for a in answers} >= {200, 401, 404, 405, 422}
        for answer in answers:
            assert answer.headers[HSTS] == "max-age=31536000", answer.status_code
            assert all(answer.headers[name] == value for name, value in SECURITY_HEADERS.items())
    with TestClient(plain) as client:
        assert all(HSTS not in a.headers for a in (client.get("/health"), client.get("/runs", headers=GOOD), client.get("/runs")))


def test_a_locked_out_answer_and_a_refused_origin_carry_it_too(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True)
    for _ in range(MAX_FAILURES):
        call(app, "GET", "/runs", headers={"Authorization": "Bearer wrong", "host": "service"})
    status, headers = call(app, "GET", "/runs", headers={**GOOD, "host": "service"})
    assert status == 429 and headers[HSTS] == STRICT_TRANSPORT_SECURITY
    (tmp_path / "second").mkdir()
    second = service(tmp_path / "second", pdf, behind_tls=True)
    status, headers = call(second, "POST", "/runs", headers={**GOOD, "host": "service", "origin": "http://evil.example"})
    assert status == 403 and headers[HSTS] == STRICT_TRANSPORT_SECURITY


# --- the start-up rule --------------------------------------------------------------------------------------------------------------------------


def settings_file(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(base.LLM.format(provider="fake") + "[ingestion]\nparse_timeout_seconds = 700\nparse_memory_mb = 1024\n[api]\nmax_concurrent_runs = 1\nmax_queued_runs = 4\nrun_timeout_seconds = 1200\n", encoding="utf-8")
    return path


def start(tmp_path, **env):
    out, err, served = io.StringIO(), io.StringIO(), []
    full = {"CREDIT_INTEL_API_OUTPUT_DIR": str(tmp_path / "out"), "CREDIT_INTEL_API_CACHE_DIR": str(tmp_path / "cache"), **env}
    code = launcher.main(["--config", str(settings_file(tmp_path))], env=full, stderr=err, stdout=out, serve=lambda *a: served.append(a), container_limit=lambda: None)
    return code, err.getvalue(), served


@pytest.mark.parametrize("env, named", [
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0"}, "api.token"),
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0", "CREDIT_INTEL_API_BEHIND_TLS": "true"}, "api.token"),  # TLS stated, no token: the token is named first
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0", "CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": "true"}, "api.token"),  # the other statement made, no token: the token is named first
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN}, "api.loopback_only_publication"),  # neither statement: both are named
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN}, "api.behind_tls"),
    ({"CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN, "CREDIT_INTEL_API_BEHIND_TLS": "false", "CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": "false"}, "api.behind_tls"),
    ({"CREDIT_INTEL_API_HOST": "192.168.1.5", ENV_API_TOKEN: TOKEN}, "api.behind_tls"),
    ({"CREDIT_INTEL_API_HOST": "example.com", ENV_API_TOKEN: TOKEN}, "api.loopback_only_publication"),
    ({"CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": "maybe"}, "api.loopback_only_publication"),
    ({"CREDIT_INTEL_API_BEHIND_TLS": "maybe"}, "api.behind_tls"),
    ({"CREDIT_INTEL_API_TRUSTED_PROXIES": "0.0.0.0/0"}, "api.trusted_proxies"),
    ({"CREDIT_INTEL_API_PUBLIC_HOSTS": "bad host"}, "api.public_hosts")])  # fmt: skip
def test_the_launcher_does_not_listen_on_a_public_address_without_the_token_and_the_statement_and_not_with_bad_proxy_settings(tmp_path, env, named):
    code, err, served = start(tmp_path, **env)
    assert code == 6 and served == [] and err.startswith("E-CONFIG-INVALID: ") and named in err and TOKEN not in err


def test_with_the_token_and_the_statement_a_public_address_is_served_and_the_settings_reach_the_application(tmp_path):
    env = {"CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN, "CREDIT_INTEL_API_BEHIND_TLS": "true", "CREDIT_INTEL_API_PUBLIC_HOSTS": "memos.example.com",
           "CREDIT_INTEL_API_TRUSTED_PROXIES": SUBNET}  # fmt: skip
    code, err, served = start(tmp_path, **env)
    assert code == 0 and err == "" and served[0][1:] == ("0.0.0.0", 8000)
    app = served[0][0]
    status, headers = asyncio.run(asgi(app, "GET", "/health", headers={"host": "memos.example.com"}))
    assert status == 200 and headers[HSTS] == STRICT_TRANSPORT_SECURITY


def test_the_other_statement_alone_lets_a_public_address_start_and_it_is_not_tls_so_no_hsts_is_sent(tmp_path):
    env = {"CREDIT_INTEL_API_HOST": "0.0.0.0", ENV_API_TOKEN: TOKEN, "CREDIT_INTEL_API_LOOPBACK_ONLY_PUBLICATION": "true"}
    code, err, served = start(tmp_path, **env)
    assert code == 0 and err == "" and served[0][1] == "0.0.0.0"
    status, headers = asyncio.run(asgi(served[0][0], "GET", "/health", headers={"host": "x"}))
    assert status == 200 and HSTS not in headers  # only a statement about TLS makes the service say "HTTPS only"
    (tmp_path / "b").mkdir()
    code, _, both = start(tmp_path / "b", **{**env, "CREDIT_INTEL_API_BEHIND_TLS": "true"})  # both statements: allowed, and the TLS one is what turns HSTS on
    assert code == 0
    assert asyncio.run(asgi(both[0][0], "GET", "/health", headers={"host": "x"}))[1][HSTS] == STRICT_TRANSPORT_SECURITY


def test_the_statement_is_not_needed_on_the_loopback_address_and_is_allowed_there(tmp_path):
    assert start(tmp_path)[0] == 0
    assert start(tmp_path, **{"CREDIT_INTEL_API_BEHIND_TLS": "true", ENV_API_TOKEN: TOKEN})[0] == 0


def test_a_public_address_is_still_refused_by_the_application_itself_without_the_statement(pdf, tmp_path):
    with pytest.raises(IngestionError) as error:
        service(tmp_path, pdf, host="0.0.0.0")
    assert error.value.code is ErrorCode.CONFIG_INVALID and "api.behind_tls" in str(error.value)
    service(tmp_path, pdf, host="0.0.0.0", behind_tls=True)
    (tmp_path / "second").mkdir()
    service(tmp_path / "second", pdf, host="0.0.0.0", loopback_only_publication=True)


# --- the origin -----------------------------------------------------------------------------------------------------------------------------------


def post(app, origin, host="credit-intel:8000", **kwargs):
    headers = {**GOOD, "host": host, "content-type": "multipart/form-data; boundary=b"}
    if origin is not None:
        headers["origin"] = origin
    return call(app, "POST", "/runs", headers=headers, **kwargs)[0]


def test_behind_a_proxy_that_rewrites_the_host_a_post_from_the_public_name_is_accepted_when_it_is_named(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, public_hosts=("memos.example.com",))
    assert post(app, "https://memos.example.com") == 422  # past the origin check: the (empty) body is what is refused
    assert post(app, "https://MEMOS.example.com") == 422
    assert post(app, "https://memos.example.com", host="memos.example.com") == 422
    assert post(app, None) == 422  # no Origin: not a browser's cross-site post


def test_with_public_hosts_set_any_other_origin_is_refused_even_if_it_is_the_host_the_request_was_sent_to(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, public_hosts=("memos.example.com",))
    for origin in ("http://credit-intel:8000", "https://evil.example", "https://memos.example.com:8443", "https://memos.example.com.evil.example", "null", "", "memos.example.com"):
        assert post(app, origin) == 403, origin


def test_the_names_are_compared_without_regard_to_case_even_when_the_settings_were_made_by_hand(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, public_hosts=("Memos.EXAMPLE.com",))  # not through the loader, which would have lower-cased it
    assert post(app, "https://memos.example.com") == 422 and post(app, "https://MEMOS.example.COM") == 422


def test_a_port_that_is_not_the_default_is_part_of_the_name(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, public_hosts=("memos.example.com:8443", "other.example"))
    assert post(app, "https://memos.example.com:8443") == 422 and post(app, "https://other.example") == 422
    assert post(app, "https://memos.example.com") == 403 and post(app, "https://other.example:9") == 403


def test_without_public_hosts_the_origin_must_be_the_host_the_request_was_sent_to_as_before(pdf, tmp_path):
    app = service(tmp_path, pdf)
    assert post(app, "http://credit-intel:8000") == 422 and post(app, "https://memos.example.com") == 403  # a rewritten Host with no `public_hosts` is the failure the runbook warns of


def test_the_form_post_of_the_page_follows_the_same_rule(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, public_hosts=("memos.example.com",))
    ok = call(app, "POST", "/ui/submit", headers={**GOOD, "host": "credit-intel:8000", "origin": "https://memos.example.com", "content-type": "multipart/form-data; boundary=b"})[0]
    refused = call(app, "POST", "/ui/submit", headers={**GOOD, "host": "credit-intel:8000", "origin": "https://evil.example", "content-type": "multipart/form-data; boundary=b"})[0]
    assert ok != 403 and refused == 403


# --- the client address and the limit ----------------------------------------------------------------------------------------------------------------


def wrong(app, peer, forwarded=None, n=1):
    headers = {"Authorization": "Bearer wrong", "host": "service"}
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return [call(app, "GET", "/runs", peer=peer, headers=headers)[0] for _ in range(n)]


def right(app, peer, forwarded=None):
    headers = {**GOOD, "host": "service"}
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    return call(app, "GET", "/runs", peer=peer, headers=headers)[0]


def test_behind_the_trusted_proxy_each_client_has_its_own_count(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, trusted_proxies=(SUBNET,))
    assert wrong(app, PROXY, "203.0.113.9", MAX_FAILURES) == [401] * MAX_FAILURES
    assert right(app, PROXY, "203.0.113.9") == 429  # that client is locked out
    assert right(app, PROXY, "203.0.113.10") == 200  # another client behind the same proxy is not
    assert right(app, PROXY, "2001:db8:1::5") == 200


def test_a_client_cannot_dodge_the_limit_by_naming_a_different_address_each_time(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, trusted_proxies=(SUBNET,))
    for n in range(MAX_FAILURES):
        wrong(app, PROXY, f"6.6.6.{n}, 203.0.113.9")  # the proxy appended the real address on the right
    assert right(app, PROXY, "7.7.7.7, 203.0.113.9") == 429


def test_a_connection_that_is_not_from_the_proxy_cannot_name_itself_at_all(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True, trusted_proxies=(SUBNET,))
    for n in range(MAX_FAILURES):
        wrong(app, "198.51.100.1", f"9.9.9.{n}")  # the header is not read: all of these are 198.51.100.1
    assert right(app, "198.51.100.1", "9.9.9.200") == 429 and right(app, "198.51.100.2") == 200


def test_without_trusted_proxies_everyone_behind_a_proxy_shares_the_proxys_count_as_disclosed(pdf, tmp_path):
    app = service(tmp_path, pdf, behind_tls=True)
    wrong(app, PROXY, "203.0.113.9", MAX_FAILURES)
    assert right(app, PROXY, "203.0.113.10") == 429


def test_the_lock_is_logged_with_the_real_client_address(pdf, tmp_path, caplog):
    app = service(tmp_path, pdf, behind_tls=True, trusted_proxies=(SUBNET,))
    caplog.set_level("WARNING", logger="credit_intel.api")
    wrong(app, PROXY, "203.0.113.9", MAX_FAILURES)
    assert "address 203.0.113.9 is locked out" in caplog.text and PROXY not in caplog.text
