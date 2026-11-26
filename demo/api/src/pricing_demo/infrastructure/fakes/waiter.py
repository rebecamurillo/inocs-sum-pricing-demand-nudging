import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from pricing_demo.infrastructure.fakes.clock import FixedClock


class FakeWaiter:
    """Moves the injected clock instead of sleeping, so tests drive the worker's timing.

    `on_wait` is called with the new time after each advance, for a test to act at a given
    moment (request a cancellation, release an executor).
    """

    def __init__(
        self, clock: FixedClock, on_wait: Callable[[datetime], None] | None = None
    ) -> None:
        self._clock = clock
        self.on_wait = on_wait
        self.calls = 0

    def wait(self, seconds: float, wake: threading.Event) -> bool:
        self.calls += 1
        # A short real wait lets a thread that is about to finish do so before time moves.
        if wake.wait(0.005):
            return True
        self._clock.advance(timedelta(seconds=seconds))
        if self.on_wait is not None:
            self.on_wait(self._clock.now())
        return False
