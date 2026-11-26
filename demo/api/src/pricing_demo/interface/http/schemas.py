from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pricing_demo.application.run_view import RunView
from pricing_demo.domain.runner_liveness import Runner
from pricing_demo.domain.runs import (
    STEP_NUMBERS,
    RunFailure,
    RunKind,
    RunState,
    RunStep,
    StepName,
    StepState,
    SubjectType,
)
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus


class ComponentStatusResponse(BaseModel):
    name: ComponentName
    available: bool
    reason: str | None

    @classmethod
    def from_domain(cls, status: ComponentStatus) -> "ComponentStatusResponse":
        return cls(name=status.name, available=status.available, reason=status.reason)


class SystemStatusResponse(BaseModel):
    api_version: str
    components: list[ComponentStatusResponse]
    can_read_stored_results: bool
    can_start_runs: bool

    @classmethod
    def from_domain(cls, status: SystemStatus, api_version: str) -> "SystemStatusResponse":
        return cls(
            api_version=api_version,
            components=[ComponentStatusResponse.from_domain(item) for item in status.components],
            can_read_stored_results=status.can_read_stored_results,
            can_start_runs=status.can_start_runs,
        )


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    """An error, as a problem document (RFC 9457)."""

    type: str
    title: str
    status: int
    detail: str
    code: str
    errors: list[FieldError] | None = None


class ComponentAnswerRequest(BaseModel):
    available: bool
    reason: str | None = None


class RunSubject(BaseModel):
    type: SubjectType
    id: str


class RunnerResource(BaseModel):
    """Whether the process that should work on the run reported within the last 30 s."""

    alive: bool
    last_heartbeat_at: datetime | None

    @classmethod
    def from_domain(cls, runner: Runner) -> "RunnerResource":
        return cls(alive=runner.alive, last_heartbeat_at=runner.last_heartbeat_at)


class StepProgress(BaseModel):
    done: int
    total: int


class RunStepResource(BaseModel):
    step: StepName
    number: int
    period: str | None
    state: StepState
    started_at: datetime | None
    finished_at: datetime | None
    counts: dict[str, Any]
    progress: StepProgress | None
    last_duration_s: float | None
    reason: str | None

    @classmethod
    def from_domain(cls, step: RunStep) -> "RunStepResource":
        has_progress = step.progress_done is not None and step.progress_total is not None
        return cls(
            step=step.step,
            number=STEP_NUMBERS[step.step],
            period=step.period,
            state=step.state,
            started_at=step.started_at,
            finished_at=step.finished_at,
            counts=dict(step.counts),
            progress=StepProgress(done=step.progress_done, total=step.progress_total)
            if has_progress
            else None,
            last_duration_s=None,
            reason=step.reason,
        )


class RunFailureResource(BaseModel):
    step: str | None
    code: str
    reason: str

    @classmethod
    def from_domain(cls, failure: RunFailure) -> "RunFailureResource":
        return cls(step=failure.step, code=failure.code, reason=failure.reason)


class RunResource(BaseModel):
    id: str
    kind: RunKind
    subject: RunSubject
    state: RunState
    attempt: int
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    server_time: datetime
    queue_position: int | None
    runner: RunnerResource
    steps: list[RunStepResource]
    failure: RunFailureResource | None
    failure_pct: float | None = Field(
        description="Share of failed trip-planner queries; null on every run that is not a build."
    )

    @classmethod
    def from_view(cls, view: RunView) -> "RunResource":
        run = view.run
        return cls(
            id=run.id,
            kind=run.kind,
            subject=RunSubject(type=run.subject.type, id=run.subject.id),
            state=run.state,
            attempt=run.attempt,
            queued_at=run.queued_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            server_time=view.server_time,
            queue_position=view.queue_position,
            runner=RunnerResource.from_domain(view.runner),
            steps=[RunStepResource.from_domain(item) for item in run.steps],
            failure=RunFailureResource.from_domain(run.failure) if run.failure else None,
            failure_pct=run.failure_pct if run.kind is RunKind.BUILD else None,
        )


class RunList(BaseModel):
    items: list[RunResource]
