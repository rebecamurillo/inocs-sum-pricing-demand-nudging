from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.domain.runner_liveness import Runner, runner_of
from pricing_demo.domain.runs import Run, RunState, StepName, queue_positions


@dataclass(frozen=True)
class RunView:
    """A run as a client reads it: the stored run and what is derived from it at read time."""

    run: Run
    queue_position: int | None
    runner: Runner
    server_time: datetime
    # Seconds the step last took on the run's instance (the pricing model step of a pricing run).
    step_durations: Mapping[StepName, float] = field(default_factory=dict)


def view_runs(
    runs: list[Run],
    repository: RunRepository,
    clock: Clock,
    durations: StepDurations | None = None,
) -> list[RunView]:
    server_time = clock.now()
    worker_heartbeat = repository.latest_worker_heartbeat()
    positions = queue_positions(repository.list_by_states([RunState.QUEUED]))
    return [
        RunView(
            run=run,
            queue_position=positions.get(run.id),
            runner=runner_of(run, worker_heartbeat, server_time),
            server_time=server_time,
            step_durations=durations.of(run) if durations else {},
        )
        for run in runs
    ]
