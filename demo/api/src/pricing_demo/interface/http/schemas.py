from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from pricing_demo.application.instance_version_view import InstanceVersionView
from pricing_demo.application.pricing_version_view import PricingVersionView
from pricing_demo.application.run_view import RunView
from pricing_demo.application.use_cases.compare_pricing_versions import (
    ComparedVersionView,
    Comparison,
)
from pricing_demo.application.use_cases.get_pricing_result import (
    GoalComparison,
    PricingResult,
    Provenance,
    SimulationResult,
    StoredSimulationFigures,
)
from pricing_demo.application.use_cases.get_showcase import ShowcaseView
from pricing_demo.application.use_cases.list_city_instances import InstanceMenuEntry
from pricing_demo.application.use_cases.list_hub_pair_results import HubPairResult, OptionResult
from pricing_demo.application.use_cases.list_hub_results import HubResult
from pricing_demo.application.use_cases.list_pricing_version_simulations import (
    VersionSimulation,
)
from pricing_demo.domain.build_plan import BUILD_STEPS, BuildPlan, Cause, PlannedStep
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import (
    PARAMETER_NAMES,
    InstancePeriod,
    Number,
    ParameterChange,
)
from pricing_demo.domain.comparison import (
    ComparisonGroup,
    ComparisonRow,
    FlatReference,
    HubDifference,
    PairDifference,
)
from pricing_demo.domain.failure_codes import FAILURE_CODES
from pricing_demo.domain.instance_rules import RuleResult, RuleValue
from pricing_demo.domain.numbers import Number as DomainNumber
from pricing_demo.domain.pricing_rules import PricingRuleResult
from pricing_demo.domain.pricing_versions import GOAL_NAMES
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
from pricing_demo.domain.traveller_simulation import SimulationRule


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


class SimulationRuleResource(BaseModel):
    """A traveller simulation rule: its id, its version and its parameters."""

    id: str
    version: int
    parameters: dict[str, float]

    @classmethod
    def from_domain(cls, rule: SimulationRule) -> "SimulationRuleResource":
        return cls(id=rule.id, version=rule.version, parameters=dict(rule.parameters))


class SystemStatusResponse(BaseModel):
    components: list[ComponentStatusResponse]
    can_build_instances: VerdictResponse
    can_run_pricing: VerdictResponse
    can_simulate: VerdictResponse
    simulation_rule: SimulationRuleResource | None = Field(
        description="The traveller simulation rule of the worker with the latest live "
        "heartbeat; null when no worker is live."
    )

    @classmethod
    def from_domain(cls, status: SystemStatus) -> "SystemStatusResponse":
        return cls(
            components=[ComponentStatusResponse.from_domain(item) for item in status.components],
            can_build_instances=VerdictResponse.from_domain(status.can_build_instances),
            can_run_pricing=VerdictResponse.from_domain(status.can_run_pricing),
            can_simulate=VerdictResponse.from_domain(status.can_simulate),
            simulation_rule=None
            if status.simulation_rule is None
            else SimulationRuleResource.from_domain(status.simulation_rule),
        )


class FieldError(BaseModel):
    field: str
    message: str


class ComponentAnswerRequest(BaseModel):
    state: ComponentState
    reason: str | None = None


PLAYED_STEPS = (*BUILD_STEPS, StepName.PRICING_MODEL)


def _a_failable_step[T: StepName | None](value: T) -> T:
    """The fake pricing model fails the four build steps and the pricing model step; it does
    not fail the traveller simulation, which runs in the worker's own domain code: another
    step would be accepted and never acted on, so a test naming it would silently run the
    happy path."""
    if value is not None and value not in PLAYED_STEPS:
        raise ValueError(f"must be one of {', '.join(item.value for item in PLAYED_STEPS)}")
    return value


HOLDABLE_STEPS = (*PLAYED_STEPS, StepName.TRAVELLER_SIMULATION)


