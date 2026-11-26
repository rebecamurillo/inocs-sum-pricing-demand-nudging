"""Builders of stored runs, shared by the unit, contract and integration tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
