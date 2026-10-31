"""Access control and response headers (PRD SEC-15, SEC-16, FR-016 criteria 11 and 12; Phase 6 step 3).

* **Exposure.** The service binds to a loopback address by default. ``check_exposure`` refuses to build the application for any other host unless a bearer
  token is set **and** the operator has stated one of two conditions (``E-CONFIG-INVALID`` naming ``api.token``, or ``api.behind_tls`` and ``api.loopback_only_publication``):
  ``api.behind_tls``, that TLS ends in front of the service or that the path is encrypted by a private network; or ``api.loopback_only_publication``, that the only path
  to the service does not leave the machine (it is published on the host's loopback address only, with no TLS to speak of). They are two statements, not one: the second is
  not a form of the first, and only the first makes the service send ``Strict-Transport-Security``. The service cannot check either.
* **Token.** When a token is set every endpoint except ``GET /health`` requires ``Authorization: Bearer <token>``. The comparison is in constant time. The token
  is read from the environment only, is never logged, never accepted in a URL, never in a body.
* **Origin (an addition for a service without a token).** A browser page on another site can submit a form to ``127.0.0.1`` without a preflight, which
  would start a run the user never asked for. A ``POST`` whose ``Origin`` header is not an allowed origin is refused: one of ``api.public_hosts`` when any are set (the
  names a browser reaches the service by, which a proxy may have rewritten in ``Host``), otherwise the host the request was sent to.
* **The client address** is the connection's own, unless the connection comes from an address in ``api.trusted_proxies``: then it is the first address in
  ``X-Forwarded-For`` (reading from the right) that is not itself a trusted proxy. Forwarded headers from anyone else are never read.
* **Headers.** Every response carries the policy of SEC-16, and, with ``api.behind_tls`` true, ``Strict-Transport-Security``.
* **Logging.** One INFO line per request: the method, the path if it has one of the service's own shapes (else ``-``) and the status; nothing the client sent.
"""

import hmac
import ipaddress
import logging
import re
from collections.abc import Sequence
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from credit_intel.api.errors import CROSS_ORIGIN, LOCKED_OUT, UNAUTHORIZED, transport_body
from credit_intel.api.lockout import FailedAttempts
from credit_intel.api.jobs import RUN_ID
from credit_intel.ingestion.errors import ErrorCode, IngestionError

logger = logging.getLogger("credit_intel.api")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
STRICT_TRANSPORT_SECURITY = "max-age=31536000"  # a year; not includeSubDomains, which would reach other sites of the same domain
_KNOWN = re.compile(rf"/(?:|runs|health|runs/{RUN_ID}(?:/(?:memo|results|manifest|report))?)")


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def check_exposure(host: str, token: str | None, behind_tls: bool = False, loopback_only_publication: bool = False) -> None:
    """Refuse a host that is not a loopback address unless a token is set and the operator has stated ``api.behind_tls`` or ``api.loopback_only_publication`` (SEC-15).

    The token is named first when it and the statement are both missing."""
    if is_loopback(host):
        return
    if token is None:
        raise IngestionError(ErrorCode.CONFIG_INVALID, "api.token")
    if not (behind_tls or loopback_only_publication):
        raise IngestionError(ErrorCode.CONFIG_INVALID, "api.behind_tls or api.loopback_only_publication")


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_networks(entries: Sequence[str]) -> tuple[Network, ...]:
    return tuple(ipaddress.ip_network(entry, strict=False) for entry in entries)


def _within(address: str, networks: Sequence[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)  # an address is never in a network of the other family


def client_address(scope: Scope, trusted: Sequence[Network] = ()) -> str:
    """The address of the client: the connection's own, or, when that connection is from a trusted proxy, the first untrusted address in ``X-Forwarded-For`` from the right.

    A forwarded list that is empty, all trusted, or has an entry that is not an address is not believed: the connection's own address is used."""
    client = scope.get("client")
    peer = str(client[0]) if client else "unknown"
    if not trusted or not client or not _within(peer, trusted):
        return peer
    entries = [part.strip() for value in Headers(scope=scope).getlist("x-forwarded-for") for part in value.split(",")]
    for entry in reversed(entries):
        try:
            ip = ipaddress.ip_address(entry)
        except ValueError:
            return peer
        if not _within(str(ip), trusted):
            return str(ip)
    return peer


def _bearer(headers: Headers) -> str | None:
    value = headers.get("authorization", "")
    scheme, _, credentials = value.partition(" ")
    return credentials if scheme.lower() == "bearer" and credentials else None


class Security:
    """A pure ASGI middleware (the upload is a stream, which a buffering middleware would spoil)."""

    def __init__(self, app: ASGIApp, token: str | None, failed_attempts: FailedAttempts | None = None, *, behind_tls: bool = False,
                 public_hosts: Sequence[str] = (), trusted_proxies: Sequence[str] = ()) -> None:  # fmt: skip
        self.app, self._token = app, token.encode() if token is not None else None
        self._attempts = failed_attempts if failed_attempts is not None else FailedAttempts()
        self._behind_tls, self._origins, self._trusted = behind_tls, tuple(h.lower() for h in public_hosts), parse_networks(trusted_proxies)

    def _authorised(self, headers: Headers) -> bool:
        given = _bearer(headers)
        return given is not None and self._token is not None and hmac.compare_digest(given.encode("utf-8"), self._token)

    def _cross_origin(self, headers: Headers) -> bool:
        origin = headers.get("origin")
        if origin is None:
            return False
        netloc = urlsplit(origin).netloc.lower()  # "null" and anything that is not a host gives an empty name
        if self._origins:
            return netloc not in self._origins  # the names a browser reaches the service by: a proxy may have rewritten `Host`
        return netloc != headers.get("host", "").lower()  # otherwise this host

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        method, path = scope["method"], scope["path"]
        status = 0

        async def respond(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    response_headers[name] = value
                if self._behind_tls:
                    response_headers["Strict-Transport-Security"] = STRICT_TRANSPORT_SECURITY
            await send(message)

        refusal: JSONResponse | None = None
        needs_token = self._token is not None and not (method == "GET" and path == "/health")
        address = client_address(scope, self._trusted)
        if needs_token and (waiting := self._attempts.locked_for(address)) is not None:
            refusal = JSONResponse(transport_body(LOCKED_OUT), status_code=429, headers={"Retry-After": str(waiting)})  # before the token is looked at
        elif needs_token and not self._authorised(headers):
            if headers.get("authorization", "").strip() and self._attempts.record_failure(address):  # a wrong credential was presented; none at all is only challenged
                logger.warning("too many failed token attempts; address %s is locked out for %d seconds", address, int(self._attempts.lockout))
            refusal = JSONResponse(transport_body(UNAUTHORIZED), status_code=401, headers={"WWW-Authenticate": "Bearer"})
        elif needs_token:
            self._attempts.record_success(address)
        if refusal is None and method == "POST" and self._cross_origin(headers):
            refusal = JSONResponse(transport_body(CROSS_ORIGIN), status_code=403)
        try:
            if refusal is not None:
                await refusal(scope, receive, respond)
            else:
                await self.app(scope, receive, respond)
        finally:
            logger.info("request method=%s path=%s status=%s", method if method in ("GET", "POST", "HEAD") else "-", path if _KNOWN.fullmatch(path) else "-", status)
