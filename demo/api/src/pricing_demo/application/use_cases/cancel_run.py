from dataclasses import dataclass

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.run_view import RunView, view_runs
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.domain.runs import (
    FINISHED_STATES,
    Run,
    RunAlreadyFinished,
    RunState,
    cancel_queued,
    request_cancellation,
)


@dataclass(frozen=True)
class Cancellation:
    view: RunView
    # True: a queued run ended at once. False: a running run was asked to stop.
    cancelled_at_once: bool


class CancelRun:
    def __init__(
        self,
        repository: RunRepository,
        clock: Clock,
        durations: StepDurations | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._durations = durations

    def execute(self, run_id: str) -> Cancellation:
        now = self._clock.now()

        def change(run: Run) -> Run:
            if run.state in FINISHED_STATES:
                raise RunAlreadyFinished(f"The run is already {run.state.value}.")
            if run.state is RunState.QUEUED:
                return cancel_queued(run, now)
            return request_cancellation(run, now)

        # A locked read-modify-write: a claim or a heartbeat that lands meanwhile is kept.
        run = self._repository.update(run_id, change)
        view = view_runs([run], self._repository, self._clock, self._durations)[0]
        return Cancellation(view, cancelled_at_once=run.state is RunState.CANCELLED)
