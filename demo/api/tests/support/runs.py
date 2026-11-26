"""Builders of stored runs, shared by the unit, contract and integration tests."""

import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.runs import (
    Run,
    RunKind,
    RunState,
    RunStep,
    StepName,
    StepState,
    Subject,
    SubjectType,
)

T0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=UTC)

BUILD_STEPS = (
    StepName.AREA,
    StepName.HUBS,
    StepName.ROUTES,
    StepName.TRAVELLERS_AND_BIKES,
)


def step(
    position: int,
    name: StepName,
    state: StepState = StepState.PENDING,
    **fields: object,
) -> RunStep:
    return replace(RunStep(position=position, step=name, state=state), **fields)  # type: ignore[arg-type]


def make_run(
    run_id: str,
    *,
    kind: RunKind = RunKind.BUILD,
    subject_id: str | None = None,
    state: RunState = RunState.QUEUED,
    queued_at: datetime = T0,
    steps: tuple[RunStep, ...] | None = None,
    **fields: object,
) -> Run:
    """A run of the given kind and state; a build gets the four build steps, pending."""
    if kind is RunKind.BUILD:
        subject = Subject(SubjectType.INSTANCE_VERSION, subject_id or "geneva-3km.v1")
        default_steps = tuple(step(n, name) for n, name in enumerate(BUILD_STEPS, start=1))
    else:
        subject = Subject(SubjectType.PRICING_VERSION, subject_id or "geneva-3km.v1.A")
        name = (
            StepName.TRAVELLER_SIMULATION if kind is RunKind.SIMULATION else StepName.PRICING_MODEL
        )
        default_steps = (step(1, name),)
    run = Run(
        id=run_id,
        kind=kind,
        subject=subject,
        state=state,
        queued_at=queued_at,
        steps=default_steps if steps is None else steps,
    )
    return replace(run, **fields)  # type: ignore[arg-type]


def later(seconds: float, base: datetime = T0) -> datetime:
    return base + timedelta(seconds=seconds)


class RecordingExecutor:
    """A step executor that records the steps it ran and answers done with fixed counts."""

    def __init__(self, log: list[str], counts: dict[str, int] | None = None) -> None:
        self._log = log
        self._counts = counts or {"rows": 1}

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        self._log.append(f"{run.id}:{step.step.value}")
        return StepOutcome.done(self._counts)


class FailingExecutor:
    def __init__(
        self, code: str = "otp_unreachable", reason: str = "The trip planner is down."
    ) -> None:
        self._code = code
        self._reason = reason

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        return StepOutcome.failed(self._code, self._reason)


class RaisingExecutor:
    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        raise RuntimeError("boom")


class BlockingExecutor:
    """Blocks until the worker's stop signal is set, then reports that it stopped."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        self.started.set()
        # The wait is bounded so that a broken test fails instead of hanging.
        deadline = time.monotonic() + 10
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.001)
        self.stopped.set()
        return StepOutcome.stopped_on_signal()


class GatedExecutor:
    """Blocks until `release` is set; used to hold a step open while the clock moves."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        self.release.wait(10)
        return StepOutcome.done({})
