from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from pricing_demo.application.instance_version_view import InstanceVersionView
from pricing_demo.application.run_view import RunView
from pricing_demo.application.use_cases.list_city_instances import InstanceMenuEntry
from pricing_demo.domain.build_plan import BUILD_STEPS, BuildPlan, Cause, PlannedStep
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import (
    PARAMETER_NAMES,
    InstancePeriod,
    Number,
    ParameterChange,
)
from pricing_demo.domain.failure_codes import FAILURE_CODES
from pricing_demo.domain.instance_rules import RuleResult, RuleValue
from pricing_demo.domain.numbers import Number as DomainNumber
from pricing_demo.domain.read_model import (
    HubPairRow,
    HubRow,
    RouteFailure,
    RoutePairRow,
    RoutesSummary,
    StationRow,
)
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


class ComponentAnswerRequest(BaseModel):
    state: ComponentState
    reason: str | None = None


def _a_build_step(value: StepName | None) -> StepName | None:
    """The fake pricing model only plays the four build steps: another step would be accepted
    and never acted on, so a test naming it would silently run the happy path."""
    if value is not None and value not in BUILD_STEPS:
        raise ValueError(f"must be one of {', '.join(item.value for item in BUILD_STEPS)}")
    return value


class FailAt(BaseModel):
    step: StepName
    code: str

    _step_is_a_build_step = field_validator("step")(_a_build_step)

    @field_validator("code")
    @classmethod
    def _is_a_failure_code(cls, value: str) -> str:
        if value not in FAILURE_CODES:
            raise ValueError(f"must be one of {', '.join(FAILURE_CODES)}")
        return value


class FakeRouteFailure(BaseModel):
    """One failed trip-planner query of the fake city: the pair, the query, how it failed."""

    origin_hub: str
    destination_hub: str
    query: Literal["pt_bike", "car"]
    kind: Literal["technical", "no_route"]
    message: str


class PricingModelSettings(BaseModel):
    """What the fake pricing model does: fail a step with a code, hold a step until it is
    released, pace the routes step, and fail trip-planner queries at named pairs. The defaults
    are no failure, no hold, no pace and no failed query."""

    fail_at: FailAt | None = None
    hold_at: StepName | None = None
    routes_pace_ms: int = Field(default=0, ge=0)
    route_failures: list[FakeRouteFailure] = Field(default_factory=list)

    _hold_is_a_build_step = field_validator("hold_at")(_a_build_step)


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


class PackageDefaultsStart(BaseModel):
    kind: Literal["package_defaults"]


class CopyStart(BaseModel):
    kind: Literal["copy"]
    instance_version_id: str


class CreateCityInstanceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: str
    start_from: Annotated[PackageDefaultsStart | CopyStart, Field(discriminator="kind")]


class CreateInstanceVersionRequest(BaseModel):
    based_on_id: str


# A JSON number: a string or a boolean is refused, and so are NaN and infinity. An integer
# is held to what a double stores exactly (the columns are doubles), so it is kept as sent.
EXACT_INTEGER = 2**53
ParameterNumber = (
    Annotated[StrictInt, Field(ge=-EXACT_INTEGER, le=EXACT_INTEGER)]
    | Annotated[float, Field(strict=True, allow_inf_nan=False)]
)


# Every field is optional, yet `null` is not a number: the default is never read, because
# `changes()` looks at the fields the request set, and a default factory keeps it out of the
# contract.
_UNSET: Any = Field(default_factory=float)


class InstanceVersionPatch(BaseModel):
    """Any subset of the parameters. A value is stored as sent: a rule it breaks is reported
    in the answer, never corrected."""

    model_config = ConfigDict(extra="forbid")

    center_lat: ParameterNumber = _UNSET
    center_lon: ParameterNumber = _UNSET
    radius_m: ParameterNumber = _UNSET
    clustering_threshold_m: ParameterNumber = _UNSET
    clustering_buffer_m: ParameterNumber = _UNSET
    min_od_distance_m: ParameterNumber = _UNSET
    seed: ParameterNumber = _UNSET
    fixed_capacity: ParameterNumber = _UNSET
    min_demand: ParameterNumber = _UNSET
    max_demand: ParameterNumber = _UNSET
    min_inventory_pct: ParameterNumber = _UNSET
    max_inventory_pct: ParameterNumber = _UNSET
    min_park_time_min: ParameterNumber = _UNSET
    max_park_time_min: ParameterNumber = _UNSET

    def changes(self) -> dict[str, Number]:
        return {name: getattr(self, name) for name in self.model_fields_set}


