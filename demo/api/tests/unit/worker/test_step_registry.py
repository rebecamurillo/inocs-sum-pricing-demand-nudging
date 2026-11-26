import pytest

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.domain.runs import RunFailure, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.fakes.worker_registry import InMemoryWorkerRegistry
from tests.support.runs import (
    T0,
    FailingExecutor,
    RaisingExecutor,
    RecordingExecutor,
    make_run,
    step,
)


class Rig:
    def __init__(self) -> None:
        self.runs = InMemoryRunRepository()
        self.workers = InMemoryWorkerRegistry()
        self.clock = FixedClock(T0)
        self.waiter = FakeWaiter(self.clock)
        self.registry = StepRegistry()
        identity = WorkerIdentity("w-1", "host", 7, T0)
        self.process = ProcessNextRun(
            self.runs, self.registry, self.workers, identity, self.clock, self.waiter
        )

    def stored(self, run_id: str = "r1"):  # type: ignore[no-untyped-def]
        run = self.runs.get(run_id)
        assert run is not None
        return run


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_a_registry_returns_the_executor_registered_for_a_step() -> None:
    registry = StepRegistry()
    executor = RecordingExecutor([])

    registry.register(StepName.AREA, executor)

    assert registry.executor_for(StepName.AREA) is executor
    assert registry.executor_for(StepName.HUBS) is None


def test_nothing_queued_means_nothing_done(rig: Rig) -> None:
    assert rig.process.execute() is False


def test_steps_run_in_position_order_and_the_run_succeeds(rig: Rig) -> None:
    log: list[str] = []
    for name in (StepName.AREA, StepName.HUBS, StepName.ROUTES, StepName.TRAVELLERS_AND_BIKES):
        rig.registry.register(name, RecordingExecutor(log, {"n": 2}))
    rig.runs.add(make_run("r1"))

    assert rig.process.execute() is True

    assert log == ["r1:area", "r1:hubs", "r1:routes", "r1:travellers_and_bikes"]
    run = rig.stored()
    assert run.state is RunState.SUCCEEDED
    assert run.finished_at is not None
    assert run.worker_id == "w-1"
    assert all(item.state is StepState.DONE for item in run.steps)
    assert all(item.counts == {"n": 2} for item in run.steps)
    assert all(item.started_at is not None and item.finished_at is not None for item in run.steps)


def test_a_failed_step_stops_the_run_and_later_steps_stay_pending(rig: Rig) -> None:
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.registry.register(
        StepName.HUBS, FailingExecutor("otp_unreachable", "The trip planner is down.")
    )
    rig.registry.register(StepName.ROUTES, RecordingExecutor(log))
    rig.runs.add(make_run("r1"))

    rig.process.execute()

    run = rig.stored()
    assert log == ["r1:area"]
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.FAILED,
        StepState.PENDING,
        StepState.PENDING,
    ]
    assert run.state is RunState.FAILED
    assert run.failure == RunFailure("hubs", "otp_unreachable", "The trip planner is down.")
    assert run.steps[1].reason == "The trip planner is down."
    assert run.finished_at is not None


def test_a_step_without_an_executor_fails_with_stage_error(rig: Rig) -> None:
    rig.runs.add(make_run("r1"))

    rig.process.execute()

    run = rig.stored()
    assert run.state is RunState.FAILED
    assert run.failure == RunFailure(
        "area", "stage_error", "no step executor is registered for area"
    )
    assert run.steps[0].state is StepState.FAILED


def test_an_executor_that_raises_fails_the_step_with_stage_error(rig: Rig) -> None:
    rig.registry.register(StepName.AREA, RaisingExecutor())
    rig.runs.add(make_run("r1"))

    rig.process.execute()

    run = rig.stored()
    assert run.state is RunState.FAILED
    assert run.failure == RunFailure("area", "stage_error", "RuntimeError: boom")


def test_done_and_kept_steps_are_skipped_and_the_rest_run(rig: Rig) -> None:
    log: list[str] = []
    rig.registry.register(StepName.ROUTES, RecordingExecutor(log))
    rig.registry.register(StepName.TRAVELLERS_AND_BIKES, RecordingExecutor(log))
    rig.runs.add(
        make_run(
            "r1",
            steps=(
                step(1, StepName.AREA, StepState.DONE),
                step(2, StepName.HUBS, StepState.KEPT),
                step(3, StepName.ROUTES),
                step(4, StepName.TRAVELLERS_AND_BIKES),
            ),
        )
    )

    rig.process.execute()

    assert log == ["r1:routes", "r1:travellers_and_bikes"]
    assert rig.stored().state is RunState.SUCCEEDED


def test_steps_are_run_in_position_order_whatever_the_stored_order(rig: Rig) -> None:
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.registry.register(StepName.HUBS, RecordingExecutor(log))
    rig.runs.add(make_run("r1", steps=(step(2, StepName.HUBS), step(1, StepName.AREA))))

    rig.process.execute()

    assert log == ["r1:area", "r1:hubs"]


def test_runs_are_taken_in_queue_order_one_after_the_other(rig: Rig) -> None:
    log: list[str] = []
    rig.registry.register(StepName.TRAVELLER_SIMULATION, RecordingExecutor(log))
    from pricing_demo.domain.runs import RunKind

    rig.runs.add(
        make_run("b", kind=RunKind.SIMULATION, queued_at=T0.replace(second=2), subject_id="b.A")
    )
    rig.runs.add(
        make_run("a", kind=RunKind.SIMULATION, queued_at=T0.replace(second=1), subject_id="a.A")
    )

    assert rig.process.execute() is True
    assert rig.stored("b").state is RunState.QUEUED
    assert rig.process.execute() is True
    assert rig.process.execute() is False

    assert log == ["a:traveller_simulation", "b:traveller_simulation"]


def test_a_run_with_no_step_left_to_do_succeeds(rig: Rig) -> None:
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA, StepState.KEPT),)))

    rig.process.execute()

    assert rig.stored().state is RunState.SUCCEEDED
