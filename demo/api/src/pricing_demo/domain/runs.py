"""Runs: the stored form of every long piece of work, and the rules of their states."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from pricing_demo.domain.errors import DomainError


class RunKind(StrEnum):
    BUILD = "build"
    PRICING = "pricing"
    SIMULATION = "simulation"


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepName(StrEnum):
    AREA = "area"
    HUBS = "hubs"
    ROUTES = "routes"
    TRAVELLERS_AND_BIKES = "travellers_and_bikes"
    PRICING_MODEL = "pricing_model"
    TRAVELLER_SIMULATION = "traveller_simulation"


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    KEPT = "kept"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubjectType(StrEnum):
    INSTANCE_VERSION = "instance_version"
    PRICING_VERSION = "pricing_version"


# The pipeline number of each step; the simulation shares number 5 with the pricing model.
STEP_NUMBERS: Mapping[StepName, int] = {
    StepName.AREA: 1,
    StepName.HUBS: 2,
    StepName.ROUTES: 3,
    StepName.TRAVELLERS_AND_BIKES: 4,
    StepName.PRICING_MODEL: 5,
    StepName.TRAVELLER_SIMULATION: 5,
}


class InvalidRunTransition(DomainError):
    pass


class InvalidStepTransition(DomainError):
    pass


class RunNotFound(DomainError):
    pass


class RunAlreadyFinished(DomainError):
    pass


@dataclass(frozen=True)
class Subject:
    """What a run works on: an instance version for a build, a pricing version otherwise."""

    type: SubjectType
    id: str


@dataclass(frozen=True)
class RunFailure:
    step: str | None
    code: str
    reason: str


@dataclass(frozen=True)
class RunStep:
    position: int
    step: StepName
    state: StepState = StepState.PENDING
    period: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: Mapping[str, Any] = field(default_factory=dict)
    progress_done: int | None = None
    progress_total: int | None = None
    reason: str | None = None
    input_key: str | None = None
    peak_rss_bytes: int | None = None
    log_excerpt: str | None = None


@dataclass(frozen=True)
class Run:
    id: str
    kind: RunKind
    subject: Subject
    state: RunState
    queued_at: datetime
    attempt: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    worker_id: str | None = None
    child_pid: int | None = None
    cancel_requested_at: datetime | None = None
    failure: RunFailure | None = None
    failure_pct: float | None = None
    steps: tuple[RunStep, ...] = ()


ALLOWED_RUN_TRANSITIONS = frozenset(
    {
        (RunState.QUEUED, RunState.RUNNING),
        (RunState.QUEUED, RunState.CANCELLED),
        (RunState.RUNNING, RunState.SUCCEEDED),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.RUNNING, RunState.CANCELLED),
    }
)

ALLOWED_STEP_TRANSITIONS = frozenset(
    {
        (StepState.PENDING, StepState.RUNNING),
        (StepState.PENDING, StepState.KEPT),
        (StepState.PENDING, StepState.CANCELLED),
        (StepState.RUNNING, StepState.DONE),
        (StepState.RUNNING, StepState.FAILED),
        (StepState.RUNNING, StepState.CANCELLED),
    }
)

FINISHED_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})


def ensure_run_transition(origin: RunState, target: RunState) -> None:
    """Refuse a move the state machine does not have. Running to queued is never one of them."""
    if (origin, target) not in ALLOWED_RUN_TRANSITIONS:
        raise InvalidRunTransition(f"A run cannot move from {origin.value} to {target.value}.")


def start(run: Run, at: datetime, worker_id: str) -> Run:
    ensure_run_transition(run.state, RunState.RUNNING)
    return replace(run, state=RunState.RUNNING, started_at=at, heartbeat_at=at, worker_id=worker_id)


def succeed(run: Run, at: datetime) -> Run:
    ensure_run_transition(run.state, RunState.SUCCEEDED)
    return replace(run, state=RunState.SUCCEEDED, finished_at=at)


def fail(run: Run, at: datetime, failure: RunFailure) -> Run:
    ensure_run_transition(run.state, RunState.FAILED)
    return replace(run, state=RunState.FAILED, finished_at=at, failure=failure)


def cancel(run: Run, at: datetime) -> Run:
    ensure_run_transition(run.state, RunState.CANCELLED)
    return replace(run, state=RunState.CANCELLED, finished_at=at)


def cancel_queued(run: Run, at: datetime) -> Run:
    """Cancel a run no worker has taken: it ends at once, and its pending steps with it."""
    if run.state is not RunState.QUEUED:
        raise InvalidRunTransition(f"A {run.state.value} run is not a queued run.")
    steps = tuple(
        replace(item, state=StepState.CANCELLED) if item.state is StepState.PENDING else item
        for item in run.steps
    )
    return replace(cancel(run, at), steps=steps)


def cancel_running(run: Run, at: datetime) -> Run:
    """End a running run the person asked to stop: the step it was in and the steps after it
    are cancelled, the steps already done or kept stay as they are."""
    if run.state is not RunState.RUNNING:
        raise InvalidRunTransition(f"A {run.state.value} run is not a running run.")
    cancelled = cancel(run, at)
    steps = tuple(
        transition_step(item, StepState.CANCELLED, at)
        if item.state is StepState.RUNNING
        else replace(item, state=StepState.CANCELLED)
        if item.state is StepState.PENDING
        else item
        for item in run.steps
    )
    return replace(cancelled, steps=steps)


def all_steps_complete(run: Run) -> bool:
    """True when every step is done or kept, so the run can succeed."""
    return all(item.state in (StepState.DONE, StepState.KEPT) for item in run.steps)


def request_cancellation(run: Run, at: datetime) -> Run:
    """Record that the person asked to cancel a running run; the first request stays."""
    if run.state is not RunState.RUNNING:
        raise InvalidRunTransition(
            f"A cancellation is requested of a running run, not a {run.state.value} one."
        )
    if run.cancel_requested_at is not None:
        return run
    return replace(run, cancel_requested_at=at)


def requeue_after_interruption(run: Run) -> Run:
    """The restart rule: a running run whose worker died goes back to the queue.

    It is the only way from running to queued. The steps that were running start again, with
    their times, progress and reason cleared; `queued_at` stays, so the run keeps its place.
    """
    if run.state is not RunState.RUNNING:
        raise InvalidRunTransition(
            f"Only a running run can be queued again, not a {run.state.value} one."
        )
    steps = tuple(
        replace(
            item,
            state=StepState.PENDING,
            started_at=None,
            finished_at=None,
            progress_done=None,
            progress_total=None,
            reason=None,
        )
        if item.state is StepState.RUNNING
        else item
        for item in run.steps
    )
    return replace(
        run,
        state=RunState.QUEUED,
        attempt=run.attempt + 1,
        started_at=None,
        heartbeat_at=None,
        worker_id=None,
        child_pid=None,
        steps=steps,
    )


def transition_step(step: RunStep, target: StepState, at: datetime) -> RunStep:
    if (step.state, target) not in ALLOWED_STEP_TRANSITIONS:
        raise InvalidStepTransition(
            f"Step {step.step.value} cannot move from {step.state.value} to {target.value}."
        )
    if target is StepState.RUNNING:
        return replace(step, state=target, started_at=at)
    return replace(step, state=target, finished_at=at)


def queue_positions(runs: Iterable[Run]) -> dict[str, int]:
    """The 1-based rank of each queued run among the queued runs, by queue time."""
    queued = sorted(
        (run for run in runs if run.state is RunState.QUEUED),
        key=lambda run: (run.queued_at, run.id),
    )
    return {run.id: rank for rank, run in enumerate(queued, start=1)}
