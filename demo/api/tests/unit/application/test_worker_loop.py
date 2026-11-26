import threading
from datetime import datetime, timedelta

import pytest

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.fakes.worker_registry import InMemoryWorkerRegistry
from tests.support.runs import (
    T0,
    BlockingExecutor,
    GatedExecutor,
    RecordingExecutor,
    later,
    make_run,
    step,
)


class Rig:
    def __init__(self, runs: InMemoryRunRepository | None = None) -> None:
        self.runs = runs or InMemoryRunRepository()
        self.workers = InMemoryWorkerRegistry()
        self.clock = FixedClock(T0)
        self.waiter = FakeWaiter(self.clock)
        self.registry = StepRegistry()
        self.until = threading.Event()
        self.identity = WorkerIdentity("w-1", "host-a", 4242, T0)
        self.process = ProcessNextRun(
            self.runs, self.registry, self.workers, self.identity, self.clock, self.waiter
        )
        self.worker = RunWorker(
            self.identity,
            self.workers,
            RecoverInterruptedRuns(self.runs, self.clock),
            self.process,
            self.clock,
            self.waiter,
        )

    def stop_at(self, seconds: float) -> None:
        previous = self.waiter.on_wait

        def hook(now: datetime) -> None:
            if previous is not None:
                previous(now)
            if now >= later(seconds):
                self.until.set()

        self.waiter.on_wait = hook

    def stored(self, run_id: str = "r1") -> Run:
        run = self.runs.get(run_id)
        assert run is not None
        return run


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_starting_registers_the_worker_at_the_time_of_the_clock(rig: Rig) -> None:
    rig.worker.start()

    row = rig.workers.rows["w-1"]
    assert (row.host, row.pid, row.started_at, row.heartbeat_at) == ("host-a", 4242, T0, T0)


def test_an_idle_worker_polls_every_second_and_heartbeats_every_five(rig: Rig) -> None:
    rig.worker.start()
    rig.stop_at(11)

    rig.worker.run(rig.until)

    assert rig.waiter.calls == 11
    assert rig.clock.now() == later(11)
    row = rig.workers.rows["w-1"]
    assert (row.started_at, row.heartbeat_at) == (T0, later(10))


def test_the_worker_row_is_created_again_by_the_next_heartbeat(rig: Rig) -> None:
    rig.worker.start()
    rig.workers.delete("w-1")
    rig.stop_at(6)

    rig.worker.run(rig.until)

    assert rig.workers.rows["w-1"].heartbeat_at == later(5)


def test_a_worker_told_to_stop_before_it_starts_polling_claims_nothing(rig: Rig) -> None:
    rig.runs.add(make_run("r1"))
    rig.until.set()

    rig.worker.run(rig.until)

    assert rig.stored().state is RunState.QUEUED
    assert rig.waiter.calls == 0


def test_a_running_run_and_its_worker_heartbeat_every_five_seconds(rig: Rig) -> None:
    gate = GatedExecutor()
    rig.registry.register(StepName.AREA, gate)
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    seen: dict[float, datetime | None] = {}

    def hook(now: datetime) -> None:
        run = rig.runs.get("r1")
        assert run is not None
        seen[(now - T0).total_seconds()] = run.heartbeat_at
        if now >= later(12):
            gate.release.set()

    rig.waiter.on_wait = hook
    rig.worker.start()
    rig.stop_at(14)

    rig.worker.run(rig.until)

    # The hook sees the stored run right after the clock moved, before the tick of that
    # second: the heartbeat of second 5 is visible at second 6.
    assert seen[5] == T0
    assert seen[6] == later(5)
    assert seen[10] == later(5)
    assert seen[11] == later(10)
    assert rig.stored().state is RunState.SUCCEEDED
    assert rig.stored().heartbeat_at == later(10)
    assert rig.workers.rows["w-1"].heartbeat_at >= later(10)


def test_a_worker_told_to_stop_leaves_the_running_run_as_it_is(rig: Rig) -> None:
    blocking = BlockingExecutor()
    rig.registry.register(StepName.AREA, blocking)
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    rig.worker.start()
    rig.stop_at(3)

    rig.worker.run(rig.until)

    assert blocking.stopped.is_set()
    run = rig.stored()
    assert run.state is RunState.RUNNING
    assert run.steps[0].state is StepState.RUNNING
    assert run.worker_id == "w-1"