assert set(InstanceVersionPatch.model_fields) == set(PARAMETER_NAMES)


class InstanceParametersResource(BaseModel):
    center_lat: float
    center_lon: float
    radius_m: float
    clustering_threshold_m: float
    clustering_buffer_m: float
    min_od_distance_m: float
    seed: float
    fixed_capacity: float
    min_demand: float
    max_demand: float
    min_inventory_pct: float
    max_inventory_pct: float
    min_park_time_min: float
    max_park_time_min: float


class RuleValueResource(BaseModel):
    name: str
    value: float | str
    unit: str | None

    @classmethod
    def from_domain(cls, value: RuleValue) -> "RuleValueResource":
        return cls(name=value.name, value=value.value, unit=value.unit)


class RuleResultResource(BaseModel):
    rule: str
    passed: bool
    values: list[RuleValueResource] = Field(
        min_length=2, max_length=2, description="The two values the rule compares."
    )

    @classmethod
    def from_domain(cls, result: RuleResult) -> "RuleResultResource":
        return cls(
            rule=result.rule,
            passed=result.passed,
            values=[RuleValueResource.from_domain(item) for item in result.values],
        )


class ProblemDetails(BaseModel):
    """An error, as a problem document (RFC 9457)."""

    type: str
    title: str
    status: int
    detail: str
    code: str
    errors: list[FieldError] | None = None
    draft_id: str | None = Field(
        default=None, description="The existing draft, on a draft_exists conflict."
    )
    failures: list[RuleResultResource] | None = Field(
        default=None, description="The rules the draft breaks, on a rule_broken conflict."
    )
    reasons: list[BlockingReasonResponse] | None = Field(
        default=None,
        description="The components that block the action, on a component_unavailable answer.",
    )
    run_id: str | None = Field(
        default=None, description="The queued or running run, on a run_active conflict."
    )


class ParameterChangeResource(BaseModel):
    parameter: str
    before: float
    after: float

    @classmethod
    def from_domain(cls, change: ParameterChange) -> "ParameterChangeResource":
        return cls(parameter=change.parameter, before=change.before, after=change.after)


class InstancePeriodResource(BaseModel):
    id: str
    key: str
    label: str
    weekday: int
    start_time: time
    end_time: time
    routing_date: date
    routing_time: time
    arrive_by: bool
    routing_date_provisional: bool

    @classmethod
    def from_domain(cls, period: InstancePeriod) -> "InstancePeriodResource":
        return cls(
            id=period.id,
            key=period.key,
            label=period.label,
            weekday=period.weekday,
            start_time=period.start_time,
            end_time=period.end_time,
            routing_date=period.routing_date,
            routing_time=period.routing_time,
            arrive_by=period.arrive_by,
            routing_date_provisional=period.routing_date_provisional,
        )


class CauseResource(BaseModel):
    kind: Literal["parameter", "city_data", "package", "trip_planner_graph"]
    parameters: list[str] = Field(description="The parameter names, for a `parameter` cause.")

    @classmethod
    def from_domain(cls, cause: Cause) -> "CauseResource":
        return cls(kind=cause.kind, parameters=list(cause.parameters))


class PlannedStepResource(BaseModel):
    step: StepName
    number: int
    period_id: str | None
    input_key: str | None = Field(
        description="Null while the package fingerprint or the trip planner's graph manifest is "
        "unknown."
    )
    action: Literal["kept", "rebuilt"]
    causes: list[CauseResource] = Field(
        description="Why the key differs from the same step of `based_on_id`; empty when the "
        "version is based on none."
    )
    last_duration_s: float | None = Field(
        description="Seconds the same step last took on the same data set and radius."
    )

    @classmethod
    def from_domain(cls, planned: PlannedStep) -> "PlannedStepResource":
        return cls(
            step=planned.step,
            number=STEP_NUMBERS[planned.step],
            period_id=planned.period_id,
            input_key=planned.input_key,
            action=planned.action,
            causes=[CauseResource.from_domain(item) for item in planned.causes],
            last_duration_s=planned.last_duration_s,
        )


