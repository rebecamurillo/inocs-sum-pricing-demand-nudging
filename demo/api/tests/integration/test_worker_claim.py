import threading

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.domain.runs import Run, RunKind, RunState, RunStep, StepName
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.runs import T0, later, make_run

pytestmark = pytest.mark.integration


def test_two_workers_claiming_at_once_never_take_the_same_run(migrated_database: Engine) -> None:
    repository = PostgresRunRepository(migrated_database)
    registry = PostgresWorkerRegistry(migrated_database)
    registry.register("w-1", "h", 1, T0)
    registry.register("w-2", "h", 2, T0)
    repository.add(make_run("a", queued_at=T0, subject_id="a.v1"))
    repository.add(make_run("b", queued_at=later(1), subject_id="b.v1"))
    barrier = threading.Barrier(2)
    claimed: dict[str, Run | None] = {}
    errors: list[BaseException] = []

    def claim(worker_id: str) -> None:
        try:
            barrier.wait(timeout=10)
            claimed[worker_id] = repository.claim_next(worker_id, later(5))
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=claim, args=(name,)) for name in ("w-1", "w-2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    first, second = claimed["w-1"], claimed["w-2"]
    assert first is not None
    assert second is not None
    assert {first.id, second.id} == {"a", "b"}
    for worker_id, run in (("w-1", first), ("w-2", second)):
        stored = repository.get(run.id)
        assert stored is not None
        assert (stored.state, stored.worker_id) == (RunState.RUNNING, worker_id)
        assert (stored.started_at, stored.heartbeat_at) == (later(5), later(5))
    assert repository.claim_next("w-1", later(6)) is None


class OneAtATime:
    """Records the order of the runs and fails when two steps overlap."""

    def __init__(self) -> None:
        self.order: list[str] = []
        self.active = 0
        self.overlap = False
        self._lock = threading.Lock()

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        with self._lock:
            self.active += 1
            self.overlap = self.overlap or self.active > 1
            self.order.append(run.id)
        with self._lock:
            self.active -= 1
        return StepOutcome.done({"rows": 1})


def test_one_worker_runs_the_queue_one_run_at_a_time_in_queue_order(
    migrated_database: Engine,
) -> None:
    repository = PostgresRunRepository(migrated_database)
    workers = PostgresWorkerRegistry(migrated_database)
    clock = FixedClock(T0)
    identity = WorkerIdentity("w-1", "h", 1, T0)
    workers.register("w-1", "h", 1, T0)
    executor = OneAtATime()
    steps = StepRegistry()
    steps.register(StepName.TRAVELLER_SIMULATION, executor)
    for run_id, queued_at in (("c", later(3)), ("a", later(1)), ("b", later(2))):
        repository.add(
            make_run(
                run_id,
                kind=RunKind.SIMULATION,
                subject_id=f"{run_id}.v1.A",
                queued_at=queued_at,
            )
        )
    process = ProcessNextRun(repository, steps, workers, identity, clock, FakeWaiter(clock))

    results = [process.execute() for _ in range(4)]

    assert results == [True, True, True, False]
    assert executor.order == ["a", "b", "c"]
    assert not executor.overlap
    for run_id in ("a", "b", "c"):
        stored = repository.get(run_id)
        assert stored is not None
        assert stored.state is RunState.SUCCEEDED
        assert stored.worker_id == "w-1"