def _a_holdable_step[T: StepName | None](value: T) -> T:
    """A hold applies to the played steps and to the traveller simulation, whose executor the
    worker wraps in fake mode only; the hold is the one thing a test may do to step 5b."""
    if value is not None and value not in HOLDABLE_STEPS:
        raise ValueError(f"must be one of {', '.join(item.value for item in HOLDABLE_STEPS)}")
    return value


class FailAt(BaseModel):
    step: StepName
    code: str

    _step_is_one_the_fake_fails = field_validator("step")(_a_failable_step)

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


class StagedSimulationRule(BaseModel):
    """The placeholder rule the worker uses, staged for a re-simulation scenario: a version
    (at least 2: version 1 is the rule's default, and a staged version 1 with other weights
    would replace its links and leave its simulations unlinked) and the two weights."""

    version: int = Field(ge=2)
    price_weight: float = Field(ge=0, le=1)
    time_weight: float = Field(ge=0, le=1)


class PricingModelSettings(BaseModel):
    """What the fake pricing model does: fail a step with a code, hold a step until it is
    released, pace the routes step, fail trip-planner queries at named pairs, and record a
    licence kind on its solves; and the rule the worker simulates travellers with. The
    defaults are no failure, no hold, no pace, no failed query, a full licence and
    `balanced-score` version 1 with equal weights."""

    fail_at: FailAt | None = None
    hold_at: StepName | None = None
    routes_pace_ms: int = Field(default=0, ge=0)
    route_failures: list[FakeRouteFailure] = Field(default_factory=list)
    licence_kind: Literal["full", "limited"] | None = None
    simulation_rule: StagedSimulationRule | None = None

    _hold_is_a_holdable_step = field_validator("hold_at")(_a_holdable_step)


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
    last_duration_s: float | None  # the pricing model step of a pricing run; else null
    reason: str | None

    @classmethod
    def from_domain(cls, step: RunStep, last_duration_s: float | None = None) -> "RunStepResource":
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
            last_duration_s=last_duration_s,
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
            steps=[
                RunStepResource.from_domain(item, view.step_durations.get(item.step))
                for item in run.steps
            ],
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


