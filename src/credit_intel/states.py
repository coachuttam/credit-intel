"""The processing states of a run and the record of how it moved through them (PRD FR-011.1).

A run is ``received → validated → text_extracted → statements_located → fields_extracted →
validated_fields → calculated → rules_evaluated → memo_generated → exported``, or ``failed`` with the
stage it failed in and the error code. A ``Recorder`` notes each transition with a timestamp from an
injectable clock, enforces that the states come in that order, one after another, and keeps the final
state and error code for the manifest (FR-012.1). It records counts only, never document text.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

RECEIVED = "received"
VALIDATED = "validated"
TEXT_EXTRACTED = "text_extracted"
STATEMENTS_LOCATED = "statements_located"
FIELDS_EXTRACTED = "fields_extracted"
VALIDATED_FIELDS = "validated_fields"
CALCULATED = "calculated"
RULES_EVALUATED = "rules_evaluated"
MEMO_GENERATED = "memo_generated"
EXPORTED = "exported"
FAILED = "failed"

STATES: tuple[str, ...] = (
    RECEIVED, VALIDATED, TEXT_EXTRACTED, STATEMENTS_LOCATED, FIELDS_EXTRACTED,
    VALIDATED_FIELDS, CALCULATED, RULES_EVALUATED, MEMO_GENERATED, EXPORTED,
)  # fmt: skip

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class StageEvent:
    state: str
    at: datetime
    counts: Mapping[str, object] = field(default_factory=dict)  # numbers and identifiers only


class Recorder:
    """Records a run's transitions, in order, with timestamps; and its failure, if any."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._events: list[StageEvent] = []
        self._failed_stage: str | None = None
        self._error_code: str | None = None
        self._failed = False

    def now(self) -> datetime:
        """The current time by this recorder's clock (so a timestamp written beside the events agrees with them in tests)."""
        return self._clock()

    @property
    def events(self) -> tuple[StageEvent, ...]:
        return tuple(self._events)

    @property
    def state(self) -> str | None:
        """The last state entered, or ``None`` before the first."""
        return self._events[-1].state if self._events else None

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def final_state(self) -> str | None:
        """``failed`` after a failure, else the last state entered."""
        return FAILED if self._failed else self.state

    @property
    def failed_stage(self) -> str | None:
        """The state the run was working towards when it failed: the first one it had not entered.

        This is the sense of the ``Stage`` column of the error catalogue (G.1): a missing file fails
        in ``validated``, a model error in ``fields_extracted``, bad configuration in ``received``.
        """
        return self._failed_stage

    @property
    def error_code(self) -> str | None:
        return self._error_code

    def enter(self, state: str, counts: Mapping[str, object] | None = None) -> StageEvent:
        """Enter the next state. States come in the FR-011 order, one after another, and not after a failure."""
        if self._failed:
            raise ValueError("a failed run enters no further state")
        expected = STATES[len(self._events)] if len(self._events) < len(STATES) else None
        if state != expected:
            raise ValueError(f"expected state {expected!r}, got {state!r}")
        event = StageEvent(state, self._clock(), dict(counts or {}))
        self._events.append(event)
        return event

    def fail(self, error_code: str | None = None) -> None:
        """Record a failure in the state the run was working towards. ``None`` is an internal error."""
        if self._failed:
            return
        self._failed = True
        self._failed_stage = STATES[min(len(self._events), len(STATES) - 1)]
        self._error_code = error_code
