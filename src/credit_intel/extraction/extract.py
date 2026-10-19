"""The extraction flow, from candidate pages to a validated response (PRD FR-003, FR-004.1-.2).

Gates first, in this order and before any LLM call: no candidate pages
(``E-EXTRACT-NO-STATEMENT-PAGES``, D-04), then the configured basis absent
(``E-EXTRACT-BASIS-UNAVAILABLE``, H.4.6). Then one call; invalid output gets one
corrective retry that includes the validation error; a second failure raises
``E-LLM-INVALID-OUTPUT``. Statuses and evidence checks are not decided here.
"""

import hashlib
import json
from dataclasses import dataclass, replace

from pydantic import ValidationError

from credit_intel.config import LLMSettings, LocatorSettings
from credit_intel.extraction.prompt import Prompt
from credit_intel.ingestion.errors import ErrorCode, IngestionError, InvalidOutputError
from credit_intel.ingestion.locator import check_statement_basis
from credit_intel.ingestion.models import IngestedDocument, LocatorResult
from credit_intel.llm.cache import CacheKeyInputs
from credit_intel.llm.gateway import LLMGateway
from credit_intel.llm.provider import STRUCTURED_OUTPUT_MODE, TEMPERATURE, LLMRequest
from credit_intel.models import ExtractionResponse

SCHEMA_VERSION = "1"
MAX_FEEDBACK_ERRORS = 20


@dataclass(frozen=True)
class ExtractionResult:
    response: ExtractionResponse
    prompt_version: str
    schema_version: str
    attempts: int  # 1, or 2 after a corrective retry


class _Invalid(Exception):
    """Output that does not parse or validate; ``feedback`` is safe to send back."""

    def __init__(self, feedback: str) -> None:
        super().__init__(feedback)
        self.feedback = feedback


def parse_response(text: str) -> ExtractionResponse:
    """Parse and validate model output, or raise ``_Invalid`` with a safe description.

    The description holds only error locations and types: no input values, so it
    never repeats document text or model output.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        line, column = getattr(exc, "lineno", 0), getattr(exc, "colno", 0)
        raise _Invalid(f"The response is not valid JSON (line {line}, column {column}).") from exc
    try:
        return ExtractionResponse.model_validate(data)
    except ValidationError as exc:
        errors = exc.errors()
        lines = [
            f"- {'.'.join(str(part) for part in e['loc']) or '(root)'}: {e['type']}"
            for e in errors[:MAX_FEEDBACK_ERRORS]
        ]
        more = len(errors) - MAX_FEEDBACK_ERRORS
        if more > 0:
            lines.append(f"- and {more} more")
        raise _Invalid("The response does not match the schema:\n" + "\n".join(lines)) from exc


def _is_valid(text: str) -> bool:
    try:
        parse_response(text)
    except _Invalid:
        return False
    return True


def render_pages(document: IngestedDocument, page_numbers: tuple[int, ...]) -> str:
    by_number = {page.page_number: page for page in document.pages}
    blocks = [
        f"=== PAGE {n} ===\n{by_number[n].text}\n=== END PAGE {n} ===" for n in page_numbers
    ]
    return "\n\n".join(blocks)


def extract_fields(
    document: IngestedDocument,
    located: LocatorResult,
    gateway: LLMGateway,
    llm: LLMSettings,
    prompt: Prompt,
    basis: str,
    locator_settings: LocatorSettings | None = None,
) -> ExtractionResult:
    if not located.candidates:
        raise IngestionError(ErrorCode.NO_STATEMENT_PAGES)
    check_statement_basis(document.pages, located, basis, locator_settings)

    pages = tuple(sorted(c.page_number for c in located.candidates))
    user = render_pages(document, pages)
    inputs = CacheKeyInputs(
        document_sha256=document.file_info.sha256,
        candidate_pages=pages,
        provider=llm.provider,
        model_id=llm.model_id,
        prompt_version=prompt.version,
        schema_version=SCHEMA_VERSION,
        temperature=TEMPERATURE,
        max_output_tokens=llm.max_output_tokens,
        structured_output_mode=STRUCTURED_OUTPUT_MODE,
    )

    def call(user_text: str, key: CacheKeyInputs) -> str:
        request = LLMRequest(
            system=prompt.system,
            user=user_text,
            model_id=llm.model_id,
            max_output_tokens=llm.max_output_tokens,
        )
        return gateway.complete(request, key, _is_valid).text

    text = call(user, inputs)
    try:
        response = parse_response(text)
    except _Invalid as first:
        retry_user = (
            f"{user}\n\nYour previous response was rejected. {first.feedback}\n"
            "Return the corrected JSON object only."
        )
        feedback_hash = hashlib.sha256(first.feedback.encode("utf-8")).hexdigest()
        text = call(retry_user, replace(inputs, corrective_feedback_sha256=feedback_hash))
        try:
            response = parse_response(text)
        except _Invalid as second:
            raise InvalidOutputError(text) from second
        attempts = 2
    else:
        attempts = 1
    return ExtractionResult(response, prompt.version, SCHEMA_VERSION, attempts)
