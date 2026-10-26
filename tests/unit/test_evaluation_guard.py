"""What may be sent to the hosted API (PRD SEC-10, the owner's G2 rule; Phase 2 Part A; B-231)."""

import hashlib
import json
from pathlib import Path

import pytest

from credit_intel.evaluation.guard import (
    ASSIGNMENTS_PATH,
    MEMBERS,
    SendRefused,
    check_may_send,
    file_sha256,
    load_current_sets,
    refuse_if_held_out,
)

R1 = "a2b9acdfbe79586ffdbe1780c4f14e5b2630743a4c81ee626f812f4c2fff1b44"
R2 = "dfc1ed6c9bcd879a3cfedc06b8f6123d1d7caaf81340f7a437afe395f9b00ea6"
HELD = "c" * 64
OTHER = "d" * 64
ROOT = Path(__file__).resolve().parents[2]


def line(document_id, sha, set_="tuning", event="assigned", moved_from=None, reason=None):
    values = [document_id, sha, set_, "2026-10-20", event, moved_from, reason]
    return json.dumps(dict(zip(MEMBERS, values)), separators=(",", ":"))


def record(tmp_path, *lines, raw=None):
    path = tmp_path / "assignments.jsonl"
    path.write_bytes(raw if raw is not None else ("\n".join(lines) + "\n").encode("utf-8"))
    return path


# --- the committed record ----------------------------------------------------------------------------


def test_the_committed_record_allows_the_two_tuning_reports_and_refuses_every_held_out_one():
    assert check_may_send(R1) == "R1" and check_may_send(R2) == "R2"
    sets = load_current_sets()
    # R1 and R2 are the text-layer tuning reports; S1 and S2 are the tuning scans (OD-17, 2026-10-26).
    assert {document for document, kind in sets.values() if kind == "tuning"} == {"R1", "R2", "S1", "S2"}
    assert ASSIGNMENTS_PATH == ROOT / "tests/eval/assignments.jsonl"
    for sha, (_, kind) in sets.items():
        if kind == "held_out":  # whatever the record holds; no held-out value is copied into a test
            with pytest.raises(SendRefused):
                check_may_send(sha)


def test_an_unrecorded_document_is_refused_with_only_a_short_hash():
    with pytest.raises(SendRefused) as excinfo:
        check_may_send(OTHER)

    assert OTHER[:12] in str(excinfo.value) and OTHER not in str(excinfo.value)
    assert "not on the assignment record" in str(excinfo.value)


# --- tuning, held out and moves ---------------------------------------------------------------------------


def test_a_held_out_document_is_refused_before_anything_is_sent(tmp_path):
    path = record(tmp_path, line("R1", R1), line("H1", HELD, "held_out"))

    assert check_may_send(R1, path) == "R1"
    with pytest.raises(SendRefused) as excinfo:
        check_may_send(HELD, path)
    assert "H1" in str(excinfo.value) and "not a tuning document" in str(excinfo.value)


def test_a_held_out_document_moved_to_tuning_may_then_be_sent(tmp_path):
    path = record(tmp_path, line("H1", HELD, "held_out"), line("H1", HELD, "tuning", "moved", "held_out", "debugged"))

    assert check_may_send(HELD, path) == "H1"


def test_a_tuning_document_moved_to_held_out_may_no_longer_be_sent(tmp_path):
    path = record(tmp_path, line("R1", R1), line("R1", R1, "held_out", "moved", "tuning", "reassigned"))

    with pytest.raises(SendRefused):
        check_may_send(R1, path)


def test_the_last_record_of_a_document_decides(tmp_path):
    path = record(tmp_path, line("R1", R1), line("R2", R2), line("R1", R1, "held_out", "moved", "tuning", "x"))

    assert check_may_send(R2, path) == "R2" and load_current_sets(path)[R1] == ("R1", "held_out")


# --- the guard fails closed --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        b"not json\n",
        b'{"document_id":"R1"}\n',
        b"[]\n",
        b'"text"\n',
        json.dumps({"sha256": R1, "document_id": "R1", "set": "tuning", "assigned_on": "2026-10-20", "event": "assigned", "moved_from": None, "reason": None}).encode() + b"\n",  # members out of order
        line("R1", R1, "archive").encode() + b"\n",  # an unknown set
        b"\xff\xfe\n",
    ],
    ids=["not json", "missing members", "a list", "a string", "members out of order", "unknown set", "not utf-8"],
)
def test_a_malformed_record_refuses_every_document(tmp_path, raw):
    path = record(tmp_path, raw=raw + b"" if raw.endswith(b"\n") else raw)

    with pytest.raises(SendRefused):
        check_may_send(R1, path)


