from datetime import datetime
from typing import Protocol

from pricing_demo.domain.read_model import RouteFailure


class RouteFailures(Protocol):
    """The failed trip-planner queries of a run, written as the routes step reports them."""

    def add(
        self,
        run_id: str,
        position: int,
        period_id: str | None,
        failure: RouteFailure,
        occurred_at: datetime,
    ) -> None:
        """Record one failure for the run's step at `position`."""
        ...

    def clear(self, run_id: str, position: int) -> None:
        """Remove the step's failures: an interrupted, re-queued routes step starts clean."""
        ...

    def of_run(self, run_id: str) -> list[tuple[RouteFailure, str | None]]:
        """Each failure with its period, ordered by origin, destination and query."""
        ...

    def of_step(self, run_id: str, position: int) -> list[RouteFailure]:
        """The step's failures, in the same order."""
        ...
