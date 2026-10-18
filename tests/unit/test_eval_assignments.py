"""Validator and tests for the assignment record (PRD O.2, F3; AC-EVAL-1 to AC-EVAL-7).

``tests/eval/assignments.jsonl`` is the append-only record of which evaluation
documents are tuning or held-out. The validator uses the standard library only.
It checks that the file is consistent within itself and (when git is available)
that it only ever grows. It does not check a SHA-256 against a PDF: the PDFs are
private and are not in the repository.

Every failure names the violated check and a 1-based line number, or a byte
offset when the bytes are not valid UTF-8.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RELATIVE_PATH = "tests/eval/assignments.jsonl"
ASSIGNMENTS = REPO_ROOT / RELATIVE_PATH

MEMBERS = ("document_id", "sha256", "set", "assigned_on", "event", "moved_from", "reason")
SETS = ("tuning", "held_out")
EVENTS = ("assigned", "moved")
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class Failure:
    check: str
    line: int | None = None
    byte_offset: int | None = None


class _DuplicateMember(ValueError):
    pass


def _no_duplicate_members(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _DuplicateMember(keys)
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def _compact(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _is_iso_date(value) -> bool:
    if not (isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _field_failures(obj: dict) -> list[str]:
    failures = []
    if not (isinstance(obj["document_id"], str) and re.fullmatch(r"[A-Z][0-9]+", obj["document_id"])):
        failures.append("document-id")
    if not (isinstance(obj["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", obj["sha256"])):
        failures.append("sha256-format")
    if obj["set"] not in SETS:
        failures.append("set-value")
    if not _is_iso_date(obj["assigned_on"]):
        failures.append("iso-date")
    if obj["event"] not in EVENTS:
        failures.append("event-value")
    if obj["moved_from"] is not None and not isinstance(obj["moved_from"], str):
        failures.append("moved-from-type")
    if obj["reason"] is not None and not isinstance(obj["reason"], str):
        failures.append("reason-type")
    return failures


def validate(data: bytes, head: bytes | None = None) -> list[Failure]:
    """Check ``data`` against the PRD O.2 rules; ``head`` is the HEAD version, if any."""
    failures: list[Failure] = []
    body = data
    if data.startswith(BOM):
        failures.append(Failure("byte-order-mark", line=1))
        body = data[len(BOM):]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        return failures + [Failure("valid-utf8", byte_offset=error.start + (len(data) - len(body)))]

    lines = text.split("\n")  # LF only: never str.splitlines (U+2028 must not split)
    if text and not text.endswith("\n"):
        failures.append(Failure("ends-with-lf", line=len(lines)))
    else:
        lines = lines[:-1]  # the empty piece after the final LF

    state: dict[str, tuple[str, str]] = {}  # document_id -> (first sha256, current set)
    owner: dict[str, str] = {}  # sha256 -> document_id
    previous_date: str | None = None
    for number, line in enumerate(lines, start=1):

        def fail(check: str, number: int = number) -> None:
            failures.append(Failure(check, line=number))

        if "\r" in line:
            fail("no-carriage-return")
        if line == "":
            fail("no-blank-lines")
            continue
        try:
            obj = json.loads(line, object_pairs_hook=_no_duplicate_members, parse_constant=_reject_constant)
        except _DuplicateMember:
            fail("members-in-order")
            continue
        except ValueError:
            fail("valid-json")
            continue
        if not isinstance(obj, dict) or tuple(obj) != MEMBERS:
            fail("members-in-order")
            continue
        if line != _compact(obj):
            fail("compact-form")
        field_failures = _field_failures(obj)
        for check in field_failures:
            fail(check)
        if field_failures:
            continue

        document, sha, set_, on, event, moved_from, reason = obj.values()
        if previous_date is not None and on < previous_date:
            fail("assigned-on-not-decreasing")
        previous_date = on
        if owner.setdefault(sha, document) != document:
            fail("sha256-single-id")
        if document not in state:
            if event != "assigned":
                fail("first-line-assigned")
            if moved_from is not None or reason is not None:
                fail("first-line-null-fields")
            state[document] = (sha, set_)
            continue
        first_sha, current = state[document]
        if event != "moved":
            fail("single-assigned")
        else:
            if moved_from != current:
                fail("moved-from-matches-current-set")
            if set_ == current:
                fail("move-changes-set")
            elif (current, set_) != ("held_out", "tuning"):
                fail("move-held-out-to-tuning-only")
            if not reason:
                fail("reason-non-empty")
        if sha != first_sha:
            fail("same-sha256-as-first-line")
        state[document] = (first_sha, set_)

    if head is not None and not data.startswith(head):
        offset = next(
            (i for i, (a, b) in enumerate(zip(data, head)) if a != b), min(len(data), len(head))
        )
        failures.append(Failure("prefix-of-head", line=data[:offset].count(b"\n") + 1))
    return failures


def head_version(repo_root: Path, relative_path: str) -> tuple[bytes | None, str]:
    """The file as committed at HEAD, or ``(None, reason)`` when there is none."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{relative_path}"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return None, f"git is not available ({type(error).__name__})"
    if result.returncode != 0:
        return None, "no HEAD version of the file (untracked file, or not a git checkout)"
    return result.stdout, ""


