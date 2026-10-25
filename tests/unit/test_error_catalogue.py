"""The error catalogue, its exit codes and its fixed messages (PRD G.1, FR-011.2, FR-011.4, FR-014; Phase 5 step 5a; B-254).

The expected table is written out here from PRD G.1 on its own, so the code is checked against the specification and not against itself.
"""

import re

import pytest

from credit_intel.ingestion.errors import (
    CATALOGUE,
    EXIT_EXPORT,
    EXIT_EXTRACT,
    EXIT_INPUT,
    EXIT_INTERNAL,
    EXIT_LLM,
    EXIT_OK,
    EXIT_CONFIG,
    EXIT_USAGE,
    MESSAGES,
    ErrorCode,
    IngestionError,
    InvalidOutputError,
    exit_code,
)

# code, stage, user action, exit code, retried -- PRD G.1
G1 = [
    ("E-INPUT-NOT-FOUND", "validated", "Check the path and file permissions.", 3, "No"),
    ("E-INPUT-TOO-LARGE", "validated", "Supply a smaller file or only the financial-statements section.", 3, "No"),
    ("E-INPUT-NOT-PDF", "validated", "Supply a PDF file.", 3, "No"),
    ("E-INPUT-CORRUPT", "validated / text_extracted", "Re-download or re-export the PDF.", 3, "No"),
    ("E-INPUT-ENCRYPTED", "validated", "Supply an unencrypted copy.", 3, "No"),
    ("E-INPUT-TOO-MANY-PAGES", "validated", "Supply only the relevant pages.", 3, "No"),
    ("E-INPUT-NO-TEXT-LAYER", "text_extracted / statements_located", "Supply a text-based PDF, or a page range that contains text.", 3, "No"),
    ("E-INPUT-PAGE-RANGE", "statements_located", "Correct --pages (e.g. 110-115,120).", 3, "No"),
    ("E-INPUT-PROFILE-INVALID", "received", "Fix the profile file to the documented keys and limits.", 3, "No"),
    ("E-INPUT-SEND-REFUSED", "received", "If the document is public and is not recorded as held out, re-run with --confirm-public-document; a held-out document cannot be sent.", 3, "No"),
    ("E-EXTRACT-NO-STATEMENT-PAGES", "fields_extracted", "Supply the statement pages with --pages.", 4, "No"),
    ("E-EXTRACT-BASIS-UNAVAILABLE", "statements_located", "Review the document; to analyse another basis, re-run with --basis.", 4, "No"),
    ("E-LLM-INVALID-OUTPUT", "fields_extracted", "Re-run; report if it persists.", 5, "Once, with the validation error"),
    ("E-LLM-UNAVAILABLE", "fields_extracted", "Re-run later.", 5, "Yes, with backoff"),
    ("E-LLM-AUTH", "fields_extracted", "Check OPENAI_API_KEY.", 5, "No"),
    ("E-LLM-BUDGET-EXCEEDED", "fields_extracted", "Narrow --pages, or raise the ceiling deliberately.", 5, "No"),
    ("E-CONFIG-INVALID", "received", "Fix the named setting.", 6, "No"),
    ("E-EXPORT-FAILED", "exported", "Check the output directory and re-run.", 7, "No"),
]  # fmt: skip


def test_the_catalogue_has_exactly_the_eighteen_codes_of_g1():
    assert {c.value for c in CATALOGUE} == {row[0] for row in G1} and len(G1) == 18
    assert set(CATALOGUE) == set(ErrorCode) == set(MESSAGES)


@pytest.mark.parametrize("code, stage, action, exit_, retried", G1, ids=[row[0] for row in G1])
def test_each_entry_matches_the_prd_table(code, stage, action, exit_, retried):
    entry = CATALOGUE[ErrorCode(code)]

    assert (entry.stage, entry.action, entry.exit_code, entry.retried) == (stage, action, exit_, retried)


@pytest.mark.parametrize("code, stage, action, exit_, retried", G1, ids=[row[0] for row in G1])
def test_each_message_is_fixed_text_that_says_what_the_user_should_do(code, stage, action, exit_, retried):
    message = MESSAGES[ErrorCode(code)]

    assert action in message and message.endswith(action)
    assert not re.search(r"[{}%]", message.replace("%PDF-", "")), "no placeholder: the text is fixed"


