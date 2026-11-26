"""The worker's periodic recovery: at its start and every 10 s of its loop, on the clock."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

import pytest

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.run_worker import RECOVERY_EVERY, RunWorker
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.fakes.worker_registry import InMemoryWorkerRegistry
from tests.support.reporting import REPORT_EVERY, quiet_report
from tests.support.runs import T0, GatedExecutor, RecordingExecutor, later, make_run, step


class Rig:
    def __init__(self, runs: InMemoryRunRepository | None = None) -> None:
        self.runs = runs or InMemoryRunRepository()
        self.workers = InMemoryWorkerRegistry()
        self.clock = FixedClock(T0)
        self.waiter = FakeWaiter(self.clock)
        self.registry = StepRegistry()
        self.until = threading.Event()
        self.identity = WorkerIdentity("w-2", "host-a", 4343, T0)
        self.worker = RunWorker(
            self.identity,
            self.workers,
            RecoverInterruptedRuns(self.runs, self.clock),
            ProcessNextRun(
                self.runs, self.registry, self.workers, self.identity, self.clock, self.waiter
            ),
            quiet_report(self.clock, "w-2"),
            REPORT_EVERY,
            self.clock,
            self.waiter,
        )
        self.hooks: list[Callable[[datetime], object]] = []
        self.waiter.on_wait = self._on_wait

    def _on_wait(self, now: datetime) -> None:
        for hook in self.hooks:
            hook(now)

    def stop_at(self, seconds: float) -> None:
        def hook(now: datetime) -> None:
            if now >= later(seconds):
                self.until.set()

        self.hooks.append(hook)

    def stored(self, run_id: str = "r1") -> Run:
        run = self.runs.get(run_id)
        assert run is not None
        return run


def left_running(
    run_id: str,
    *,
    heartbeat_at: datetime,
    attempt: int = 1,
    cancel_requested_at: datetime | None = None,
) -> Run:
    """A run its worker left running when it stopped: area done, hubs running, routes pending."""
    return make_run(
        run_id,
        subject_id=f"{run_id}.v1",
        state=RunState.RUNNING,
        attempt=attempt,
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


def test_the_recovery_cadence_is_ten_seconds() -> None:
    assert timedelta(seconds=10) == RECOVERY_EVERY


def test_i_a_worker_restarted_within_sixty_seconds_recovers_the_old_run_on_a_later_pass() -> None:
    rig = Rig()
    log: list[str] = []
    for name in (StepName.HUBS, StepName.ROUTES):
        rig.registry.register(name, RecordingExecutor(log))
    # The previous worker heartbeated 3 s before this one started.
    rig.runs.add(left_running("r1", heartbeat_at=later(-3)))
    seen: dict[int, RunState] = {}
    rig.hooks.append(
        lambda now: seen.setdefault(int((now - T0).total_seconds()), rig.stored().state)
    )
    rig.stop_at(80)

    rig.worker.start()
    assert rig.stored().state is RunState.RUNNING

    rig.worker.run(rig.until)

    # Passes at 0, 10, …, 50 find a heartbeat at most 53 s old; the pass at 60 finds it 63 s old.
    assert seen[57] is RunState.RUNNING
    run = rig.stored()
    assert run.state is RunState.SUCCEEDED
    assert run.attempt == 2
    assert run.worker_id == "w-2"
    assert run.steps[0].finished_at == T0
    assert log == ["r1:hubs", "r1:routes"]


def test_ii_the_run_in_hand_is_never_recovered_by_its_own_worker() -> None:
    class SilentHeartbeat(InMemoryRunRepository):
        """The run's heartbeat never lands, so its stored heartbeat stays at the claim."""

        def heartbeat_run(self, run_id: str, at: datetime) -> None:
            raise ConnectionError("the heartbeat is lost")

    rig = Rig(SilentHeartbeat())
    gate = GatedExecutor()
    rig.registry.register(StepName.AREA, gate)
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    states: list[RunState] = []

    def hook(now: datetime) -> None:
        states.append(rig.stored().state)
        if now >= later(100):
            gate.release.set()

    rig.hooks.append(hook)
    rig.stop_at(102)

    rig.worker.start()
    rig.worker.run(rig.until)

    assert set(states) == {RunState.RUNNING, RunState.SUCCEEDED}
    run = rig.stored()
    assert run.state is RunState.SUCCEEDED
    assert run.attempt == 1
    assert run.heartbeat_at == T0


