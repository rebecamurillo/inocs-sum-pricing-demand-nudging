from collections.abc import Collection
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.runs import Run, RunState


class RunRepository(Protocol):
    def add(self, run: Run) -> None:
        """Store a new run with its steps."""
        ...

    def get(self, run_id: str) -> Run | None: ...

    def list_by_states(self, states: Collection[RunState]) -> list[Run]:
        """The runs in any of the states, oldest queue time first."""
        ...

    def latest_worker_heartbeat(self) -> datetime | None:
        """The most recent report of any worker, or None when no worker has ever reported."""
        ...

    def save(self, run: Run) -> None:
        """Persist the state, finish time, cancellation request and steps of a stored run."""
        ...
