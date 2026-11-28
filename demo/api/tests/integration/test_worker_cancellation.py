import threading
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.instances import SeedingRunRepository
from tests.support.reporting import REPORT_EVERY, quiet_fingerprint, quiet_report
from tests.support.runs import T0, BlockingExecutor, RecordingExecutor, later, make_run, step

pytestmark = pytest.mark.integration


def test_a_cancellation_stops_the_executor_and_cancels_the_run_keeping_done_steps(
    migrated_database: Engine,
) -> None:
    repository = SeedingRunRepository(migrated_database)
    workers = PostgresWorkerRegistry(migrated_database)
    clock = FixedClock(T0)
    waiter = FakeWaiter(clock)
    identity = WorkerIdentity("w-1", "h", 1, T0)
    blocking = BlockingExecutor()
    log: list[str] = []
    steps = StepRegistry()
    steps.register(StepName.AREA, RecordingExecutor(log))
    steps.register(StepName.HUBS, blocking)
    process = ProcessNextRun(repository, steps, workers, identity, clock, waiter)
    worker = RunWorker(
        identity,
        workers,
        RecoverInterruptedRuns(repository, clock),
        process,
        quiet_report(clock),
        REPORT_EVERY,
        clock,
        waiter,
        quiet_fingerprint(clock),
    )
    repository.add(
        make_run(
            "r1",
            steps=(
                step(1, StepName.AREA),
                step(2, StepName.HUBS),
                step(3, StepName.ROUTES),
            ),
        )
    )
    cancel = CancelRun(repository, clock)
    until = threading.Event()

    def hook(now: datetime) -> None:
        if now == later(3):
            cancel.execute("r1")
        if now >= later(30):
            until.set()

    waiter.on_wait = hook
    worker.start()

    worker.run(until)

    run = repository.get("r1")
    assert run is not None
    assert log == ["r1:area"]
    assert blocking.stopped.is_set()
    assert run.state is RunState.CANCELLED
    assert run.cancel_requested_at == later(3)
    assert run.finished_at is not None
    assert run.finished_at - later(3) <= timedelta(seconds=2)
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]


def test_a_cancellation_and_a_concurrent_write_of_the_worker_both_survive(
    migrated_database: Engine,
) -> None:
    repository = SeedingRunRepository(migrated_database)
    PostgresWorkerRegistry(migrated_database).register("w-1", "h", 1, T0)
    repository.add(make_run("r1"))
    claimed = repository.claim_next("w-1", later(1))
    assert claimed is not None
    inside = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def worker_write(run: Run) -> Run:
        inside.set()
        release.wait(10)
        return replace(run, heartbeat_at=later(5))

    def write() -> None:
        try:
            repository.update("r1", worker_write)
        except BaseException as error:
            errors.append(error)

    def request() -> None:
        try:
            CancelRun(repository, FixedClock(later(6))).execute("r1")
        except BaseException as error:
            errors.append(error)

    writer = threading.Thread(target=write)
    writer.start()
    assert inside.wait(10)
    canceller = threading.Thread(target=request)
    canceller.start()
    release.set()
    writer.join(20)
    canceller.join(20)

    assert errors == []
    stored = repository.get("r1")
    assert stored is not None
    assert (stored.worker_id, stored.started_at) == ("w-1", later(1))
    assert stored.heartbeat_at == later(5)
    assert stored.cancel_requested_at == later(6)
