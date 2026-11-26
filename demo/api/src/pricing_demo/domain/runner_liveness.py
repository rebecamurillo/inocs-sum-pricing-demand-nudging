"""Whether the process that should be working on a run is still reporting."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from pricing_demo.domain.runs import FINISHED_STATES, Run, RunState

LIVENESS_WINDOW = timedelta(seconds=30)


@dataclass(frozen=True)
class Runner:
    alive: bool
    last_heartbeat_at: datetime | None


def is_alive(heartbeat: datetime | None, server_time: datetime) -> bool:
    return heartbeat is not None and server_time - heartbeat <= LIVENESS_WINDOW


def runner_of(run: Run, latest_worker_heartbeat: datetime | None, server_time: datetime) -> Runner:
    """A queued run waits for any worker; a running run is held by one; a finished one by none."""
    if run.state is RunState.QUEUED:
        return Runner(is_alive(latest_worker_heartbeat, server_time), latest_worker_heartbeat)
    if run.state in FINISHED_STATES:
        return Runner(False, run.heartbeat_at)
    return Runner(is_alive(run.heartbeat_at, server_time), run.heartbeat_at)
