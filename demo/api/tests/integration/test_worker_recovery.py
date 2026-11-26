"""The periodic recovery through PostgreSQL: the listing of running runs and the locked update."""

import threading
from datetime import datetime

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.reporting import REPORT_EVERY, quiet_report
from tests.support.runs import T0, RecordingExecutor, later, make_run, step

pytestmark = pytest.mark.integration


def left_running(
    run_id: str, heartbeat_at: datetime, cancel_requested_at: datetime | None = None
) -> Run:
    return make_run(
        run_id,
        subject_id=f"{run_id}.v1",
        state=RunState.RUNNING,
        started_at=heartbeat_at,
        worker_id="old-worker",
        heartbeat_at=heartbeat_at,
        steps=(
            step(1, StepName.AREA, StepState.DONE, started_at=T0, finished_at=T0),
            step(2, StepName.HUBS, StepState.RUNNING, started_at=T0),
            step(3, StepName.ROUTES),
        ),
        cancel_requested_at=cancel_requested_at,
    )


@pytest.fixture
def repository(migrated_database: Engine) -> PostgresRunRepository:
    PostgresWorkerRegistry(migrated_database).register("old-worker", "h", 1, T0)
    return PostgresRunRepository(migrated_database)


def stored(repository: PostgresRunRepository, run_id: str) -> Run:
    run = repository.get(run_id)
    assert run is not None
    return run


def test_recovery_skips_the_run_in_hand_and_cancels_a_stale_cancelled_run(
    repository: PostgresRunRepository,
) -> None:
    repository.add(left_running("in-hand", T0))
    repository.add(left_running("stale", T0))
    repository.add(left_running("asked", T0, cancel_requested_at=later(10)))
    repository.add(left_running("fresh", later(100)))

    recovered = RecoverInterruptedRuns(repository, FixedClock(later(120))).execute(
        in_hand="in-hand"
    )

    assert sorted(run.id for run in recovered) == ["asked", "stale"]
    assert stored(repository, "in-hand").state is RunState.RUNNING
    assert stored(repository, "fresh").state is RunState.RUNNING
    stale = stored(repository, "stale")
    assert (stale.state, stale.attempt) == (RunState.QUEUED, 2)
    asked = stored(repository, "asked")
    assert asked.state is RunState.CANCELLED
    assert asked.finished_at == later(120)
    assert [item.state for item in asked.steps] == [
        StepState.DONE,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]


def test_a_worker_restarted_within_sixty_seconds_recovers_the_old_run_on_a_later_pass(
    migrated_database: Engine, repository: PostgresRunRepository
) -> None:
    workers = PostgresWorkerRegistry(migrated_database)
    clock = FixedClock(T0)
    waiter = FakeWaiter(clock)
    identity = WorkerIdentity("w-2", "h", 2, T0)
    log: list[str] = []
    steps = StepRegistry()
    for name in (StepName.HUBS, StepName.ROUTES):
        steps.register(name, RecordingExecutor(log))
    worker = RunWorker(
        identity,
        workers,
        RecoverInterruptedRuns(repository, clock),
        ProcessNextRun(repository, steps, workers, identity, clock, waiter),
        quiet_report(clock),
        REPORT_EVERY,
        clock,
        waiter,
    )
    repository.add(left_running("r1", later(-3)))
    until = threading.Event()
    seen: dict[int, RunState] = {}

    def hook(now: datetime) -> None:
        seen.setdefault(int((now - T0).total_seconds()), stored(repository, "r1").state)
        if now >= later(80):
            until.set()

    waiter.on_wait = hook

    worker.start()
    assert stored(repository, "r1").state is RunState.RUNNING
    worker.run(until)

    assert seen[57] is RunState.RUNNING
    run = stored(repository, "r1")
    assert run.state is RunState.SUCCEEDED
    assert (run.attempt, run.worker_id) == (2, "w-2")
    assert log == ["r1:hubs", "r1:routes"]
