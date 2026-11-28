from collections.abc import Callable, Collection
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
        """Persist the state, finish time, cancellation request and steps of a stored run.

        Not safe against a concurrent writer: it overwrites what another transaction wrote
        since the run was read. No use case calls it; they call `update`.
        """
        ...

    def update(self, run_id: str, change: Callable[[Run], Run]) -> Run:
        """Read the run under a lock, apply `change`, store the result in one transaction.

        Raises `RunNotFound` for an unknown id; an error raised by `change` stores nothing.
        """
        ...
