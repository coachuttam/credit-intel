"""Ingestion error codes and the exception that carries them (PRD FR-001, FR-011, G.1).

Messages are fixed, user-safe text: they never include document content,
library error text, or stack traces. The underlying library exception, if
any, is kept on ``__cause__`` for debugging only.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "E-INPUT-NOT-FOUND"
    TOO_LARGE = "E-INPUT-TOO-LARGE"
    NOT_PDF = "E-INPUT-NOT-PDF"
    CORRUPT = "E-INPUT-CORRUPT"
    ENCRYPTED = "E-INPUT-ENCRYPTED"
    TOO_MANY_PAGES = "E-INPUT-TOO-MANY-PAGES"
    NO_TEXT_LAYER = "E-INPUT-NO-TEXT-LAYER"
    PAGE_RANGE = "E-INPUT-PAGE-RANGE"
    BASIS_UNAVAILABLE = "E-EXTRACT-BASIS-UNAVAILABLE"
    CONFIG_INVALID = "E-CONFIG-INVALID"
    LLM_BUDGET_EXCEEDED = "E-LLM-BUDGET-EXCEEDED"
    NO_STATEMENT_PAGES = "E-EXTRACT-NO-STATEMENT-PAGES"
    LLM_INVALID_OUTPUT = "E-LLM-INVALID-OUTPUT"
    LLM_AUTH = "E-LLM-AUTH"


MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.NOT_FOUND: "The input file does not exist, is not a regular file, or cannot be read.",
    ErrorCode.TOO_LARGE: "The input file exceeds the maximum allowed size.",
    ErrorCode.NOT_PDF: "The input file is not a PDF (missing %PDF- signature).",
    ErrorCode.CORRUPT: "The PDF is corrupt or cannot be parsed.",
    ErrorCode.ENCRYPTED: "The PDF is encrypted or password-protected; encrypted PDFs are not supported.",
    ErrorCode.TOO_MANY_PAGES: "The PDF has more pages than the maximum allowed.",
    ErrorCode.NO_TEXT_LAYER: (
        "The PDF has no extractable text layer. Scanned or image-only PDFs are not supported "
        "(OCR is not supported)."
    ),
    ErrorCode.PAGE_RANGE: (
        "The page range is invalid. Use comma-separated 1-based page numbers or ranges within "
        "the document and no larger than the candidate-page limit, e.g. 110-115,120."
    ),
    ErrorCode.BASIS_UNAVAILABLE: (
        "No financial statement of the configured basis was found. Review the document; "
        "to analyse another basis, re-run with --basis."
    ),
    ErrorCode.CONFIG_INVALID: (
        "The settings file is missing, unparsable, or fails validation. Fix the named setting."
    ),
    ErrorCode.LLM_BUDGET_EXCEEDED: (
        "The per-run token ceiling would be exceeded, so the LLM call was not made. "
        "Narrow --pages, or raise the ceiling deliberately."
    ),
    ErrorCode.NO_STATEMENT_PAGES: (
        "No candidate statement pages were found and no page range was supplied. "
        "Supply the statement pages with --pages."
    ),
    ErrorCode.LLM_AUTH: (
        "Authentication with the LLM provider failed. Check OPENAI_API_KEY."
    ),
    ErrorCode.LLM_INVALID_OUTPUT: (
        "The model's output was still invalid after one corrective retry. "
        "Re-run; report if it persists."
    ),
}


class IngestionError(Exception):
    """Raised when an input document fails validation or extraction."""

    def __init__(self, code: ErrorCode, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = MESSAGES[code]
        if detail:
            message = f"{message} ({detail})"
        super().__init__(f"{code}: {message}")


class InvalidOutputError(IngestionError):
    """The model's output failed validation twice (FR-004.1).

    ``raw_response`` is the last raw response, kept for diagnosis. It is not part of
    the message, which never includes document or model text.
    """

    def __init__(self, raw_response: str) -> None:
        super().__init__(ErrorCode.LLM_INVALID_OUTPUT)
        self.raw_response = raw_response
