from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.run_view import RunView, view_runs
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.domain.runs import RunNotFound


class GetRun:
    def __init__(
        self,
        repository: RunRepository,
        clock: Clock,
        durations: StepDurations | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._durations = durations

    def execute(self, run_id: str) -> RunView:
        run = self._repository.get(run_id)
        if run is None:
            raise RunNotFound(f"No run has the id {run_id}.")
        return view_runs([run], self._repository, self._clock, self._durations)[0]
