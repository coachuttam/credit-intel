"""When a document may be sent to the hosted API, and the fixed reason it may not (PRD SEC-10, FR-014 criterion 8, G.1; PRD v0.4.27; step S1; B-288)."""

import json

import pytest

from credit_intel.evaluation.guard import MEMBERS, SendRefused
from credit_intel.send_rule import REASONS, SendRefusal, check_send

SHA = "a" * 64


def record(tmp_path, *rows):
    path = tmp_path / "assignments.jsonl"
    path.write_text("".join(json.dumps(dict(zip(MEMBERS, (doc, sha, group, "2026-10-24", "assigned", None, None), strict=True))) + "\n" for doc, sha, group in rows), encoding="utf-8")
    return path


def refusal(tmp_path, assignments, **kw):
    with pytest.raises(SendRefusal) as caught:
        check_send(SHA, external=True, confirmed=kw.pop("confirmed", False), assignments=assignments)
    return caught.value


def test_a_provider_that_sends_nothing_off_the_machine_is_never_checked(tmp_path):
    unreadable = tmp_path / "bad.jsonl"
    unreadable.write_text("{not json", encoding="utf-8")

    assert check_send(SHA, external=False, confirmed=False, assignments=unreadable) == "local"
    assert check_send(SHA, external=False, confirmed=False, assignments=tmp_path / "absent.jsonl") == "local"


def test_a_tuning_document_is_sent_with_or_without_the_confirmation(tmp_path):
    path = record(tmp_path, ("R9", SHA, "tuning"))

    assert check_send(SHA, external=True, confirmed=False, assignments=path) == "tuning"
    assert check_send(SHA, external=True, confirmed=True, assignments=path) == "tuning"


def test_a_held_out_document_is_refused_whatever_the_confirmation(tmp_path):
    path = record(tmp_path, ("H9", SHA, "held_out"))

    for confirmed in (False, True):
        with pytest.raises(SendRefusal) as caught:
            check_send(SHA, external=True, confirmed=confirmed, assignments=path)
        assert caught.value.reason == "held_out"


def test_a_document_that_moved_from_held_out_to_tuning_is_sent(tmp_path):
    path = tmp_path / "assignments.jsonl"
    rows = [dict(zip(MEMBERS, ("H9", SHA, "held_out", "2026-10-24", "assigned", None, None), strict=True)),
            dict(zip(MEMBERS, ("H9", SHA, "tuning", "2026-10-25", "moved", "held_out", "inspected"), strict=True))]  # fmt: skip
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    assert check_send(SHA, external=True, confirmed=False, assignments=path) == "tuning"


def test_an_unrecorded_document_needs_the_confirmation(tmp_path):
    path = record(tmp_path, ("R9", "b" * 64, "tuning"))

    assert refusal(tmp_path, path).reason == "not_recorded"
    assert check_send(SHA, external=True, confirmed=True, assignments=path) == "confirmed"


def test_with_no_record_file_every_document_is_unrecorded(tmp_path):
    absent = tmp_path / "absent.jsonl"

    assert refusal(tmp_path, absent).reason == "not_recorded"
    assert check_send(SHA, external=True, confirmed=True, assignments=absent) == "confirmed"


@pytest.mark.parametrize("content", ["{not json\n", "[]\n", '{"document_id": "R9"}\n', "ÿþ", '{"document_id": 1, "sha256": 2, "set": "tuning", "assigned_on": "x", "event": "y", "moved_from": null, "reason": null}\n'])
def test_a_record_that_exists_but_cannot_be_read_refuses_every_document_even_when_confirmed(tmp_path, content):
    path = tmp_path / "assignments.jsonl"
    path.write_bytes(content.encode("latin-1", errors="replace"))

    for confirmed in (False, True):
        with pytest.raises(SendRefusal) as caught:
            check_send(SHA, external=True, confirmed=confirmed, assignments=path)
        assert caught.value.reason == "record_unreadable"


def test_a_record_that_is_a_directory_is_unreadable_not_absent(tmp_path):
    (tmp_path / "assignments.jsonl").mkdir()

    assert refusal(tmp_path, tmp_path / "assignments.jsonl", confirmed=True).reason == "record_unreadable"


def test_the_message_is_the_reason_word_and_nothing_else(tmp_path):
    path = record(tmp_path, ("H9", SHA, "held_out"))
    error = refusal(tmp_path, path)

    assert str(error) == "held_out" and "H9" not in str(error) and SHA[:12] not in str(error) and str(tmp_path) not in str(error)


def test_a_refusal_is_a_send_refused_so_the_tuning_tools_still_catch_it():
    assert issubclass(SendRefusal, SendRefused) and set(REASONS) == {"held_out", "not_recorded", "record_unreadable"}


def test_only_the_three_reasons_exist():
    for reason in REASONS:
        assert SendRefusal(reason).reason == reason
    with pytest.raises(ValueError):
        SendRefusal("because I said so")