class BuildPlanResource(BaseModel):
    steps: list[PlannedStepResource]
    build_verdict: VerdictResponse = Field(
        description="Whether this plan can be built now, and what blocks it."
    )

    @classmethod
    def from_domain(cls, plan: BuildPlan, verdict: Verdict) -> "BuildPlanResource":
        return cls(
            steps=[PlannedStepResource.from_domain(item) for item in plan.steps],
            build_verdict=VerdictResponse.from_domain(verdict),
        )


class NumberResource(BaseModel):
    """A number with its unit and where it comes from."""

    value: float
    unit: str
    source: Literal["model", "package_summary", "input", "trip_planner", "derived", "simulation"]
    group: Literal["headline", "advanced"]

    @classmethod
    def from_domain(cls, number: DomainNumber) -> "NumberResource":
        return cls(value=number.value, unit=number.unit, source=number.source, group=number.group)


class InstanceCounts(BaseModel):
    """The five headline counts of a built version."""

    stops: NumberResource
    bike_stations: NumberResource
    hubs: NumberResource
    hub_pairs_with_routes: NumberResource
    travellers: NumberResource


class RoutesSummaryResource(BaseModel):
    """What the trip planner answered for the routes of the build."""

    queries: int
    queries_failed: int
    failure_pct: float
    pairs_without_public_transport: int
    pairs_without_car: int
    retries: int
    run_id: str | None = Field(
        description="The run whose routes step produced the routes the version links; "
        "`GET /runs/{run_id}/route-failures` lists the failed queries."
    )

    @classmethod
    def from_domain(cls, summary: RoutesSummary) -> "RoutesSummaryResource":
        return cls(
            queries=summary.queries,
            queries_failed=summary.queries_failed,
            failure_pct=summary.failure_pct,
            pairs_without_public_transport=summary.pairs_without_public_transport,
            pairs_without_car=summary.pairs_without_car,
            retries=summary.retries,
            run_id=summary.run_id,
        )


class InstanceVersionResource(BaseModel):
    id: str
    instance_id: str
    number: int
    based_on_id: str | None
    status: Literal["draft", "sealed"]
    created_at: datetime = Field(description="When the version was created.")
    sealed_at: datetime | None = Field(description="When the version was saved; null for a draft.")
    state: str = Field(
        description="`draft`; for a saved version the state of its latest build: `queued`, "
        "`building`, `ready`, `failed` or `cancelled` (`sealed` while it has none)."
    )
    parameters: InstanceParametersResource
    periods: list[InstancePeriodResource]
    rules: list[RuleResultResource]
    changes: list[ParameterChangeResource] = Field(
        description="The parameters that differ from `based_on_id`, in column order."
    )
    counts: InstanceCounts | None = Field(description="Null until the version is built.")
    routes: RoutesSummaryResource | None = Field(description="Null until the version is built.")
    build_plan: BuildPlanResource
    build_run_id: str | None = Field(
        description="The version's latest build run; null for a draft or a version never built."
    )
    package_defaults: InstanceParametersResource | None = Field(
        description="The model package's default values with the data set's preset centre and "
        "radius, for a draft; null for a saved version or while the package is not known."
    )

    @classmethod
    def from_view(cls, view: InstanceVersionView) -> "InstanceVersionResource":
        version = view.version
        return cls(
            id=version.id,
            instance_id=version.instance_id,
            number=version.number,
            based_on_id=version.based_on_id,
            status=version.status,
            created_at=version.created_at,
            sealed_at=version.sealed_at,
            state=view.state,
            parameters=InstanceParametersResource(**version.parameters.as_dict()),
            periods=[InstancePeriodResource.from_domain(item) for item in view.periods],
            rules=[RuleResultResource.from_domain(item) for item in view.rules],
            changes=[ParameterChangeResource.from_domain(item) for item in view.changes],
            counts=InstanceCounts(
                **{name: NumberResource.from_domain(item) for name, item in view.counts.items()}
            )
            if view.counts is not None
            else None,
            routes=RoutesSummaryResource.from_domain(view.routes)
            if view.routes is not None
            else None,
            build_plan=BuildPlanResource.from_domain(view.plan, view.build_verdict),
            build_run_id=view.build_run_id,
            package_defaults=InstanceParametersResource(**view.package_defaults.as_dict())
            if view.package_defaults is not None
            else None,
        )


