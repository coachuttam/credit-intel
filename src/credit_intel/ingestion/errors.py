"""Ingestion error codes and the exception that carries them (PRD FR-001, FR-011, G.1).

Messages are fixed, user-safe text: they never include document content,
library error text, or stack traces. The underlying library exception, if
any, is kept on ``__cause__`` for debugging only.
"""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "E-INPUT-NOT-FOUND"
    TOO_LARGE = "E-INPUT-TOO-LARGE"
    NOT_PDF = "E-INPUT-NOT-PDF"
    CORRUPT = "E-INPUT-CORRUPT"
    ENCRYPTED = "E-INPUT-ENCRYPTED"
    TOO_MANY_PAGES = "E-INPUT-TOO-MANY-PAGES"
    NO_TEXT_LAYER = "E-INPUT-NO-TEXT-LAYER"
    OCR_UNAVAILABLE = "E-INPUT-OCR-UNAVAILABLE"
    OCR_FAILED = "E-INPUT-OCR-FAILED"
    PARSE_LIMIT = "E-INPUT-PARSE-LIMIT"
    PAGE_RANGE = "E-INPUT-PAGE-RANGE"
    BASIS_UNAVAILABLE = "E-EXTRACT-BASIS-UNAVAILABLE"
    CONFIG_INVALID = "E-CONFIG-INVALID"
    LLM_BUDGET_EXCEEDED = "E-LLM-BUDGET-EXCEEDED"
    NO_STATEMENT_PAGES = "E-EXTRACT-NO-STATEMENT-PAGES"
    LLM_INVALID_OUTPUT = "E-LLM-INVALID-OUTPUT"
    LLM_AUTH = "E-LLM-AUTH"
    LLM_UNAVAILABLE = "E-LLM-UNAVAILABLE"
    PROFILE_INVALID = "E-INPUT-PROFILE-INVALID"
    SEND_REFUSED = "E-INPUT-SEND-REFUSED"
    EXPORT_FAILED = "E-EXPORT-FAILED"
    RUN_TIMEOUT = "E-RUN-TIMEOUT"  # API only (PRD v0.4.59, FR-016 criterion 10)
    API_REQUEST = "E-API-REQUEST"  # API only (PRD v0.4.59, FR-016 criterion 5)
    RUN_INTERRUPTED = "E-RUN-INTERRUPTED"  # API only (PRD v0.4.62, FR-016 criterion 10, OD-32)


@dataclass(frozen=True)
class CatalogueEntry:
    """One row of the error catalogue (PRD G.1)."""

    code: ErrorCode
    stage: str  # the FR-011 state(s) in which it can occur
    body: str  # what went wrong, as fixed user-safe text
    action: str  # what the user should do
    exit_code: int | None  # None for the two API-only codes: the command line never raises them (PRD v0.4.59)
    retried: str  # "No", "Once, with the validation error", or "Yes, with backoff"

    @property
    def message(self) -> str:
        return f"{self.body} {self.action}"


EXIT_OK = 0
EXIT_INTERNAL = 1  # a failure not in the catalogue is a bug (FR-011.2)
EXIT_USAGE = 2  # argument errors, argparse's convention (FR-014.4)
EXIT_INPUT, EXIT_EXTRACT, EXIT_LLM, EXIT_CONFIG, EXIT_EXPORT = 3, 4, 5, 6, 7

