from collections.abc import Collection
from datetime import datetime

from pricing_demo.domain.runs import Run, RunState


class InMemoryRunRepository:
    """Stores runs in a dict; passes the same contract suite as the PostgreSQL repository."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._worker_heartbeats: list[datetime] = []

    def add(self, run: Run) -> None:
        if run.id in self._runs:
            raise ValueError(f"Run {run.id} is already stored.")
        self._runs[run.id] = run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_by_states(self, states: Collection[RunState]) -> list[Run]:
        found = [run for run in self._runs.values() if run.state in states]
        return sorted(found, key=lambda run: (run.queued_at, run.id))

    def latest_worker_heartbeat(self) -> datetime | None:
        return max(self._worker_heartbeats, default=None)

    def save(self, run: Run) -> None:
        if run.id not in self._runs:
            raise KeyError(run.id)
        self._runs[run.id] = run

    def record_worker_heartbeat(self, at: datetime) -> None:
        self._worker_heartbeats.append(at)