# --- Test helpers ---------------------------------------------------------------

SHA_A, SHA_B, SHA_C = "a" * 64, "b" * 64, "c" * 64

R1_LINE = (
    '{"document_id":"R1","sha256":"a2b9acdfbe79586ffdbe1780c4f14e5b2630743a4c81ee626f812f4c2fff1b44",'
    '"set":"tuning","assigned_on":"2026-10-13","event":"assigned","moved_from":null,"reason":null}'
)
R2_LINE = (
    '{"document_id":"R2","sha256":"dfc1ed6c9bcd879a3cfedc06b8f6123d1d7caaf81340f7a437afe395f9b00ea6",'
    '"set":"tuning","assigned_on":"2026-10-13","event":"assigned","moved_from":null,"reason":null}'
)


def record(**overrides) -> dict:
    base = {
        "document_id": "R1",
        "sha256": SHA_A,
        "set": "tuning",
        "assigned_on": "2026-10-13",
        "event": "assigned",
        "moved_from": None,
        "reason": None,
    }
    return base | overrides


def line_of(**overrides) -> str:
    return _compact(record(**overrides))


def file_of(*lines: str) -> bytes:
    return "".join(line + "\n" for line in lines).encode("utf-8")


def held_out(document="H1", sha=SHA_B, on="2026-10-14") -> str:
    return line_of(document_id=document, sha256=sha, set="held_out", assigned_on=on)


def move(document="H1", sha=SHA_B, on="2026-10-15", **overrides) -> str:
    fields = {
        "document_id": document,
        "sha256": sha,
        "set": "tuning",
        "assigned_on": on,
        "event": "moved",
        "moved_from": "held_out",
        "reason": "inspected to debug a failure",
    }
    return line_of(**(fields | overrides))


def found(data: bytes, head: bytes | None = None) -> list[tuple[int | None, str]]:
    return [(f.line, f.check) for f in validate(data, head)]


# --- AC-EVAL-1: valid lines ---------------------------------------------------


def test_ac_eval_1_valid_file_passes():
    data = file_of(line_of(), held_out(), move())
    assert validate(data) == []


def test_ac_eval_1_the_two_prd_lines_pass():
    assert validate(file_of(R1_LINE, R2_LINE)) == []


def test_an_empty_file_has_no_violation():
    assert validate(b"") == []


# --- AC-EVAL-2: members, formats, JSON ------------------------------------------


def _reordered() -> str:
    obj = record()
    swapped = {"sha256": obj.pop("sha256"), **obj}
    return json.dumps(swapped, separators=(",", ":"))


def _without(member: str) -> str:
    obj = record()
    del obj[member]
    return _compact(obj)


@pytest.mark.parametrize(
    ("text", "check"),
    [
        pytest.param(_reordered(), "members-in-order", id="members out of order"),
        pytest.param(_without("reason"), "members-in-order", id="missing member"),
        pytest.param(_compact(record() | {"extra": 1}), "members-in-order", id="extra member"),
        pytest.param(
            '{"document_id":"R1","document_id":"R2","sha256":"x"}', "members-in-order", id="duplicate member"
        ),
        pytest.param("[]", "members-in-order", id="not an object"),
        pytest.param(line_of(sha256="a" * 63), "sha256-format", id="63-character sha256"),
        pytest.param(line_of(sha256="A" * 64), "sha256-format", id="uppercase sha256"),
        pytest.param(line_of(sha256=1), "sha256-format", id="sha256 not a string"),
        pytest.param(line_of(assigned_on="13-10-2026"), "iso-date", id="day-first date"),
        pytest.param(line_of(assigned_on="20261013"), "iso-date", id="basic-format date"),
        pytest.param(line_of(assigned_on="2026-13-01"), "iso-date", id="impossible month"),
        pytest.param(line_of(assigned_on="2026-10-13T00:00:00"), "iso-date", id="date-time"),
        pytest.param(line_of(set="validation"), "set-value", id="unknown set"),
        pytest.param(line_of(event="created"), "event-value", id="unknown event"),
        pytest.param(line_of(document_id="r1"), "document-id", id="lowercase document_id"),
        pytest.param(line_of(document_id="R"), "document-id", id="document_id without digits"),
        pytest.param(line_of(document_id="R1a"), "document-id", id="document_id with a letter suffix"),
        pytest.param(line_of(moved_from=3), "moved-from-type", id="moved_from not a string"),
        pytest.param(line_of(reason=3), "reason-type", id="reason not a string"),
        pytest.param("{", "valid-json", id="truncated JSON"),
        pytest.param("not json", "valid-json", id="not JSON"),
        pytest.param(line_of()[:-1] + ",}", "valid-json", id="trailing comma"),
        pytest.param(line_of().replace('"reason":null', '"reason":NaN'), "valid-json", id="NaN constant"),
    ],
)
def test_ac_eval_2_malformed_lines_fail_naming_line_and_check(text, check):
    assert (1, check) in found((text + "\n").encode("utf-8"))