def test_ii_recovery_skips_the_run_in_hand_by_its_id() -> None:
    runs = InMemoryRunRepository()
    runs.add(left_running("mine", heartbeat_at=T0))
    runs.add(left_running("other", heartbeat_at=T0))

    recovered = RecoverInterruptedRuns(runs, FixedClock(later(120))).execute(in_hand="mine")

    assert [run.id for run in recovered] == ["other"]
    mine = runs.get("mine")
    assert mine is not None
    assert mine.state is RunState.RUNNING


@pytest.mark.parametrize("attempt", [1, 2])
def test_iii_a_stale_run_with_a_cancellation_request_becomes_cancelled(attempt: int) -> None:
    rig = Rig()
    rig.clock.set(later(1000))
    rig.runs.add(
        left_running("r1", heartbeat_at=later(900), attempt=attempt, cancel_requested_at=later(920))
    )

    rig.worker.start()

    run = rig.stored()
    assert run.state is RunState.CANCELLED
    assert run.attempt == attempt
    assert run.finished_at == later(1000)
    assert run.failure is None
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]
    assert run.steps[0].finished_at == T0


class FailingEndOfStep(InMemoryRunRepository):
    """Every write that ends a step raises, `failures` times; the other writes succeed."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures_left = failures

    def update(self, run_id: str, change: Callable[[Run], Run]) -> Run:
        func = getattr(change, "func", None)
        if self.failures_left and getattr(func, "__name__", "") == "_end":
            self.failures_left -= 1
            raise ConnectionError("the database went away")
        return super().update(run_id, change)


def test_iv_a_failed_end_of_step_write_leads_to_a_requeue_on_a_later_pass(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig(FailingEndOfStep(failures=1))
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    seen: dict[int, Run] = {}
    rig.hooks.append(lambda now: seen.setdefault(int((now - T0).total_seconds()), rig.stored()))
    rig.stop_at(80)

    with caplog.at_level(logging.ERROR):
        rig.worker.start()
        rig.worker.run(rig.until)

    # Abandoned: its heartbeat stopped at the claim and it stays running until a pass finds
    # the heartbeat more than 60 s old (the pass at 70 s).
    assert seen[30].state is RunState.RUNNING
    assert seen[30].heartbeat_at == T0
    assert seen[69].state is RunState.RUNNING
    run = rig.stored()
    assert run.state is RunState.SUCCEEDED
    assert run.attempt == 2
    assert log == ["r1:area", "r1:area"]
    abandoned = [record for record in caplog.records if "could not be written" in record.message]
    assert len(abandoned) == 1
    assert "area" in abandoned[0].message
    assert "the database went away" in abandoned[0].message


def test_v_the_second_interruption_fails_the_run() -> None:
    rig = Rig(FailingEndOfStep(failures=2))
    log: list[str] = []
    rig.registry.register(StepName.AREA, RecordingExecutor(log))
    rig.runs.add(make_run("r1", steps=(step(1, StepName.AREA),)))
    rig.stop_at(160)

    rig.worker.start()
    rig.worker.run(rig.until)

    run = rig.stored()
    assert log == ["r1:area", "r1:area"]
    assert run.state is RunState.FAILED
    assert run.attempt == 2
    assert run.failure is not None
    assert run.failure.code == "interrupted"
    assert run.failure.reason == "The run was interrupted twice by a stop of the runner"
    assert run.failure.step == "area"
    assert run.steps[0].state is StepState.FAILED


def test_a_failed_recovery_pass_does_not_end_the_worker() -> None:
    class FlakyListing(InMemoryRunRepository):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def running_runs(self) -> list[Run]:
            self.calls += 1
            if self.calls == 2:
                raise ConnectionError("the database is restarting")
            return super().running_runs()

    rig = Rig(FlakyListing())
    rig.runs.add(left_running("r1", heartbeat_at=later(-3)))
    rig.stop_at(80)

    rig.worker.start()
    rig.worker.run(rig.until)

    # The pass at 10 s failed; a later one still recovered the run (no executor: stage_error).
    run = rig.stored()
    assert run.attempt == 2
    assert run.state is RunState.FAILED
    assert run.failure is not None
    assert run.failure.code == "stage_error"