class MenuVersion(BaseModel):
    id: str
    number: int
    status: Literal["draft", "sealed"]
    state: str = Field(
        description="`draft`, or the state of the latest build: `queued`, `building`, `ready`, "
        "`failed`, `cancelled` (`sealed` while it has none)."
    )
    pricing_version_count: int


class CityInstanceMenuItem(BaseModel):
    id: str
    name: str
    dataset_id: str
    versions: list[MenuVersion]

    @classmethod
    def from_domain(cls, entry: InstanceMenuEntry) -> "CityInstanceMenuItem":
        return cls(
            id=entry.instance.id,
            name=entry.instance.name,
            dataset_id=entry.instance.dataset_id,
            versions=[
                MenuVersion(
                    id=version.id,
                    number=version.number,
                    status=version.status,
                    state=entry.states[version.id],
                    pricing_version_count=0,
                )
                for version in entry.versions
            ],
        )


class CityInstanceMenu(BaseModel):
    items: list[CityInstanceMenuItem]


class StationResource(BaseModel):
    station_id: str
    kind: Literal["pt", "bs"] = Field(
        description="`pt` a public transport stop, `bs` a bike station."
    )
    name: str
    lat: float
    lon: float

    @classmethod
    def from_domain(cls, row: StationRow) -> "StationResource":
        return cls(
            station_id=row.station_id, kind=row.kind, name=row.name, lat=row.lat, lon=row.lon
        )


class StationList(BaseModel):
    items: list[StationResource]


class HubResource(BaseModel):
    hub_id: str
    label: str
    lat: float
    lon: float
    outline: dict[str, Any] | None = Field(description="A GeoJSON polygon, or null.")
    pt_station_ids: list[str]
    bike_station_ids: list[str]
    lines: list[str]

    @classmethod
    def from_domain(cls, row: HubRow) -> "HubResource":
        return cls(
            hub_id=row.hub_id,
            label=row.label,
            lat=row.lat,
            lon=row.lon,
            outline=dict(row.outline) if row.outline is not None else None,
            pt_station_ids=list(row.pt_station_ids),
            bike_station_ids=list(row.bike_station_ids),
            lines=list(row.lines),
        )


class HubList(BaseModel):
    items: list[HubResource]


class HubPairResource(BaseModel):
    origin_hub: str
    destination_hub: str
    demand: float
    euclid_dist_m: float

    @classmethod
    def from_domain(cls, row: HubPairRow) -> "HubPairResource":
        return cls(
            origin_hub=row.origin_hub,
            destination_hub=row.destination_hub,
            demand=row.demand,
            euclid_dist_m=row.euclid_dist_m,
        )


class HubPairList(BaseModel):
    items: list[HubPairResource]


class RoutePairResource(BaseModel):
    origin_hub: str
    destination_hub: str

    @classmethod
    def from_domain(cls, row: RoutePairRow) -> "RoutePairResource":
        return cls(origin_hub=row.origin_hub, destination_hub=row.destination_hub)


class RoutePairList(BaseModel):
    items: list[RoutePairResource]


class RouteFailureResource(BaseModel):
    origin_hub: str
    destination_hub: str
    query: Literal["pt_bike", "car"]
    kind: Literal["technical", "no_route"]
    message: str
    attempts: int
    period: str | None = Field(description="The id of the period the query was made for.")

    @classmethod
    def from_domain(cls, failure: RouteFailure, period: str | None) -> "RouteFailureResource":
        return cls(
            origin_hub=failure.origin_hub,
            destination_hub=failure.destination_hub,
            query=failure.query,
            kind=failure.kind,
            message=failure.message,
            attempts=failure.attempts,
            period=period,
        )


class RouteFailureList(BaseModel):
    items: list[RouteFailureResource]
