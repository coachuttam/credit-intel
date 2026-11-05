"""The held-out ledger and the release of a used document (PRD O.2, v0.4.42; the owner's decision of 2026-11-05). Synthetic lines only."""

import json

import pytest

from credit_intel.evaluation.ledger import LEDGER_MEMBERS, RELEASE_MEMBERS, LedgerUnreadable, append_ledger, read_ledger, release_line, used_shas

A, B = "a" * 64, "b" * 64
HEAD = "c" * 40


def line(sha, event, run="H-1", document="H9"):
    return dict(zip(LEDGER_MEMBERS, (document, sha, run, event, "2026-11-04T00:00:00Z", HEAD, "d" * 64), strict=True))


def release(sha, run="H-1", reason="stopped before any page was read", document="H9"):
    return dict(zip(RELEASE_MEMBERS, (document, sha, run, "released", "2026-11-05T00:00:00Z", HEAD, "d" * 64, reason), strict=True))


def write(tmp_path, *records, raw=None):
    path = tmp_path / "ledger.jsonl"
    path.write_text(raw if raw is not None else "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records), encoding="utf-8")
    return path


def test_a_missing_ledger_is_empty_and_good_lines_are_read(tmp_path):
    assert read_ledger(tmp_path / "none.jsonl") == []
    path = write(tmp_path, line(A, "started"), line(A, "completed"), release(A))

    assert [r["event"] for r in read_ledger(path)] == ["started", "completed", "released"]


@pytest.mark.parametrize(
    "records",
    [
        [{**line(A, "started"), "event": "finished"}],  # an unknown event
        [dict(list(line(A, "started").items())[::-1])],  # members out of order
        [{**line(A, "started"), "reason": "extra member"}],  # a use line with a reason
        [{k: v for k, v in release(A).items() if k != "reason"}],  # a release without its reason member
        [release(A)],  # a release of a document never used
        [line(A, "started"), release(A), release(A)],  # a second release
        [line(A, "started"), release(A, reason="   ")],  # an empty reason
        [line(A, "started"), release(A, reason="x" * 1001)],  # too long
        [line(A, "started"), release(B)],  # a release of another document
        [{**line(A, "started"), "run_id": 5}],  # a non-string
    ],
)
def test_a_malformed_ledger_is_unreadable(tmp_path, records):
    with pytest.raises(LedgerUnreadable):
        read_ledger(write(tmp_path, *records))


@pytest.mark.parametrize("raw", ["not json\n", "[]\n", '{"a":1}', "\r\n", "\xff"])
def test_a_ledger_that_is_not_lines_of_objects_is_unreadable(tmp_path, raw):
    with pytest.raises(LedgerUnreadable):
        read_ledger(write(tmp_path, raw=raw))


def test_a_ledger_with_carriage_returns_is_unreadable_even_if_each_line_is_valid(tmp_path):
    text = json.dumps(line(A, "started"), separators=(",", ":")) + "\r\n"
    with pytest.raises(LedgerUnreadable):
        read_ledger(write(tmp_path, raw=text))


def test_a_binary_ledger_is_unreadable(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(LedgerUnreadable):
        read_ledger(path)


def test_a_document_is_used_by_a_started_or_completed_line_and_unused_again_by_a_later_release():
    assert used_shas([line(A, "started")]) == {A}
    assert used_shas([line(A, "started"), line(A, "completed")]) == {A}
    assert used_shas([line(A, "started"), line(A, "completed"), release(A)]) == set()
    assert used_shas([line(A, "started"), release(A), line(A, "started", run="H-2")]) == {A}
    assert used_shas([line(A, "started"), line(B, "started"), release(B)]) == {A}
    assert used_shas([]) == set()


def test_a_release_line_is_built_for_a_used_document_by_the_run_that_used_it_and_with_its_reason():
    records = [line(A, "started"), line(A, "completed")]
    built = release_line(records, A, run_id="H-1", at="2026-11-05T00:00:00Z", freeze_commit=HEAD, assignments_sha256="d" * 64, reason="no page read")

    assert tuple(built) == RELEASE_MEMBERS and built["event"] == "released" and built["document_id"] == "H9" and built["reason"] == "no page read"


@pytest.mark.parametrize(
    ("sha", "run", "reason"),
    [(B, "H-1", "r"), (A, "H-other", "r"), (A, "H-1", ""), (A, "H-1", "  "), (A, "H-1", "x" * 1001)],
)
def test_a_release_is_refused_for_an_unused_document_another_run_or_without_a_reason(sha, run, reason):
    with pytest.raises(ValueError):
        release_line([line(A, "started")], sha, run_id=run, at="t", freeze_commit=HEAD, assignments_sha256="d", reason=reason)


def test_a_release_of_an_already_released_document_is_refused():
    records = [line(A, "started"), release(A)]
    with pytest.raises(ValueError):
        release_line(records, A, run_id="H-1", at="t", freeze_commit=HEAD, assignments_sha256="d", reason="again")


def test_an_appended_release_is_read_back_and_other_lines_are_not_accepted(tmp_path):
    path = write(tmp_path, line(A, "started"), line(A, "completed"))
    append_ledger(path, release(A))

    assert used_shas(read_ledger(path)) == set()
    with pytest.raises(AssertionError):
        append_ledger(path, {"document_id": "H9"})