_E = CatalogueEntry
C = ErrorCode
CATALOGUE: dict[ErrorCode, CatalogueEntry] = {
    entry.code: entry
    for entry in (
        _E(C.NOT_FOUND, "validated", "The input file does not exist, is not a regular file, or cannot be read.",
           "Check the path and file permissions.", EXIT_INPUT, "No"),
        _E(C.TOO_LARGE, "validated", "The input file exceeds the maximum allowed size.",
           "Supply a smaller file or only the financial-statements section.", EXIT_INPUT, "No"),
        _E(C.NOT_PDF, "validated", "The input file is not a PDF (missing %PDF- signature).",
           "Supply a PDF file.", EXIT_INPUT, "No"),
        _E(C.CORRUPT, "validated / text_extracted", "The PDF is corrupt or cannot be parsed.",
           "Re-download or re-export the PDF.", EXIT_INPUT, "No"),
        _E(C.ENCRYPTED, "validated", "The PDF is encrypted or password-protected; encrypted PDFs are not supported.",
           "Supply an unencrypted copy.", EXIT_INPUT, "No"),
        _E(C.TOO_MANY_PAGES, "validated", "The PDF has more pages than the maximum allowed.",
           "Supply only the relevant pages.", EXIT_INPUT, "No"),
        _E(C.NO_TEXT_LAYER, "text_extracted / statements_located",
           "The PDF has no extractable text layer: it appears to be scanned or image-only.",
           "Supply a text-based PDF or a page range that contains text, or turn OCR on with --ocr and --pages.", EXIT_INPUT, "No"),
        _E(C.OCR_UNAVAILABLE, "text_extracted", "OCR is turned on but the OCR engine is not installed or not configured.",
           "Install the engine, or run without --ocr.", EXIT_INPUT, "No"),
        _E(C.OCR_FAILED, "text_extracted", "The OCR engine failed, or the OCR page cap or time limit was exceeded.",
           "Narrow --pages, or raise the limits deliberately.", EXIT_INPUT, "No"),
        _E(C.PARSE_LIMIT, "validated / text_extracted", "Parsing the PDF exceeded the time limit or the memory limit.",
           "Supply a smaller or simpler file, or raise the limit deliberately.", EXIT_INPUT, "No"),
        _E(C.PAGE_RANGE, "statements_located",
           "The page range is invalid: it must be comma-separated 1-based page numbers or ranges within the document and no larger than the candidate-page limit.",
           "Correct --pages (e.g. 110-115,120).", EXIT_INPUT, "No"),
        _E(C.PROFILE_INVALID, "received",
           "The profile file is invalid: it must be a JSON object with only the keys borrower_name, industry, facility_requested and notes, each a string of at most 500 characters.",
           "Fix the profile file to the documented keys and limits.", EXIT_INPUT, "No"),
        _E(C.SEND_REFUSED, "received",
           "The document may not be sent to the hosted API: it is recorded as held out, or it is not on the assignment record and --confirm-public-document was not given, or the record cannot be read.",
           "If the document is public and is not recorded as held out, re-run with --confirm-public-document; a held-out document cannot be sent.", EXIT_INPUT, "No"),
        _E(C.NO_STATEMENT_PAGES, "fields_extracted", "No candidate statement pages were found and no page range was supplied.",
           "Supply the statement pages with --pages.", EXIT_EXTRACT, "No"),
        _E(C.BASIS_UNAVAILABLE, "statements_located", "No financial statement of the configured basis was found.",
           "Review the document; to analyse another basis, re-run with --basis.", EXIT_EXTRACT, "No"),
        _E(C.LLM_INVALID_OUTPUT, "fields_extracted", "The model's output was still invalid after one corrective retry.",
           "Re-run; report if it persists.", EXIT_LLM, "Once, with the validation error"),
        _E(C.LLM_UNAVAILABLE, "fields_extracted", "The LLM provider was unavailable after repeated attempts.",
           "Re-run later.", EXIT_LLM, "Yes, with backoff"),
        _E(C.LLM_AUTH, "fields_extracted", "Authentication with the LLM provider failed.",
           "Check OPENAI_API_KEY.", EXIT_LLM, "No"),
        _E(C.LLM_BUDGET_EXCEEDED, "fields_extracted", "The per-run token ceiling would be exceeded, so the LLM call was not made.",
           "Narrow --pages, or raise the ceiling deliberately.", EXIT_LLM, "No"),
        _E(C.CONFIG_INVALID, "received", "The settings or rules file is missing, unparsable, or fails validation.",
           "Fix the named setting.", EXIT_CONFIG, "No"),
        _E(C.EXPORT_FAILED, "exported", "The output could not be written, or the run directory already exists.",
           "Check the output directory and re-run.", EXIT_EXPORT, "No"),
        _E(C.RUN_TIMEOUT, "any, after received", "The run passed the time limit for one run.",
           "Narrow the pages, or raise the limit deliberately.", None, "No"),
        _E(C.RUN_INTERRUPTED, "any, after received", "The service stopped while the run was queued or running.",
           "Submit the document again.", None, "No"),
        _E(C.API_REQUEST, "before received", "The request is malformed: a file is missing, a field is unknown or a value is of the wrong form.",
           "Correct the request to the documented fields.", None, "No"),
    )
}  # fmt: skip

MESSAGES: dict[ErrorCode, str] = {code: entry.message for code, entry in CATALOGUE.items()}


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


def exit_code(error: BaseException) -> int:
    """The process exit code for a failure: the catalogue's for a catalogued error, else 1 (FR-011.2)."""
    if isinstance(error, IngestionError):
        return CATALOGUE[error.code].exit_code or EXIT_INTERNAL  # an API-only code has none: if one reached the command line it is a bug
    return EXIT_INTERNAL
