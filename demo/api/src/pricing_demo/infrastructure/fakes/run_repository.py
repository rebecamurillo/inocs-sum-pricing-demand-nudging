import threading
from collections.abc import Callable, Collection
from dataclasses import replace
from datetime import datetime

from pricing_demo.domain.runs import Run, RunNotFound, RunState, start


class InMemoryRunRepository:
    """Stores runs in a dict; passes the same contract suite as the PostgreSQL repository.

    One lock guards every access: the worker's executor runs in a thread of its own.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._worker_heartbeats: list[datetime] = []
        self._lock = threading.Lock()

    def add(self, run: Run) -> None:
        with self._lock:
            if run.id in self._runs:
                raise ValueError(f"Run {run.id} is already stored.")
            self._runs[run.id] = run

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_by_states(self, states: Collection[RunState]) -> list[Run]:
        with self._lock:
            found = [run for run in self._runs.values() if run.state in states]
        return sorted(found, key=lambda run: (run.queued_at, run.id))

    def latest_worker_heartbeat(self) -> datetime | None:
        with self._lock:
            return max(self._worker_heartbeats, default=None)

    def save(self, run: Run) -> None:
        with self._lock:
            if run.id not in self._runs:
                raise KeyError(run.id)
            self._runs[run.id] = run

    def update(self, run_id: str, change: Callable[[Run], Run]) -> Run:
        with self._lock:
            current = self._runs.get(run_id)
            if current is None:
                raise RunNotFound(f"No run has the id {run_id}.")
            changed = change(current)
            self._runs[run_id] = changed
            return changed

    def claim_next(self, worker_id: str, at: datetime) -> Run | None:
        with self._lock:
            queued = [run for run in self._runs.values() if run.state is RunState.QUEUED]
            if not queued:
                return None
            oldest = min(queued, key=lambda run: (run.queued_at, run.id))
            claimed = start(oldest, at, worker_id)
            self._runs[claimed.id] = claimed
            return claimed

    def heartbeat_run(self, run_id: str, at: datetime) -> None:
        with self._lock:
            current = self._runs.get(run_id)
            if current is not None and current.state is RunState.RUNNING:
                self._runs[run_id] = replace(current, heartbeat_at=at)

    def running_runs(self) -> list[Run]:
        return self.list_by_states([RunState.RUNNING])

    def record_worker_heartbeat(self, at: datetime) -> None:
        with self._lock:
            self._worker_heartbeats.append(at)
