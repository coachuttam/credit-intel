"""The processing states and the recorder (PRD FR-011.1, FR-012.1; Phase 5 step 5c; B-256)."""

from datetime import UTC, datetime, timedelta

import pytest

from credit_intel import states
from credit_intel.states import FAILED, STATES, Recorder


def ticking(start=datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)):
    moments = iter(start + timedelta(seconds=n) for n in range(100))
    return lambda: next(moments)


def test_the_states_are_the_ten_of_fr_011_in_order():
    assert STATES == ("received", "validated", "text_extracted", "statements_located", "fields_extracted",
                      "validated_fields", "calculated", "rules_evaluated", "memo_generated", "exported")  # fmt: skip
    assert FAILED == "failed" and FAILED not in STATES


def test_a_run_through_every_state_is_recorded_with_a_timestamp_each():
    recorder = Recorder(ticking())

    for state in STATES:
        recorder.enter(state, {"n": 1})

    assert [e.state for e in recorder.events] == list(STATES)
    assert [e.at.second for e in recorder.events] == list(range(10))
    assert recorder.state == "exported" and recorder.final_state == "exported" and not recorder.failed


def test_a_run_that_has_not_started_has_no_state():
    recorder = Recorder()

    assert recorder.state is None and recorder.final_state is None and recorder.events == ()


def test_the_default_clock_is_utc_and_timestamps_never_go_back():
    recorder = Recorder()
    first = recorder.enter(STATES[0]).at
    second = recorder.enter(STATES[1]).at

    assert first.tzinfo is UTC and second >= first


@pytest.mark.parametrize("wrong", ["validated", "exported", "failed", "nonsense", ""])
def test_the_first_state_must_be_received(wrong):
    with pytest.raises(ValueError):
        Recorder().enter(wrong)


def test_states_must_come_one_after_another_with_none_skipped_or_repeated():
    recorder = Recorder()
    recorder.enter("received")
    with pytest.raises(ValueError):
        recorder.enter("text_extracted")  # skips one
    with pytest.raises(ValueError):
        recorder.enter("received")  # repeats
    recorder.enter("validated")
    assert recorder.state == "validated"


def test_nothing_is_entered_after_the_last_state():
    recorder = Recorder()
    for state in STATES:
        recorder.enter(state)

    with pytest.raises(ValueError):
        recorder.enter("exported")


def test_a_failure_records_the_stage_it_was_working_towards_and_the_code():
    recorder = Recorder()
    recorder.enter("received")
    recorder.enter("validated")

    recorder.fail("E-INPUT-NO-TEXT-LAYER")

    assert recorder.failed and recorder.final_state == FAILED
    assert recorder.failed_stage == "text_extracted" and recorder.error_code == "E-INPUT-NO-TEXT-LAYER"
    assert recorder.state == "validated"  # the last state entered is still known


def test_the_failed_stage_is_the_first_state_not_entered_and_the_last_if_all_were():
    for entered in range(len(STATES)):
        recorder = Recorder()
        for state in STATES[:entered]:
            recorder.enter(state)
        recorder.fail("E-X")
        assert recorder.failed_stage == STATES[entered]
    done = Recorder()
    for state in STATES:
        done.enter(state)
    done.fail("E-X")
    assert done.failed_stage == "exported"


def test_an_internal_error_is_a_failure_with_no_code():
    recorder = Recorder()
    recorder.enter("received")

    recorder.fail(None)

    assert recorder.failed and recorder.error_code is None and recorder.failed_stage == "validated"


def test_a_failure_before_any_state_is_placed_in_received():
    recorder = Recorder()

    recorder.fail("E-CONFIG-INVALID")

    assert recorder.failed_stage == "received" and recorder.final_state == FAILED


def test_a_failed_run_enters_no_further_state_and_a_second_failure_changes_nothing():
    recorder = Recorder()
    recorder.enter("received")
    recorder.fail("E-A")

    with pytest.raises(ValueError):
        recorder.enter("validated")
    recorder.fail("E-B")
    assert recorder.error_code == "E-A"


def test_the_events_are_a_snapshot_not_a_handle_to_the_recorder():
    recorder = Recorder()
    recorder.enter("received")
    snapshot = recorder.events

    recorder.enter("validated")

    assert len(snapshot) == 1 and len(recorder.events) == 2


def test_the_counts_are_copied_so_a_later_change_cannot_alter_the_record():
    counts = {"pages": 3}
    recorder = Recorder()
    recorder.enter("received", counts)

    counts["pages"] = 99

    assert recorder.events[0].counts == {"pages": 3}


def test_the_extraction_pipeline_uses_the_same_state_names():
    from credit_intel.extraction import pipeline

    for name in ("RECEIVED", "VALIDATED", "TEXT_EXTRACTED", "STATEMENTS_LOCATED", "FIELDS_EXTRACTED", "VALIDATED_FIELDS", "FAILED"):
        assert getattr(pipeline, name) == getattr(states, name)
