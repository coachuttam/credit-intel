"""Access control and response headers (PRD SEC-15, SEC-16, FR-016 criteria 11 and 12; Phase 6 step 3).

* **Exposure.** The service binds to a loopback address by default. ``check_exposure`` refuses to build the application for any other host unless a bearer
  token is set (``E-CONFIG-INVALID`` naming ``api.token``).
* **Token.** When a token is set every endpoint except ``GET /health`` requires ``Authorization: Bearer <token>``. The comparison is in constant time. The token
  is read from the environment only, is never logged, never accepted in a URL, never in a body.
* **Origin (an addition for a service without a token).** A browser page on another site can submit a form to ``127.0.0.1`` without a preflight, which
  would start a run the user never asked for. A ``POST`` whose ``Origin`` header names a different host than the one the request was sent to is refused.
* **Headers.** Every response carries the policy of SEC-16.
* **Logging.** One INFO line per request: the method, the path if it has one of the service's own shapes (else ``-``) and the status; nothing the client sent.
"""

import hmac
import ipaddress
import logging
import re
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from credit_intel.api.errors import CROSS_ORIGIN, UNAUTHORIZED, transport_body
from credit_intel.api.jobs import RUN_ID
from credit_intel.ingestion.errors import ErrorCode, IngestionError

logger = logging.getLogger("credit_intel.api")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
_KNOWN = re.compile(rf"/(?:|runs|health|runs/{RUN_ID}(?:/(?:memo|results|manifest|report))?)")


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def check_exposure(host: str, token: str | None) -> None:
    """Refuse a host that is not a loopback address when no token is set (SEC-15)."""
    if not is_loopback(host) and token is None:
        raise IngestionError(ErrorCode.CONFIG_INVALID, "api.token")


def _bearer(headers: Headers) -> str | None:
    value = headers.get("authorization", "")
    scheme, _, credentials = value.partition(" ")
    return credentials if scheme.lower() == "bearer" and credentials else None


class Security:
    """A pure ASGI middleware (the upload is a stream, which a buffering middleware would spoil)."""

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app, self._token = app, token.encode() if token is not None else None

    def _authorised(self, headers: Headers) -> bool:
        given = _bearer(headers)
        return given is not None and self._token is not None and hmac.compare_digest(given.encode("utf-8"), self._token)

    @staticmethod
    def _cross_origin(headers: Headers) -> bool:
        origin = headers.get("origin")
        if origin is None:
            return False
        return urlsplit(origin).netloc.lower() != headers.get("host", "").lower()  # "null" and anything else that is not this host

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
            await send(message)

        refusal: JSONResponse | None = None
        if self._token is not None and not (method == "GET" and path == "/health") and not self._authorised(headers):
            refusal = JSONResponse(transport_body(UNAUTHORIZED), status_code=401, headers={"WWW-Authenticate": "Bearer"})
        elif method == "POST" and self._cross_origin(headers):
            refusal = JSONResponse(transport_body(CROSS_ORIGIN), status_code=403)
        try:
            if refusal is not None:
                await refusal(scope, receive, respond)
            else:
                await self.app(scope, receive, respond)
        finally:
            logger.info("request method=%s path=%s status=%s", method if method in ("GET", "POST", "HEAD") else "-", path if _KNOWN.fullmatch(path) else "-", status)
