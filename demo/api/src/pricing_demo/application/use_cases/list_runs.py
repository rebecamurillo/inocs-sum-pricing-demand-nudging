from collections.abc import Collection

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.run_view import RunView, view_runs
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.domain.runs import RunState


class ListRuns:
    def __init__(
        self,
        repository: RunRepository,
        clock: Clock,
        durations: StepDurations | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._durations = durations

    def execute(self, states: Collection[RunState]) -> list[RunView]:
        runs = self._repository.list_by_states(states)
        return view_runs(runs, self._repository, self._clock, self._durations)
