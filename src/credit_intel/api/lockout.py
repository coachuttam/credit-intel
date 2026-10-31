"""A limit on failed token attempts, per client address (PRD SEC-15, OD-34 (a); Phase 7 step 4).

A bearer token is only as strong as the number of guesses an attacker can make. After ``MAX_FAILURES`` requests that presented a wrong credential within ``WINDOW_SECONDS``,
the client address is **locked out for ``LOCKOUT_SECONDS``**: every request from it that needs the token is refused with ``429`` and ``Retry-After`` **before the token
is looked at**, so a guess made during the lock-out cannot succeed even if it is right. A request that presented no credential at all is only challenged (``401``) and
is not counted: it tells an attacker nothing and a browser or a probe sends them. ``GET /health`` needs no token and is outside all of this.

The values are fixed in the code, like the report's 120 s and the upload's 30 s idle time, and are not settings. The state is in memory (a restart clears it, as it
clears every in-flight run) and is bounded: at most ``MAX_TRACKED`` addresses are kept, the oldest first to go, so a flood of addresses cannot grow it without end.

The address is the one the connection came from. Behind a reverse proxy that is the proxy's address, so everyone would share one count; the proxy settings and the
trust in forwarded addresses belong to the proxy step (SEC-15, OD-36) and are not here. In the container as shipped (published on the host's loopback address only)
the service likewise sees one address for every client on that host.
"""

import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

MAX_FAILURES = 5
WINDOW_SECONDS = 300.0
LOCKOUT_SECONDS = 900.0
MAX_TRACKED = 4096


@dataclass
class _Record:
    failures: deque[float] = field(default_factory=deque)
    locked_until: float = 0.0


class FailedAttempts:
    def __init__(self, *, max_failures: int = MAX_FAILURES, window_seconds: float = WINDOW_SECONDS, lockout_seconds: float = LOCKOUT_SECONDS,
                 max_tracked: int = MAX_TRACKED, clock: Callable[[], float] = time.monotonic) -> None:  # fmt: skip
        self.max_failures, self.window, self.lockout, self.max_tracked, self._clock = max_failures, window_seconds, lockout_seconds, max_tracked, clock
        self._records: OrderedDict[str, _Record] = OrderedDict()

    def __len__(self) -> int:
        return len(self._records)

    def locked_for(self, address: str) -> int | None:
        """Whole seconds left of a lock-out on ``address``, or ``None`` if it is not locked."""
        record = self._records.get(address)
        if record is None:
            return None
        remaining = record.locked_until - self._clock()
        if remaining > 0:
            return max(1, int(remaining + 0.999))
        if record.locked_until and not record.failures:
            del self._records[address]  # the lock-out is over and nothing else is held
        return None

    def record_failure(self, address: str) -> bool:
        """Count a wrong credential. Returns whether this one locked the address."""
        now = self._clock()
        record = self._records.pop(address, None) or _Record()
        while record.failures and now - record.failures[0] >= self.window:
            record.failures.popleft()
        record.failures.append(now)
        locked = len(record.failures) >= self.max_failures
        if locked:
            record.locked_until = now + self.lockout
            record.failures.clear()  # the next count starts after the lock-out
        self._records[address] = record  # most recently used last
        while len(self._records) > self.max_tracked:
            self._records.popitem(last=False)
        return locked

    def record_success(self, address: str) -> None:
        """A right credential clears the failures of an address that is not locked (a locked one never gets this far)."""
        record = self._records.get(address)
        if record is not None and record.locked_until <= self._clock():
            del self._records[address]