def test_failures_name_the_line_they_occur_on():
    data = file_of(R1_LINE, line_of(sha256="A" * 64, document_id="R2"), R2_LINE)
    assert (2, "sha256-format") in found(data)
    assert {line for line, _ in found(data)} == {2}


# --- AC-EVAL-3: event sequence ------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param(
            [move()], (1, "first-line-assigned"), id="first line is moved"
        ),
        pytest.param(
            [line_of(moved_from="tuning")], (1, "first-line-null-fields"), id="assigned line with moved_from"
        ),
        pytest.param(
            [line_of(reason="why")], (1, "first-line-null-fields"), id="assigned line with a reason"
        ),
        pytest.param(
            [held_out(), held_out()], (2, "single-assigned"), id="second assigned for one ID"
        ),
        pytest.param(
            [held_out(), move(moved_from="tuning")], (2, "moved-from-matches-current-set"), id="moved_from is not the current set"
        ),
        pytest.param(
            [held_out(), move(set="held_out")], (2, "move-changes-set"), id="move to the same set"
        ),
        pytest.param(
            [line_of(document_id="H1", sha256=SHA_B), move(set="held_out", moved_from="tuning")],
            (2, "move-held-out-to-tuning-only"),
            id="move from tuning to held_out",
        ),
        pytest.param(
            [held_out(), move(reason="")], (2, "reason-non-empty"), id="move with an empty reason"
        ),
        pytest.param(
            [held_out(), move(reason=None)], (2, "reason-non-empty"), id="move with a null reason"
        ),
    ],
)
def test_ac_eval_3_sequence_violations_fail(lines, expected):
    assert expected in found(file_of(*lines))


def test_a_moved_document_cannot_be_moved_again():
    data = file_of(held_out(), move(), move(on="2026-10-16", moved_from="tuning", set="held_out"))
    assert (3, "move-held-out-to-tuning-only") in found(data)


# --- AC-EVAL-4: identity, order, compact form, newlines -------------------------


def test_ac_eval_4_one_sha256_under_two_ids_fails():
    data = file_of(line_of(), line_of(document_id="R2"))
    assert (2, "sha256-single-id") in found(data)


def test_ac_eval_4_moved_line_with_a_different_sha256_fails():
    data = file_of(held_out(), move(sha=SHA_C))
    assert (2, "same-sha256-as-first-line") in found(data)


def test_ac_eval_4_assigned_on_decreasing_fails():
    data = file_of(line_of(assigned_on="2026-10-14"), line_of(document_id="R2", sha256=SHA_B, assigned_on="2026-10-13"))
    assert (2, "assigned-on-not-decreasing") in found(data)


def test_ac_eval_4_equal_dates_are_allowed():
    data = file_of(R1_LINE, R2_LINE)
    assert validate(data) == []


def test_ac_eval_4_line_not_in_compact_form_fails():
    spaced = json.dumps(record())  # default separators put spaces after , and :
    assert (1, "compact-form") in found((spaced + "\n").encode("utf-8"))


def test_ac_eval_4_non_ascii_written_as_an_escape_fails():
    escaped = json.dumps(
        record(document_id="H1", sha256=SHA_B, set="tuning", assigned_on="2026-10-15", event="moved",
               moved_from="held_out", reason="caf\u00e9"),
        separators=(",", ":"), ensure_ascii=True,
    )
    assert "\\u00e9" in escaped
    assert (2, "compact-form") in found(file_of(held_out(), escaped))


def test_ac_eval_4_missing_trailing_newline_fails():
    data = file_of(line_of())[:-1]
    assert (1, "ends-with-lf") in found(data)


def test_ac_eval_4_blank_line_fails():
    data = file_of(R1_LINE, "", R2_LINE)
    assert (2, "no-blank-lines") in found(data)


# --- AC-EVAL-5: prefix check ----------------------------------------------------


def test_ac_eval_5_appending_to_head_passes():
    head = file_of(R1_LINE, R2_LINE)
    assert found(head + file_of(held_out(on="2026-10-14")), head) == []


