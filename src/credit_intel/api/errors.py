"""Catalogued errors as HTTP answers (PRD FR-016 criterion 5, v0.4.59).

``HTTP_AT_SUBMISSION`` has a row for **every** catalogued code (a test requires it): the status the code has when it is raised in the request,
before a run exists, or ``None`` when it is only ever reported in a run's status after the run was accepted. The body is fixed: the code and
the catalogue's message, which may carry only a reason word or numeric limit (FR-011.4); never document text, a path or a trace.
"""

from credit_intel.ingestion.errors import ErrorCode, IngestionError

C = ErrorCode
HTTP_AT_SUBMISSION: dict[ErrorCode, int | None] = {
    C.TOO_LARGE: 413,
    C.NOT_PDF: 422,
    C.SEND_REFUSED: 403,
    C.PROFILE_INVALID: 422,
    C.PAGE_RANGE: 422,  # the range's syntax and any page beyond the input limit; a range outside this document is reported in the status
    C.API_REQUEST: 422,
    C.CONFIG_INVALID: 500,
    C.NOT_FOUND: 500,  # the server's own temporary copy is missing
    C.OCR_UNAVAILABLE: 503,  # `ocr` was requested and the engine is not installed
    C.CORRUPT: None,
    C.ENCRYPTED: None,
    C.TOO_MANY_PAGES: None,
    C.NO_TEXT_LAYER: None,
    C.OCR_FAILED: None,
    C.PARSE_LIMIT: None,
    C.NO_STATEMENT_PAGES: None,
    C.BASIS_UNAVAILABLE: None,
    C.LLM_BUDGET_EXCEEDED: None,
    C.LLM_INVALID_OUTPUT: None,
    C.LLM_UNAVAILABLE: None,
    C.LLM_AUTH: None,
    C.EXPORT_FAILED: None,
    C.RUN_TIMEOUT: None,
    C.RUN_INTERRUPTED: None,  # found at the next start from a marker file; reported in the status
}

BUSY = "Too many runs are waiting. Try again later."
STALLED = "The upload stopped arriving and was cancelled."
CLOSING = "The service is shutting down. Try again later."
NOT_FOUND = "There is no such run or file."
METHOD = "That method is not allowed here."
REFUSED = "The request was refused."
INTERNAL = "Internal error. Re-run, and report it if it persists."


def message_of(error: IngestionError) -> str:
    """The catalogue's fixed message (and the detail the error carries: a reason word or a numeric limit), without the code."""
    return str(error).split(": ", 1)[1]


def error_body(error: IngestionError) -> dict[str, str | None]:
    return {"code": error.code.value, "message": message_of(error)}


def transport_body(message: str) -> dict[str, str | None]:
    """The body of an answer that is about the transport and not a catalogued failure (a full queue, an unknown run): no code."""
    return {"code": None, "message": message}


def status_of(error: IngestionError) -> int:
    """The HTTP status of a catalogued failure raised in the request (500 for one that is only ever reported in a run's status)."""
    return HTTP_AT_SUBMISSION[error.code] or 500
UNAUTHORIZED = "A valid bearer token is required."
CROSS_ORIGIN = "The request came from another origin."
