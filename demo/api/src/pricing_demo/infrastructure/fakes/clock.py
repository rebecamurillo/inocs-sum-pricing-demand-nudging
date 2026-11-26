from datetime import datetime, timedelta


class FixedClock:
    """A clock that tells the time it was given until it is moved."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, by: timedelta) -> None:
        self._now += by