def test_a_cancellation_stops_the_running_executor_within_one_check(rig: Rig) -> None:
    blocking = BlockingExecutor()
    rig.registry.register(StepName.AREA, blocking)
    rig.runs.add(
        make_run(
            "r1",
            steps=(
                step(1, StepName.AREA),
                step(2, StepName.HUBS),
            ),
        )
    )
    cancel = CancelRun(rig.runs, rig.clock)

    def hook(now: datetime) -> None:
        if now == later(3):
            cancel.execute("r1")

    rig.waiter.on_wait = hook
    rig.worker.start()
    rig.stop_at(30)

    rig.worker.run(rig.until)

    run = rig.stored()
    assert blocking.stopped.is_set()
    assert run.state is RunState.CANCELLED
    assert run.cancel_requested_at == later(3)
    assert run.finished_at is not None
    assert run.finished_at - run.cancel_requested_at <= timedelta(seconds=2)
    assert [item.state for item in run.steps] == [StepState.CANCELLED, StepState.CANCELLED]


def test_a_cancellation_keeps_the_steps_that_are_done(rig: Rig) -> None:
    log: list[str] = []
    blocking = BlockingExecutor()
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.registry.register(StepName.HUBS, blocking)
    rig.runs.add(
        make_run(
            "r1",
            steps=(
                step(1, StepName.AREA),
                step(2, StepName.HUBS),
                step(3, StepName.ROUTES),
            ),
        )
    )
    cancel = CancelRun(rig.runs, rig.clock)

    def hook(now: datetime) -> None:
        if blocking.started.is_set() and rig.stored().cancel_requested_at is None:
            cancel.execute("r1")

    rig.waiter.on_wait = hook
    rig.worker.start()
    rig.stop_at(30)

    rig.worker.run(rig.until)

    run = rig.stored()
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]
    assert run.state is RunState.CANCELLED


def test_a_cancellation_requested_before_a_step_starts_runs_no_further_step(rig: Rig) -> None:
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.runs.add(make_run("r1", cancel_requested_at=T0))

    rig.process.execute()

    run = rig.stored()
    assert log == []
    assert run.state is RunState.CANCELLED
    assert all(item.state is StepState.CANCELLED for item in run.steps)


def test_a_database_error_does_not_end_the_worker() -> None:
    class FlakyRepository(InMemoryRunRepository):
        def __init__(self) -> None:
            super().__init__()
            self.failures_left = 1

        def claim_next(self, worker_id: str, at: datetime) -> Run | None:
            if self.failures_left:
                self.failures_left -= 1
                raise ConnectionError("the database is restarting")
            return super().claim_next(worker_id, at)

    rig = Rig(FlakyRepository())
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    rig.worker.start()
    rig.stop_at(3)

    rig.worker.run(rig.until)

    assert log == ["r1:area"]
    assert rig.stored().state is RunState.SUCCEEDED


def stale_run(
    run_id: str, *, heartbeat_age: float, attempt: int = 1, kind: RunKind = RunKind.BUILD
) -> Run:
    return make_run(
        run_id,
        kind=kind,
        subject_id=f"{run_id}.v1",
        state=RunState.RUNNING,
        attempt=attempt,
        started_at=T0,
        worker_id="old-worker",
        heartbeat_at=later(1000 - heartbeat_age),
        steps=(
            step(1, StepName.AREA, StepState.DONE, started_at=T0, finished_at=later(5)),
            step(2, StepName.HUBS, StepState.RUNNING, started_at=later(5)),
            step(3, StepName.ROUTES),
        ),
    )


def test_recovery_queues_a_stale_run_again_and_leaves_a_fresh_one(rig: Rig) -> None:
    rig.clock.set(later(1000))
    rig.runs.add(stale_run("stale", heartbeat_age=61))
    rig.runs.add(stale_run("fresh", heartbeat_age=59))
    rig.runs.add(stale_run("edge", heartbeat_age=60))

    recovered = RecoverInterruptedRuns(rig.runs, rig.clock).execute()

    assert [run.id for run in recovered] == ["stale"]
    stale = rig.stored("stale")
    assert (stale.state, stale.attempt, stale.worker_id) == (RunState.QUEUED, 2, None)
    assert [item.state for item in stale.steps] == [
        StepState.DONE,
        StepState.PENDING,
        StepState.PENDING,
    ]
    assert rig.stored("fresh").state is RunState.RUNNING
    assert rig.stored("edge").state is RunState.RUNNING