def test_an_unknown_set_on_any_line_refuses_even_the_documents_on_good_lines(tmp_path):
    path = record(tmp_path, line("R1", R1), line("X1", OTHER, "archive"), line("R2", R2))

    for sha in (R1, R2):
        with pytest.raises(SendRefused) as excinfo:
            check_may_send(sha, path)
    assert "line 2" in str(excinfo.value)
    with pytest.raises(SendRefused):
        load_current_sets(path)


def test_reading_the_record_itself_fails_when_it_is_missing_or_not_utf8(tmp_path):
    with pytest.raises(SendRefused) as missing:
        load_current_sets(tmp_path / "absent.jsonl")
    with pytest.raises(SendRefused):
        load_current_sets(record(tmp_path, raw=b"\xff\xfe\n"))

    assert "cannot be read" in str(missing.value) and str(tmp_path) not in str(missing.value)


def test_one_bad_line_among_good_ones_refuses_everything(tmp_path):
    path = record(tmp_path, line("R1", R1), "oops", line("R2", R2))

    for sha in (R1, R2):
        with pytest.raises(SendRefused) as excinfo:
            check_may_send(sha, path)
    assert "line 2" in str(excinfo.value)


def test_a_missing_or_empty_record_refuses_every_document(tmp_path):
    with pytest.raises(SendRefused):
        check_may_send(R1, tmp_path / "absent.jsonl")
    with pytest.raises(SendRefused):
        check_may_send(R1, record(tmp_path, raw=b""))


def test_blank_lines_are_ignored(tmp_path):
    path = record(tmp_path, raw=(line("R1", R1) + "\n\n" + line("R2", R2) + "\n\n").encode())

    assert check_may_send(R2, path) == "R2"


def test_a_refusal_never_names_the_path_or_holds_document_content(tmp_path):
    path = tmp_path / "secret-folder" / "assignments.jsonl"

    with pytest.raises(SendRefused) as excinfo:
        check_may_send(R1, path)

    assert "secret-folder" not in str(excinfo.value) and str(tmp_path) not in str(excinfo.value)


# --- synthetic documents and the live runner ---------------------------------------------------------------------------


def test_a_synthetic_document_passes_only_when_a_test_says_so(tmp_path):
    empty = record(tmp_path, raw=b"")

    assert check_may_send(OTHER, empty, synthetic=True) == "synthetic"
    with pytest.raises(SendRefused):
        check_may_send(OTHER, empty)


def test_the_live_runner_never_asks_for_the_synthetic_exemption():
    live = (ROOT / "tests" / "live" / "test_live_tuning.py").read_text(encoding="utf-8")
    smoke = (ROOT / "tests" / "live" / "test_live_openai.py").read_text(encoding="utf-8")

    assert "synthetic=" not in live and "synthetic=" not in smoke  # no value of the flag, true or false
    assert "run_tuning_document(" in live  # the guard runs inside it


# --- hashing ----------------------------------------------------------------------------------------------------------------


def test_the_file_hash_matches_hashlib_including_files_larger_than_a_chunk(tmp_path):
    small, large = tmp_path / "s.bin", tmp_path / "l.bin"
    small.write_bytes(b"abc")
    large.write_bytes(bytes(range(256)) * 9000)  # about 2.2 MB, more than one 1 MiB chunk

    assert file_sha256(small) == hashlib.sha256(b"abc").hexdigest()
    assert file_sha256(large) == hashlib.sha256(large.read_bytes()).hexdigest()


# --- a held-out document is not even looked at (PRD O.2; the dry run) ---------------------------------------------


def test_a_held_out_document_is_refused_before_inspection_and_the_message_holds_no_content(tmp_path):
    path = record(tmp_path, line("H9", HELD, "held_out"))

    with pytest.raises(SendRefused) as excinfo:
        refuse_if_held_out(HELD, path)

    assert "H9" in str(excinfo.value) and HELD not in str(excinfo.value) and "held out" in str(excinfo.value)


def test_tuning_and_unrecorded_documents_are_not_refused_for_inspection(tmp_path):
    path = record(tmp_path, line("R9", R1, "tuning"))

    assert refuse_if_held_out(R1, path) is None
    assert refuse_if_held_out(OTHER, path) is None


def test_a_document_moved_from_held_out_to_tuning_may_be_inspected_again(tmp_path):
    path = record(tmp_path, line("H9", HELD, "held_out"), line("H9", HELD, "tuning", "moved", "held_out", "debugged a failure"))

    assert refuse_if_held_out(HELD, path) is None


def test_a_missing_or_malformed_record_refuses_inspection_too(tmp_path):
    with pytest.raises(SendRefused):
        refuse_if_held_out(R1, tmp_path / "absent.jsonl")
    with pytest.raises(SendRefused):
        refuse_if_held_out(R1, record(tmp_path, raw=b"not json\n"))