def test_exit_codes_group_by_kind_and_none_collides_with_success_usage_or_internal():
    groups = {
        EXIT_INPUT: {c for c in ErrorCode if c.value.startswith("E-INPUT")},
        EXIT_EXTRACT: {c for c in ErrorCode if c.value.startswith("E-EXTRACT")},
        EXIT_LLM: {c for c in ErrorCode if c.value.startswith("E-LLM")},
        EXIT_CONFIG: {ErrorCode.CONFIG_INVALID},
        EXIT_EXPORT: {ErrorCode.EXPORT_FAILED},
    }
    for exit_, codes in groups.items():
        assert {CATALOGUE[c].exit_code for c in codes} == {exit_}
    assert (EXIT_OK, EXIT_INTERNAL, EXIT_USAGE) == (0, 1, 2) and {3, 4, 5, 6, 7} == set(groups)
    assert not {CATALOGUE[c].exit_code for c in ErrorCode} & {EXIT_OK, EXIT_INTERNAL, EXIT_USAGE}
    assert sum(len(c) for c in groups.values()) == 18  # every code in exactly one group


@pytest.mark.parametrize("code", list(ErrorCode))
def test_an_error_exits_with_its_catalogue_code(code):
    assert exit_code(IngestionError(code)) == CATALOGUE[code].exit_code
    assert exit_code(IngestionError(code, detail="report.pdf")) == CATALOGUE[code].exit_code


def test_a_subclass_of_the_error_keeps_its_codes_exit_code():
    assert exit_code(InvalidOutputError("garbage")) == EXIT_LLM


@pytest.mark.parametrize("error", [ValueError("x"), RuntimeError("y"), KeyError("z"), AssertionError(), OSError("disk"), ZeroDivisionError()])
def test_a_failure_not_in_the_catalogue_is_an_internal_error_with_exit_code_1(error):
    assert exit_code(error) == EXIT_INTERNAL


# --- messages never carry secrets, text from the document, or a stack trace (FR-011.4) -------------------------------------------------------------


def test_no_message_contains_a_key_a_path_or_a_stack_trace():
    for code, message in MESSAGES.items():
        assert "Traceback" not in message and "File \"" not in message and "sk-" not in message
        assert "/Users" not in message and "\\" not in message, code
        assert "OPENAI_API_KEY=" not in message


def test_the_only_key_name_in_a_message_is_the_variable_not_its_value():
    assert "OPENAI_API_KEY" in MESSAGES[ErrorCode.LLM_AUTH] and "OPENAI_API_KEY=" not in MESSAGES[ErrorCode.LLM_AUTH]


def test_the_exception_text_is_the_code_then_the_fixed_message_then_only_the_detail():
    error = IngestionError(ErrorCode.TOO_LARGE, detail="5000 bytes; limit 100 bytes")

    assert str(error) == f"E-INPUT-TOO-LARGE: {MESSAGES[ErrorCode.TOO_LARGE]} (5000 bytes; limit 100 bytes)"
    assert str(IngestionError(ErrorCode.NOT_PDF)) == f"E-INPUT-NOT-PDF: {MESSAGES[ErrorCode.NOT_PDF]}"


def test_the_underlying_library_error_stays_on_the_cause_and_out_of_the_message():
    secret = "library said: page text Revenue 1,234 and key sk-abc123"
    try:
        try:
            raise OSError(secret)
        except OSError as exc:
            raise IngestionError(ErrorCode.CORRUPT) from exc
    except IngestionError as error:
        assert secret not in str(error) and error.__cause__ is not None


def test_the_retry_text_marks_only_the_two_codes_that_retry():
    retried = {c.value: e.retried for c, e in CATALOGUE.items() if e.retried != "No"}

    assert retried == {"E-LLM-INVALID-OUTPUT": "Once, with the validation error", "E-LLM-UNAVAILABLE": "Yes, with backoff"}


def test_every_stage_is_one_of_the_fr_011_states():
    states = {"received", "validated", "text_extracted", "statements_located", "fields_extracted", "validated_fields",
              "calculated", "rules_evaluated", "memo_generated", "exported"}  # fmt: skip
    for entry in CATALOGUE.values():
        assert {part.strip() for part in entry.stage.split("/")} <= states, entry.code
