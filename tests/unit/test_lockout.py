"""The limit on failed token attempts, alone (PRD SEC-15, OD-34 (a); Phase 7 step 4)."""

import pytest

from credit_intel.api.lockout import LOCKOUT_SECONDS, MAX_FAILURES, MAX_TRACKED, WINDOW_SECONDS, FailedAttempts


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def limiter(clock, **kwargs):
    return FailedAttempts(clock=clock, **kwargs)


def test_the_values_are_five_failures_in_five_minutes_and_fifteen_minutes_locked():
    assert (MAX_FAILURES, WINDOW_SECONDS, LOCKOUT_SECONDS, MAX_TRACKED) == (5, 300.0, 900.0, 4096)


def test_four_failures_do_not_lock_and_the_fifth_does(clock):
    attempts = limiter(clock)
    for _ in range(MAX_FAILURES - 1):
        assert attempts.record_failure("a") is False and attempts.locked_for("a") is None
    assert attempts.record_failure("a") is True
    assert attempts.locked_for("a") == 900


def test_the_time_left_counts_down_in_whole_seconds_rounded_up_and_is_never_less_than_one(clock):
    attempts = limiter(clock)
    for _ in range(5):
        attempts.record_failure("a")
    clock.advance(0.2)
    assert attempts.locked_for("a") == 900  # 899.8 seconds left: rounded up
    clock.advance(899.0)
    assert attempts.locked_for("a") == 1  # 0.8 left
    clock.advance(0.79)
    assert attempts.locked_for("a") == 1  # 0.01 left: still locked, shown as 1
    clock.advance(0.02)
    assert attempts.locked_for("a") is None


def test_the_lock_ends_exactly_when_the_time_is_up_and_the_record_is_dropped(clock):
    attempts = limiter(clock)
    for _ in range(5):
        attempts.record_failure("a")
    clock.advance(LOCKOUT_SECONDS)
    assert attempts.locked_for("a") is None and len(attempts) == 0


def test_after_a_lock_the_count_starts_again_from_nothing(clock):
    attempts = limiter(clock)
    for _ in range(5):
        attempts.record_failure("a")
    clock.advance(LOCKOUT_SECONDS + 1)
    for _ in range(4):
        assert attempts.record_failure("a") is False
    assert attempts.locked_for("a") is None
    assert attempts.record_failure("a") is True


def test_failures_older_than_the_window_do_not_count(clock):
    attempts = limiter(clock)
    for _ in range(4):
        attempts.record_failure("a")
    clock.advance(WINDOW_SECONDS)  # the four are exactly a window old: they no longer count
    assert attempts.record_failure("a") is False and attempts.locked_for("a") is None


def test_failures_just_inside_the_window_still_count(clock):
    attempts = limiter(clock)
    for _ in range(4):
        attempts.record_failure("a")
    clock.advance(WINDOW_SECONDS - 0.5)
    assert attempts.record_failure("a") is True


def test_the_window_slides_so_spread_out_failures_never_lock(clock):
    attempts = limiter(clock)
    for _ in range(50):
        assert attempts.record_failure("a") is False
        clock.advance(WINDOW_SECONDS / 4 + 1)  # no more than three in any window
    assert attempts.locked_for("a") is None


def test_addresses_are_counted_apart(clock):
    attempts = limiter(clock)
    for _ in range(4):
        attempts.record_failure("a")
        attempts.record_failure("b")
    assert attempts.record_failure("a") is True and attempts.locked_for("a") == 900 and attempts.locked_for("b") is None
    assert attempts.locked_for("never-seen") is None


def test_a_right_credential_clears_the_failures_of_an_address_that_is_not_locked(clock):
    attempts = limiter(clock)
    for _ in range(4):
        attempts.record_failure("a")
    attempts.record_success("a")
    for _ in range(4):
        assert attempts.record_failure("a") is False
    assert attempts.record_failure("a") is True


def test_a_right_credential_does_not_end_a_lock(clock):
    attempts = limiter(clock)
    for _ in range(5):
        attempts.record_failure("a")
    attempts.record_success("a")
    assert attempts.locked_for("a") == 900


def test_a_success_for_an_address_never_seen_is_nothing(clock):
    attempts = limiter(clock)
    attempts.record_success("x")
    assert len(attempts) == 0


def test_only_the_most_recent_addresses_are_kept_so_a_flood_cannot_grow_the_state_without_end(clock):
    attempts = limiter(clock, max_tracked=3)
    for name in "abcd":
        attempts.record_failure(name)
    assert len(attempts) == 3
    for _ in range(5):
        attempts.record_failure("e")
    assert len(attempts) == 3 and attempts.locked_for("e") == 900
    attempts.record_failure("b")
    assert len(attempts) == 3  # an address already held is refreshed, not added twice


def test_the_arguments_can_be_changed_for_a_test(clock):
    attempts = limiter(clock, max_failures=2, window_seconds=10, lockout_seconds=30)
    attempts.record_failure("a")
    assert attempts.record_failure("a") is True and attempts.locked_for("a") == 30
