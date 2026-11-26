from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.runs import Run


class RunQueue(Protocol):
    """What the worker needs of the stored runs. Every write is one transaction."""

    def claim_next(self, worker_id: str, at: datetime) -> Run | None:
        """Take the oldest queued run for the worker, or None when none is queued.

        One transaction selects it (a concurrent claimer skips a locked row), sets it running
        with `worker_id`, `started_at` and `heartbeat_at`, and commits.
        """
        ...

    def get(self, run_id: str) -> Run | None: ...

    def update(self, run_id: str, change: Callable[[Run], Run]) -> Run:
        """Read the run under a lock, apply `change` to it, store the result, commit.

        Raises `RunNotFound` for an unknown id. An error raised by `change` stores nothing.
        """
        ...

    def heartbeat_run(self, run_id: str, at: datetime) -> None:
        """Set `heartbeat_at` of a running run and nothing else; a run in another state stays."""
        ...

    def running_runs(self) -> list[Run]:
        """The running runs, oldest queue time first."""
        ...