def test_recovery_fails_a_run_found_stale_on_its_second_attempt(rig: Rig) -> None:
    rig.clock.set(later(1000))
    rig.runs.add(stale_run("r1", heartbeat_age=61, attempt=2))

    RecoverInterruptedRuns(rig.runs, rig.clock).execute()

    run = rig.stored("r1")
    assert run.state is RunState.FAILED
    assert run.failure is not None
    assert (run.failure.code, run.failure.step) == ("interrupted", "hubs")


def test_a_heartbeat_that_arrives_during_recovery_wins() -> None:
    class StaleSnapshot(InMemoryRunRepository):
        """Lists the run as it was before its worker's last heartbeat landed."""

        def __init__(self, snapshot: Run) -> None:
            super().__init__()
            self._snapshot = snapshot

        def running_runs(self) -> list[Run]:
            return [self._snapshot]

    snapshot = stale_run("r1", heartbeat_age=61)
    repository = StaleSnapshot(snapshot)
    repository.add(stale_run("r1", heartbeat_age=1))

    recovered = RecoverInterruptedRuns(repository, FixedClock(later(1000))).execute()

    assert recovered == []
    stored = repository.get("r1")
    assert stored is not None
    assert stored.state is RunState.RUNNING


def test_the_worker_recovers_interrupted_runs_when_it_starts(rig: Rig) -> None:
    rig.clock.set(later(1000))
    rig.runs.add(stale_run("r1", heartbeat_age=120))

    rig.worker.start()

    assert rig.stored("r1").state is RunState.QUEUED


def test_after_a_reset_deleted_the_worker_row_the_worker_writes_it_before_claiming() -> None:
    workers = InMemoryWorkerRegistry()

    class ForeignKeyRepository(InMemoryRunRepository):
        """A claim names the worker: like PostgreSQL, refuse it when the row is missing."""

        def claim_next(self, worker_id: str, at: datetime) -> Run | None:
            if worker_id not in workers.rows:
                raise LookupError("runs.worker_id references a missing workers row")
            return super().claim_next(worker_id, at)

    rig = Rig(ForeignKeyRepository())
    rig.workers = workers
    rig.process = ProcessNextRun(
        rig.runs, rig.registry, workers, rig.identity, rig.clock, rig.waiter
    )
    rig.worker = RunWorker(
        rig.identity,
        workers,
        RecoverInterruptedRuns(rig.runs, rig.clock),
        rig.process,
        rig.clock,
        rig.waiter,
    )
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.worker.start()
    workers.delete("w-1")
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    rig.stop_at(3)

    rig.worker.run(rig.until)

    assert log == ["r1:area"]
    assert rig.stored().state is RunState.SUCCEEDED
    assert "w-1" in workers.rows


def test_a_failed_heartbeat_does_not_abandon_the_running_step() -> None:
    class FlakyHeartbeatRepository(InMemoryRunRepository):
        def __init__(self) -> None:
            super().__init__()
            self.failures_left = 1

        def heartbeat_run(self, run_id: str, at: datetime) -> None:
            if self.failures_left:
                self.failures_left -= 1
                raise ConnectionError("the database is restarting")
            super().heartbeat_run(run_id, at)

    rig = Rig(FlakyHeartbeatRepository())
    gate = GatedExecutor()
    rig.registry.register(StepName.AREA, gate)
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))

    def hook(now: datetime) -> None:
        if now >= later(8):
            gate.release.set()

    rig.waiter.on_wait = hook
    rig.worker.start()
    rig.stop_at(14)

    rig.worker.run(rig.until)

    run = rig.stored()
    assert run.state is RunState.SUCCEEDED
    assert run.steps[0].state is StepState.DONE
    # The heartbeat that failed at second 5 is tried again at the next tick.
    assert run.heartbeat_at == later(6)


def test_a_step_that_ends_as_the_worker_is_told_to_stop_keeps_its_outcome(rig: Rig) -> None:
    gate = GatedExecutor()
    rig.registry.register(StepName.AREA, gate)
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))

    def hook(now: datetime) -> None:
        if now >= later(3):
            gate.release.set()
            rig.until.set()

    rig.waiter.on_wait = hook
    rig.worker.start()

    rig.worker.run(rig.until)

    run = rig.stored()
    assert run.steps[0].state is StepState.DONE
    assert run.state is RunState.SUCCEEDED
