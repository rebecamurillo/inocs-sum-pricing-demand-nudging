from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import RunNotFound


class ListRouteFailures:
    """The failed trip-planner queries a run recorded, each with its period."""

    def __init__(self, runs: RunRepository, route_failures: RouteFailures) -> None:
        self._runs = runs
        self._route_failures = route_failures

    def execute(self, run_id: str) -> list[tuple[RouteFailure, str | None]]:
        if self._runs.get(run_id) is None:
            raise RunNotFound(f"No run has the id {run_id}.")
        return self._route_failures.of_run(run_id)