def test_ac_eval_5_unchanged_file_passes():
    head = file_of(R1_LINE, R2_LINE)
    assert found(head, head) == []


def test_ac_eval_5_edited_earlier_line_fails():
    head = file_of(R1_LINE, R2_LINE)
    edited = file_of(R1_LINE.replace("2026-10-13", "2026-10-12"), R2_LINE)
    assert (1, "prefix-of-head") in found(edited, head)


def test_ac_eval_5_edit_on_a_later_line_names_that_line():
    head = file_of(R1_LINE, R2_LINE)
    edited = file_of(R1_LINE, R2_LINE.replace("2026-10-13", "2026-10-12"))
    assert (2, "prefix-of-head") in found(edited, head)


def test_ac_eval_5_deleted_last_line_names_the_first_missing_line():
    head = file_of(R1_LINE, R2_LINE)
    assert (2, "prefix-of-head") in found(file_of(R1_LINE), head)


def test_ac_eval_5_deleted_first_line_fails():
    head = file_of(R1_LINE, R2_LINE)
    assert (1, "prefix-of-head") in found(file_of(R2_LINE), head)


def test_ac_eval_5_reordered_lines_fail():
    head = file_of(R1_LINE, R2_LINE)
    assert (1, "prefix-of-head") in found(file_of(R2_LINE, R1_LINE), head)


def test_ac_eval_5_incomplete_last_head_line_is_reported_at_that_line():
    head = file_of(R1_LINE, R2_LINE)
    assert (2, "prefix-of-head") in found(head[: len(head) - 10], head)


def test_ac_eval_5_no_head_version_means_no_prefix_check():
    assert found(file_of(R1_LINE), None) == []


def _git(path: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, env=env,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_ac_eval_5_head_version_is_read_from_a_git_checkout(tmp_path):
    (tmp_path / "tests" / "eval").mkdir(parents=True)
    target = tmp_path / RELATIVE_PATH
    target.write_bytes(file_of(R1_LINE, R2_LINE))

    version, reason = head_version(tmp_path, RELATIVE_PATH)
    assert version is None and "HEAD" in reason  # not a git checkout yet

    _git(tmp_path, "init", "-q")
    version, reason = head_version(tmp_path, RELATIVE_PATH)
    assert version is None and "HEAD" in reason  # a repository, but no commit and not tracked

    _git(tmp_path, "add", RELATIVE_PATH)
    _git(tmp_path, "commit", "-q", "-m", "assignments")
    head, reason = head_version(tmp_path, RELATIVE_PATH)
    assert head == target.read_bytes() and reason == ""

    appended = target.read_bytes() + file_of(held_out())
    assert found(appended, head) == []
    edited = target.read_bytes().replace(b"2026-10-13", b"2026-10-12", 1)
    assert (1, "prefix-of-head") in found(edited, head)


# --- AC-EVAL-6: the committed file ----------------------------------------------


def test_ac_eval_6_committed_file_passes_the_validator():
    assert validate(ASSIGNMENTS.read_bytes()) == []


def test_ac_eval_6_committed_file_holds_the_owner_supplied_r1_and_r2_lines():
    lines = ASSIGNMENTS.read_bytes().decode("utf-8").split("\n")
    assert lines[:2] == [R1_LINE, R2_LINE]


def test_ac_eval_6_committed_file_only_extends_its_head_version():
    head, reason = head_version(REPO_ROOT, RELATIVE_PATH)
    if head is None:
        pytest.skip(reason)
    assert validate(ASSIGNMENTS.read_bytes(), head) == []


# --- AC-EVAL-7: encoding and newlines ---------------------------------------------


def test_ac_eval_7_crlf_line_endings_fail():
    data = file_of(R1_LINE, R2_LINE).replace(b"\n", b"\r\n")
    assert (1, "no-carriage-return") in found(data)


def test_ac_eval_7_byte_order_mark_fails():
    assert (1, "byte-order-mark") in found(BOM + file_of(R1_LINE))


def test_ac_eval_7_invalid_utf8_fails_with_a_byte_offset():
    data = file_of(R1_LINE) + b"\xff\n"
    failures = validate(data)
    assert [(f.check, f.byte_offset, f.line) for f in failures] == [("valid-utf8", len(file_of(R1_LINE)), None)]


def test_ac_eval_7_raw_non_ascii_in_reason_passes():
    data = file_of(held_out(), move(reason="café – re-examined"))
    assert "café" in data.decode("utf-8")
    assert validate(data) == []


def test_ac_eval_7_raw_u2028_in_reason_does_not_split_the_line():
    data = file_of(held_out(), move(reason="first second"))
    text = data.decode("utf-8")
    assert " " in text
    assert len(text.splitlines()) > text.count("\n")  # a Unicode-aware split would break the line
    assert validate(data) == []