class PricingRuleResultResource(BaseModel):
    rule: str
    passed: bool
    field: str = Field(description="The goal the rule checks.")
    value: float
    message: str = Field(description="Names the value, as a failure reads on the form.")

    @classmethod
    def from_domain(cls, result: PricingRuleResult) -> "PricingRuleResultResource":
        return cls(
            rule=result.rule,
            passed=result.passed,
            field=result.field,
            value=result.value,
            message=result.message,
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
    pricing_failures: list[PricingRuleResultResource] | None = Field(
        default=None,
        description="The rules the pricing draft breaks, each with its goal and value, on a "
        "rule_broken conflict of a pricing version.",
    )
    run_id: str | None = Field(
        default=None, description="The queued or running run, on a run_active conflict."
    )
    pricing_version_ids: list[str] | None = Field(
        default=None,
        description="The pricing versions that block a deletion, in letter order, on a "
        "has_pricing_versions conflict.",
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
    pricing_version_letters: list[str] = Field(
        description="The letters of the version's pricing versions, in letter order."
    )


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
                    pricing_version_count=len(entry.pricing_letters[version.id]),
                    pricing_version_letters=list(entry.pricing_letters[version.id]),
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


class CreatePricingVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    based_on: str | None = Field(
        default=None, description="A pricing version of the same instance version to copy."
    )


class PricingVersionPatch(BaseModel):
    """Any subset of the eight goal values. A value is stored as sent: a rule it breaks is
    reported in the answer, never corrected."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="The version's name, trimmed; it may not be blank.",
    )
    cost_bike_chf: ParameterNumber = _UNSET
    lowest_price_chf: ParameterNumber = _UNSET
    ridership_weight: ParameterNumber = _UNSET
    station_balance_weight: ParameterNumber = _UNSET
    pt_fare_chf: ParameterNumber = _UNSET
    car_parking_fee_chf: ParameterNumber = _UNSET
    max_displayed_options: ParameterNumber = _UNSET
    flat_price_per_ride_chf: ParameterNumber = _UNSET

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("The name may not be blank.")
        return trimmed

    def changes(self) -> dict[str, Number]:
        return {name: getattr(self, name) for name in self.model_fields_set if name in GOAL_NAMES}


assert set(PricingVersionPatch.model_fields) - {"name"} == set(GOAL_NAMES)


class PricingGoalsResource(BaseModel):
    cost_bike_chf: float
    lowest_price_chf: float
    ridership_weight: float
    station_balance_weight: float
    pt_fare_chf: float
    car_parking_fee_chf: float
    max_displayed_options: float
    flat_price_kind: Literal["per_ride"]
    flat_price_per_ride_chf: float


class PricingPeriodResource(BaseModel):
    id: str
    key: str
    label: str


class PricingVersionRef(BaseModel):
    id: str
    letter: str


class PricingVersionResource(BaseModel):
    id: str
    instance_version_id: str
    letter: str
    name: str
    status: Literal["draft", "sealed"]
    state: Literal["draft", "queued", "running", "failed", "cancelled", "result"] = Field(
        description="Derived from the status and the version's last run."
    )
    based_on_id: str | None
    run_id: str | None = Field(
        description="The id of the version's latest pricing run; null for a draft."
    )
    kept_from: PricingVersionRef | None = Field(
        description="The sealed version whose fare, parking fee, options shown and flat price "
        "this draft kept; null when it started from the default values."
    )
    last_duration_s: float | None = Field(
        description="Seconds the pricing model last took on this instance's data set and "
        "radius, or null when it has not run there."
    )
    created_at: datetime
    sealed_at: datetime | None
    goals: PricingGoalsResource
    periods: list[PricingPeriodResource]
    rules: list[PricingRuleResultResource]

    @classmethod
    def from_view(cls, view: PricingVersionView) -> "PricingVersionResource":
        version = view.version
        return cls(
            id=version.id,
            instance_version_id=version.instance_version_id,
            letter=version.letter,
            name=version.name,
            status=version.status,
            state=view.state,
            based_on_id=version.based_on_id,
            run_id=view.run_id,
            kept_from=(
                PricingVersionRef(id=view.kept_from[0], letter=view.kept_from[1])
                if view.kept_from
                else None
            ),
            last_duration_s=view.last_duration_s,
            created_at=version.created_at,
            sealed_at=version.sealed_at,
            goals=PricingGoalsResource(
                **version.goals.as_dict(), flat_price_kind=version.goals.flat_price_kind
            ),
            periods=[
                PricingPeriodResource(id=item.id, key=item.key, label=item.label)
                for item in view.periods
            ],
            rules=[PricingRuleResultResource.from_domain(item) for item in view.rules],
        )


class PricingVersionList(BaseModel):
    items: list[PricingVersionResource]


class PricingVersionSimulationResource(BaseModel):
    """One stored simulation of a pricing version: a period under a price scheme and a rule."""

    period_id: str
    price_scheme: Literal["model_prices", "flat"]
    rule_id: str
    rule_version: int
    rule_parameters: dict[str, float]
    rule_current: bool = Field(
        description="True when the rule is the one the live worker uses now; false for every "
        "simulation when no worker is live."
    )
    simulation_key: str
    created_at: datetime

    @classmethod
    def from_view(cls, view: VersionSimulation) -> "PricingVersionSimulationResource":
        linked = view.linked
        return cls(
            period_id=linked.period_id,
            price_scheme=linked.price_scheme,
            rule_id=linked.rule_id,
            rule_version=linked.rule_version,
            rule_parameters=dict(linked.rule_parameters),
            rule_current=view.rule_current,
            simulation_key=linked.simulation_key,
            created_at=linked.created_at,
        )


class PricingVersionSimulationList(BaseModel):
    items: list[PricingVersionSimulationResource]


def _number(item: DomainNumber | None) -> "NumberResource | None":
    return None if item is None else NumberResource.from_domain(item)


def _numbers(items: Mapping[str, DomainNumber]) -> "dict[str, NumberResource]":
    return {name: NumberResource.from_domain(item) for name, item in items.items()}


class GoalResource(BaseModel):
    """One goal: what the model's own result says (absent when it says nothing), the value
    simulated with the model's prices and with the flat price, and their difference."""

    name: Literal[
        "ridership",
        "revenue",
        "cost",
        "profit",
        "mean_bike_price",
        "stations_empty",
        "stations_full",
    ]
    model: NumberResource | None
    model_prices: NumberResource | None
    flat: NumberResource | None
    change: NumberResource | None = Field(
        description="The simulation with the model's prices minus the simulation with the flat "
        "price; absent when either value is."
    )

    @classmethod
    def from_domain(cls, item: GoalComparison) -> "GoalResource":
        return cls(
            name=item.name,
            model=_number(item.model),
            model_prices=_number(item.model_prices),
            flat=_number(item.flat),
            change=_number(item.change),
        )


class SimulationResultResource(BaseModel):
    """The latest simulation of one price scheme."""

    price_scheme: Literal["model_prices", "flat"]
    period_id: str
    rule_id: str
    rule_version: int
    rule_parameters: dict[str, float]
    rule_current: bool
    simulation_key: str
    created_at: datetime
    travellers: dict[str, NumberResource] = Field(
        description="Travellers per mode: `pt_bike`, `pt_only`, `car`."
    )
    displaced: NumberResource
    unserved: NumberResource
    bike_rides: NumberResource
    revenue: NumberResource
    cost: NumberResource

    @classmethod
    def from_domain(cls, item: SimulationResult) -> "SimulationResultResource":
        summary = item.summary
        return cls(
            price_scheme=item.link.price_scheme,
            period_id=item.link.period_id,
            rule_id=item.link.rule_id,
            rule_version=item.link.rule_version,
            rule_parameters=dict(summary.rule_parameters),
            rule_current=item.rule_current,
            simulation_key=item.link.simulation_key,
            created_at=item.link.created_at,
            travellers={
                mode: NumberResource(
                    value=count, unit="travellers", source="simulation", group="headline"
                )
                for mode, count in summary.travellers_per_mode.items()
            },
            displaced=NumberResource(
                value=summary.displaced, unit="travellers", source="simulation", group="headline"
            ),
            unserved=NumberResource(
                value=summary.unserved, unit="travellers", source="simulation", group="headline"
            ),
            bike_rides=NumberResource(
                value=summary.bike_rides, unit="bike_rides", source="simulation", group="headline"
            ),
            revenue=NumberResource.from_domain(item.goals["revenue"]),
            cost=NumberResource.from_domain(item.goals["cost"]),
        )


class StoredSimulationResource(BaseModel):
    """One stored simulation of the version (older rules included), as stories 3-9 to 3-12
    read it."""

    price_scheme: Literal["model_prices", "flat"]
    period_id: str
    rule_id: str
    rule_version: int
    simulation_key: str
    created_at: datetime
    bike_rides: NumberResource
    revenue: NumberResource
    cost: NumberResource

    @classmethod
    def from_domain(cls, item: StoredSimulationFigures) -> "StoredSimulationResource":
        return cls(
            price_scheme=item.link.price_scheme,
            period_id=item.link.period_id,
            rule_id=item.link.rule_id,
            rule_version=item.link.rule_version,
            simulation_key=item.link.simulation_key,
            created_at=item.link.created_at,
            bike_rides=NumberResource.from_domain(item.bike_rides),
            revenue=NumberResource.from_domain(item.revenue),
            cost=NumberResource.from_domain(item.cost),
        )


class AdvancedResource(BaseModel):
    """The technical numbers: only here, never among the headline ones."""

    solver_status_name: str
    numbers: dict[str, NumberResource]


class SimulationProvenanceResource(BaseModel):
    price_scheme: Literal["model_prices", "flat"]
    rule_id: str
    rule_version: int
    created_at: datetime


class ProvenanceResource(BaseModel):
    run_id: str
    solve_key: str
    derivation_version: int
    package_fingerprint: str
    package_version: str | None
    package_commit: str | None
    package_dirty: bool | None
    gurobi_version: str
    licence_kind: str
    solver_parameters: dict[str, Any]
    dependency_lock_sha256: str
    platform: str
    demonstrator_version: str
    input_keys: dict[str, str] = Field(description="The key of each build step's artefact.")
    gtfs_sha256: str | None
    gbfs_sha256: str | None
    timetable_valid_from: date | None
    timetable_valid_to: date | None
    routing_date: date | None
    routing_time: time | None
    routing_date_provisional: bool | None
    bike_stations_fetched_at: datetime | None
    timetable_operator: str | None = Field(
        description="The agency names of the timetable's agency.txt, joined by a comma."
    )
    bike_stations_source_url: str | None = Field(
        description="The address the bike-station snapshot was fetched from."
    )
    simulations: list[SimulationProvenanceResource] = Field(
        description="The rule and the date of the latest simulation of each scheme."
    )

    @classmethod
    def from_domain(cls, item: Provenance) -> "ProvenanceResource":
        fields = dict(item.__dict__)
        fields["simulations"] = [
            SimulationProvenanceResource(
                price_scheme=found.price_scheme,
                rule_id=found.rule_id,
                rule_version=found.rule_version,
                created_at=found.created_at,
            )
            for found in item.simulations
        ]
        return cls(**fields)


class PricingResultResponse(BaseModel):
    pricing_version_id: str
    period_id: str
    headline: dict[str, NumberResource]
    goals: list[GoalResource]
    simulations: list[SimulationResultResource] = Field(
        description="The latest simulation of each scheme: `model_prices`, then `flat`."
    )
    simulation_history: list[StoredSimulationResource]
    model_split: dict[str, NumberResource]
    advanced: AdvancedResource
    coefficients: dict[str, NumberResource | None] | None = Field(
        description="The choice-model coefficients read from the package source, each null when "
        "not found; null as a whole when the package fingerprint is not stored."
    )
    hub_pairs_with_bike_option: NumberResource
    provenance: ProvenanceResource

    @classmethod
    def from_domain(cls, result: PricingResult) -> "PricingResultResponse":
        return cls(
            pricing_version_id=result.version.id,
            period_id=result.period_id,
            headline=_numbers(result.headline),
            goals=[GoalResource.from_domain(item) for item in result.goals],
            simulations=[SimulationResultResource.from_domain(item) for item in result.simulations],
            simulation_history=[
                StoredSimulationResource.from_domain(item) for item in result.simulation_history
            ],
            model_split=_numbers(result.model_split),
            advanced=AdvancedResource(
                solver_status_name=result.solver_status_name, numbers=_numbers(result.advanced)
            ),
            coefficients=None
            if result.coefficients is None
            else {name: _number(item) for name, item in result.coefficients.items()},
            hub_pairs_with_bike_option=NumberResource.from_domain(
                result.numbers.numbers["hub_pairs_with_bike_option"]
            ),
            provenance=ProvenanceResource.from_domain(result.provenance),
        )


class RouteLegResource(BaseModel):
    mode: str
    duration_s: float
    distance_m: float
    line_kind: Literal["street", "shape", "straight"]
    line: str | None = Field(
        description=(
            "The line's public code; null for a leg without one (a street leg) and for a leg"
            " stored before the names were kept."
        )
    )
    from_place: str | None = Field(
        description=(
            "Where the leg starts; null when the trip planner gave no name and for a leg"
            " stored before the names were kept."
        )
    )
    to_place: str | None = Field(
        description=(
            "Where the leg ends; null when the trip planner gave no name and for a leg"
            " stored before the names were kept."
        )
    )


class OptionResultResource(BaseModel):
    arc_id: str
    mode: Literal["pt_bike", "pt_only", "car"]
    legs: list[RouteLegResource]
    duration: NumberResource
    bike_legs: NumberResource | None
    bike_price: NumberResource | None = Field(
        description="Absent when the model does not offer it."
    )
    riders: NumberResource | None = Field(description="Absent when the model has no row for it.")

    @classmethod
    def from_domain(cls, item: OptionResult) -> "OptionResultResource":
        return cls(
            arc_id=item.arc_id,
            mode=item.mode,
            legs=[
                RouteLegResource(
                    mode=leg.mode,
                    duration_s=leg.duration_s,
                    distance_m=leg.distance_m,
                    line_kind=leg.line_kind,
                    line=leg.line,
                    from_place=leg.from_place,
                    to_place=leg.to_place,
                )
                for leg in item.legs
            ],
            duration=NumberResource.from_domain(item.duration_s),
            bike_legs=_number(item.bike_legs),
            bike_price=_number(item.bike_price),
            riders=_number(item.riders),
        )


class HubPairResultResource(BaseModel):
    origin_hub: str
    destination_hub: str
    mean_bike_price: NumberResource | None = Field(
        description="Absent when the pair has no offered PT + bike option."
    )
    min_bike_price: NumberResource | None
    max_bike_price: NumberResource | None
    travellers: dict[str, NumberResource] = Field(
        description="Travellers per mode of the model's own result."
    )
    options: list[OptionResultResource]

    @classmethod
    def from_domain(cls, item: HubPairResult) -> "HubPairResultResource":
        numbers = item.numbers
        return cls(
            origin_hub=numbers.origin_hub,
            destination_hub=numbers.destination_hub,
            mean_bike_price=_number(numbers.mean_bike_price),
            min_bike_price=_number(numbers.min_bike_price),
            max_bike_price=_number(numbers.max_bike_price),
            travellers=_numbers(numbers.travellers),
            options=[OptionResultResource.from_domain(option) for option in item.options],
        )


class HubPairResultList(BaseModel):
    items: list[HubPairResultResource]


class HubResultResource(BaseModel):
    hub_id: str
    label: str
    lat: float
    lon: float
    rides_starting: NumberResource
    rides_ending: NumberResource
    mean_bike_price: NumberResource | None = Field(
        description="Over the offered options that start at the hub; absent without any."
    )

    @classmethod
    def from_domain(cls, item: HubResult) -> "HubResultResource":
        return cls(
            hub_id=item.hub.hub_id,
            label=item.hub.label,
            lat=item.hub.lat,
            lon=item.hub.lon,
            rides_starting=NumberResource.from_domain(item.numbers.rides_starting),
            rides_ending=NumberResource.from_domain(item.numbers.rides_ending),
            mean_bike_price=_number(item.numbers.mean_bike_price),
        )


class HubResultList(BaseModel):
    items: list[HubResultResource]


class ShowcaseRequest(BaseModel):
    pricing_version_id: str
    period_id: str | None = Field(
        default=None, description="The period to show; the version's first when absent."
    )


class ShowcaseResponse(BaseModel):
    pricing_version_id: str
    period_id: str
    marked_at: datetime
    letter: str
    instance_version_id: str
    instance_version_name: str
    headline: dict[str, NumberResource]

    @classmethod
    def from_view(cls, view: ShowcaseView) -> "ShowcaseResponse":
        return cls(
            pricing_version_id=view.mark.pricing_version_id,
            period_id=view.mark.period_id,
            marked_at=view.mark.marked_at,
            letter=view.letter,
            instance_version_id=view.instance_version_id,
            instance_version_name=view.instance_version_name,
            headline=_numbers(view.headline),
        )


class ComparisonInstanceVersion(BaseModel):
    id: str
    name: str = Field(description='The instance name and number, as "{name} v{number}".')


class ComparisonPeriod(BaseModel):
    id: str
    name: str


class PackageResource(BaseModel):
    fingerprint: str
    commit: str | None


class ComparedSimulationResource(BaseModel):
    """A simulation a compared version is read with: the latest of its scheme."""

    price_scheme: Literal["model_prices", "flat"]
    simulation_key: str
    rule_id: str
    rule_version: int
    rule_parameters: dict[str, float]
    rule_current: bool


class ComparedVersionResource(BaseModel):
    id: str
    letter: str
    name: str
    goals: dict[str, NumberResource] = Field(
        description="The eight goals of the version, keyed by goal name."
    )
    package: PackageResource
    simulations: list[ComparedSimulationResource] = Field(
        description="`model_prices`, then `flat`."
    )
    model_split: dict[str, NumberResource]
    flat_reference: str = Field(description="The `id` of its entry in `flat_references`.")
    solve_key: str

    @classmethod
    def from_view(cls, view: ComparedVersionView) -> "ComparedVersionResource":
        return cls(
            id=view.version.id,
            letter=view.version.letter,
            name=view.version.name,
            goals=_numbers(view.goals),
            package=PackageResource(
                fingerprint=view.package_fingerprint, commit=view.package_commit
            ),
            simulations=[
                ComparedSimulationResource(
                    price_scheme=item.link.price_scheme,
                    simulation_key=item.link.simulation_key,
                    rule_id=item.link.rule_id,
                    rule_version=item.link.rule_version,
                    rule_parameters=dict(item.summary.rule_parameters),
                    rule_current=item.rule_current,
                )
                for item in view.result.simulations
            ],
            model_split=_numbers(view.result.model_split),
            flat_reference=view.flat_reference,
            solve_key=view.result.provenance.solve_key,
        )


class FlatReferenceResource(BaseModel):
    id: str = Field(
        description="The flat column's id: its flat simulation's key and its cost of one ride."
    )
    simulation_key: str = Field(
        description="The stored flat simulation it reads; two references may share one."
    )
    letters: list[str] = Field(description="The versions this flat column serves.")
    values: dict[str, NumberResource]
    cost_bike_chf: NumberResource = Field(
        description="The cost of one ride its simulated profit is computed with."
    )
    rule_id: str
    rule_version: int
    rule_parameters: dict[str, float]
    rule_current: bool

    @classmethod
    def from_domain(cls, item: FlatReference) -> "FlatReferenceResource":
        return cls(
            id=item.id,
            simulation_key=item.simulation_key,
            letters=list(item.letters),
            values=_numbers(item.values),
            cost_bike_chf=NumberResource.from_domain(item.cost_bike_chf),
            rule_id=item.rule_id,
            rule_version=item.rule_version,
            rule_parameters=dict(item.rule_parameters),
            rule_current=item.rule_current,
        )


def _optional_numbers(
    items: Mapping[str, DomainNumber | None],
) -> "dict[str, NumberResource | None]":
    return {name: _number(item) for name, item in items.items()}


class ComparisonRowResource(BaseModel):
    key: str = Field(description="A stable key; the screen owns the label.")
    values: dict[str, NumberResource | None] = Field(
        description="Per version letter; null when the version has no value."
    )
    changes: dict[str, NumberResource | None] = Field(
        description="Simulated group only: the model's prices minus the flat simulation."
    )
    flats: dict[str, NumberResource | None] = Field(
        description="Simulated group only: the value per flat reference id."
    )
    best: list[str] = Field(description="The letters with the best value; empty when none.")

    @classmethod
    def from_domain(cls, item: ComparisonRow) -> "ComparisonRowResource":
        return cls(
            key=item.key,
            values=_optional_numbers(item.values),
            changes=_optional_numbers(item.changes),
            flats=_optional_numbers(item.flats),
            best=list(item.best),
        )


class ComparisonGroupResource(BaseModel):
    name: Literal["simulated", "model", "derived", "goals_that_differ", "solver"]
    rows: list[ComparisonRowResource]

    @classmethod
    def from_domain(cls, item: ComparisonGroup) -> "ComparisonGroupResource":
        return cls(
            name=item.name,
            rows=[ComparisonRowResource.from_domain(row) for row in item.rows],
        )


class PairDifferenceResource(BaseModel):
    origin_hub: str
    destination_hub: str
    mean_price_a: NumberResource
    mean_price_b: NumberResource
    price_difference: NumberResource
    travellers_a: NumberResource
    travellers_b: NumberResource
    travellers_difference: NumberResource

    @classmethod
    def from_domain(cls, item: PairDifference) -> "PairDifferenceResource":
        return cls(
            origin_hub=item.origin_hub,
            destination_hub=item.destination_hub,
            mean_price_a=NumberResource.from_domain(item.mean_price_a),
            mean_price_b=NumberResource.from_domain(item.mean_price_b),
            price_difference=NumberResource.from_domain(item.price_difference),
            travellers_a=NumberResource.from_domain(item.travellers_a),
            travellers_b=NumberResource.from_domain(item.travellers_b),
            travellers_difference=NumberResource.from_domain(item.travellers_difference),
        )


class PairDifferences(BaseModel):
    a: str = Field(description="The letter of the version before the last.")
    b: str = Field(description="The letter of the last version; differences are `b` minus `a`.")
    pairs: list[PairDifferenceResource]


class HubDifferenceResource(BaseModel):
    hub_id: str
    mean_price_a: NumberResource | None
    mean_price_b: NumberResource | None
    price_difference: NumberResource | None
    price_b_minus_flat: NumberResource | None = Field(
        description="The mean bike price of `b` minus `b`'s flat price per ride."
    )
    rides_starting_a: NumberResource | None
    rides_starting_b: NumberResource | None
    rides_starting_difference: NumberResource | None

    @classmethod
    def from_domain(cls, item: HubDifference) -> "HubDifferenceResource":
        return cls(
            hub_id=item.hub_id,
            mean_price_a=_number(item.mean_price_a),
            mean_price_b=_number(item.mean_price_b),
            price_difference=_number(item.price_difference),
            price_b_minus_flat=_number(item.price_b_minus_flat),
            rides_starting_a=_number(item.rides_starting_a),
            rides_starting_b=_number(item.rides_starting_b),
            rides_starting_difference=_number(item.rides_starting_difference),
        )


class ComparisonResponse(BaseModel):
    instance_version: ComparisonInstanceVersion
    period: ComparisonPeriod
    versions: list[ComparedVersionResource] = Field(description="In letter order.")
    flat_references: list[FlatReferenceResource]
    groups: list[ComparisonGroupResource] = Field(
        description="`simulated`, `model`, `derived`, `goals_that_differ`, `solver`."
    )
    pair_differences: PairDifferences
    hub_differences: list[HubDifferenceResource]
    identical_solves: list[list[str]] = Field(
        description="Letters of versions whose result is the same stored solve; empty when none."
    )

    @classmethod
    def from_domain(cls, item: Comparison) -> "ComparisonResponse":
        return cls(
            instance_version=ComparisonInstanceVersion(
                id=item.instance_version_id, name=item.instance_version_name
            ),
            period=ComparisonPeriod(id=item.period_id, name=item.period_name),
            versions=[ComparedVersionResource.from_view(view) for view in item.versions],
            flat_references=[
                FlatReferenceResource.from_domain(ref) for ref in item.flat_references
            ],
            groups=[ComparisonGroupResource.from_domain(group) for group in item.groups],
            pair_differences=PairDifferences(
                a=item.pair_difference_letters[0],
                b=item.pair_difference_letters[1],
                pairs=[PairDifferenceResource.from_domain(pair) for pair in item.pair_differences],
            ),
            hub_differences=[
                HubDifferenceResource.from_domain(hub) for hub in item.hub_differences
            ],
            identical_solves=[list(letters) for letters in item.identical_solves],
        )
