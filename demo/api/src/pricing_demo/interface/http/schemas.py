from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field

from pricing_demo.application.run_view import RunView
from pricing_demo.domain.city_datasets import CityDataset
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
from pricing_demo.domain.system_status import (
    BlockingReason,
    ComponentName,
    ComponentState,
    ComponentStatus,
    SystemStatus,
    Verdict,
)


class ComponentStatusResponse(BaseModel):
    name: ComponentName
    state: ComponentState
    reason: str | None

    @classmethod
    def from_domain(cls, status: ComponentStatus) -> "ComponentStatusResponse":
        return cls(name=status.name, state=status.state, reason=status.reason)


class BlockingReasonResponse(BaseModel):
    """The component that blocks an action, with that component's own reason."""

    component: ComponentName
    reason: str

    @classmethod
    def from_domain(cls, blocking: BlockingReason) -> "BlockingReasonResponse":
        return cls(component=blocking.component, reason=blocking.reason)


class VerdictResponse(BaseModel):
    allowed: bool
    reasons: list[BlockingReasonResponse]

    @classmethod
    def from_domain(cls, verdict: Verdict) -> "VerdictResponse":
        return cls(
            allowed=verdict.allowed,
            reasons=[BlockingReasonResponse.from_domain(item) for item in verdict.reasons],
        )


class SystemStatusResponse(BaseModel):
    components: list[ComponentStatusResponse]
    can_build_instances: VerdictResponse
    can_run_pricing: VerdictResponse
    can_simulate: VerdictResponse

    @classmethod
    def from_domain(cls, status: SystemStatus) -> "SystemStatusResponse":
        return cls(
            components=[ComponentStatusResponse.from_domain(item) for item in status.components],
            can_build_instances=VerdictResponse.from_domain(status.can_build_instances),
            can_run_pricing=VerdictResponse.from_domain(status.can_run_pricing),
            can_simulate=VerdictResponse.from_domain(status.can_simulate),
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
    state: ComponentState
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


class PolygonResource(BaseModel):
    """A GeoJSON polygon: one closed ring of [longitude, latitude] positions."""

    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]


class PresetResource(BaseModel):
    centre_lat: float
    centre_lon: float
    radius_m: int


class RoutingMomentResource(BaseModel):
    date: date
    time: time
    arrive_by: bool
    provisional: bool


class CityDatasetResource(BaseModel):
    id: str
    name: str
    gtfs_valid_from: date
    gtfs_valid_to: date
    gtfs_timezone: str
    gbfs_fetched_at: datetime
    available_area: PolygonResource
    preset: PresetResource
    routing_moment: RoutingMomentResource
    bus_shapes: Literal["generated", "none"]
    bus_shapes_reason: str | None
    shape_tool_image: str | None

    @classmethod
    def from_domain(cls, dataset: CityDataset) -> "CityDatasetResource":
        moment = dataset.routing_moment
        preset = dataset.preset
        return cls(
            id=dataset.id,
            name=dataset.name,
            gtfs_valid_from=dataset.gtfs.valid_from,
            gtfs_valid_to=dataset.gtfs.valid_to,
            gtfs_timezone=dataset.gtfs.timezone,
            gbfs_fetched_at=dataset.gbfs.fetched_at,
            available_area=PolygonResource.model_validate(
                dataset.available_area.to_geojson_polygon()
            ),
            preset=PresetResource(
                centre_lat=preset.centre_lat,
                centre_lon=preset.centre_lon,
                radius_m=preset.radius_m,
            ),
            routing_moment=RoutingMomentResource(
                date=moment.date,
                time=moment.time,
                arrive_by=moment.arrive_by,
                provisional=moment.provisional,
            ),
            bus_shapes=dataset.bus_shapes.status,
            bus_shapes_reason=dataset.bus_shapes.reason,
            shape_tool_image=dataset.bus_shapes.tool_image,
        )


class CityDatasetList(BaseModel):
    items: list[CityDatasetResource]


class CreatedCityDataset(BaseModel):
    """What the e2e suite gets back from inserting a fake city data set."""

    id: str
