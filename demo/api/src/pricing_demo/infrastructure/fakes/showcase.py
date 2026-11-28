import threading
from collections.abc import Collection
from datetime import datetime

from pricing_demo.application.ports.showcase import ShowcaseMark


class InMemoryShowcase:
    """The one mark in memory; passes the same contract suite as the PostgreSQL adapter."""

    def __init__(self) -> None:
        self._mark: ShowcaseMark | None = None
        self._lock = threading.Lock()

    def mark(self, pricing_version_id: str, period_id: str, at: datetime) -> None:
        with self._lock:
            self._mark = ShowcaseMark(pricing_version_id, period_id, at)

    def current(self) -> ShowcaseMark | None:
        with self._lock:
            return self._mark

    # What the deletion of versions does (the database cascades); the port has no such method.
    def drop_version(self, version_ids: Collection[str]) -> None:
        with self._lock:
            if self._mark is not None and self._mark.pricing_version_id in version_ids:
                self._mark = None
