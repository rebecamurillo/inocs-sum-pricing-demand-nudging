from collections.abc import Collection

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.run_view import RunView, view_runs
from pricing_demo.domain.runs import RunState


class ListRuns:
    def __init__(self, repository: RunRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self, states: Collection[RunState]) -> list[RunView]:
        return view_runs(self._repository.list_by_states(states), self._repository, self._clock)
