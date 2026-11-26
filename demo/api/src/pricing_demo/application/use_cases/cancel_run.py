from dataclasses import dataclass

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.run_view import RunView, view_runs
from pricing_demo.domain.runs import (
    FINISHED_STATES,
    RunAlreadyFinished,
    RunNotFound,
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
    def __init__(self, repository: RunRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self, run_id: str) -> Cancellation:
        run = self._repository.get(run_id)
        if run is None:
            raise RunNotFound(f"No run has the id {run_id}.")
        if run.state in FINISHED_STATES:
            raise RunAlreadyFinished(f"The run is already {run.state.value}.")
        now = self._clock.now()
        if run.state is RunState.QUEUED:
            run = cancel_queued(run, now)
        else:
            run = request_cancellation(run, now)
        self._repository.save(run)
        view = view_runs([run], self._repository, self._clock)[0]
        return Cancellation(view, cancelled_at_once=run.state is RunState.CANCELLED)
