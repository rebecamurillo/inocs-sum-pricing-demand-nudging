import threading
from dataclasses import dataclass
from datetime import datetime

from pricing_demo.domain.read_model import RouteFailure


@dataclass(frozen=True)
class _Stored:
    run_id: str
    position: int
    period_id: str | None
    failure: RouteFailure
    occurred_at: datetime


class InMemoryRouteFailures:
    """The failures in a list; passes the same contract suite as the PostgreSQL adapter."""

    def __init__(self) -> None:
        self._rows: list[_Stored] = []
        self._lock = threading.Lock()

    def add(
        self,
        run_id: str,
        position: int,
        period_id: str | None,
        failure: RouteFailure,
        occurred_at: datetime,
    ) -> None:
        with self._lock:
            self._rows.append(_Stored(run_id, position, period_id, failure, occurred_at))

    def clear(self, run_id: str, position: int) -> None:
        with self._lock:
            self._rows = [
                row for row in self._rows if (row.run_id, row.position) != (run_id, position)
            ]

    def of_run(self, run_id: str) -> list[tuple[RouteFailure, str | None]]:
        with self._lock:
            rows = [row for row in self._rows if row.run_id == run_id]
        return [(row.failure, row.period_id) for row in sorted(rows, key=_order)]

    def of_step(self, run_id: str, position: int) -> list[RouteFailure]:
        with self._lock:
            rows = [row for row in self._rows if (row.run_id, row.position) == (run_id, position)]
        return [row.failure for row in sorted(rows, key=_order)]

    def clear_all(self) -> None:
        with self._lock:
            self._rows.clear()


def _order(row: _Stored) -> tuple[str, str, str]:
    return (row.failure.origin_hub, row.failure.destination_hub, row.failure.query)
