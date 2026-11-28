from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.runner_liveness import is_alive
from pricing_demo.domain.traveller_simulation import SimulationRule


class ComponentName(StrEnum):
    """The parts of the system an action depends on, in the order they are reported."""

    STORAGE = "storage"
    RUNNER = "runner"
    SOLVER = "solver"
    PACKAGE = "package"
    TRIP_PLANNER = "trip_planner"
    CITY_DATA = "city_data"


class ComponentState(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


# The components the worker probes and reports; the API probes storage and derives the runner.
PROBED_COMPONENTS = (ComponentName.SOLVER, ComponentName.PACKAGE, ComponentName.TRIP_PLANNER)

NO_RUNNER_REASON = "No runner has reported in the last 30 s."
NO_CITY_DATA_REASON = "No city data is imported yet"
STORAGE_UNKNOWN_REASON = "Not known: the database does not answer."
_REPORT_LABELS = {
    ComponentName.SOLVER: "solver",
    ComponentName.PACKAGE: "pricing package",
    ComponentName.TRIP_PLANNER: "trip planner",
}


def not_reported_reason(name: ComponentName) -> str:
    return f"The runner has not reported the {_REPORT_LABELS[name]}."


def no_city_data_status() -> "ComponentStatus":
    return ComponentStatus.unavailable(ComponentName.CITY_DATA, NO_CITY_DATA_REASON)


class InvalidComponentStatus(DomainError):
    pass


class IncompleteSystemStatus(DomainError):
    pass


@dataclass(frozen=True)
class ComponentStatus:
    name: ComponentName
    state: ComponentState
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.state is ComponentState.AVAILABLE and self.reason is not None:
            raise InvalidComponentStatus(f"{self.name}: an available component has no reason.")
        if self.state is not ComponentState.AVAILABLE and not self.reason:
            raise InvalidComponentStatus(f"{self.name}: a {self.state} component needs a reason.")
        if self.state is ComponentState.LIMITED and self.name is not ComponentName.SOLVER:
            raise InvalidComponentStatus(f"{self.name}: only the solver can be limited.")

    @classmethod
    def ready(cls, name: ComponentName) -> "ComponentStatus":
        return cls(name=name, state=ComponentState.AVAILABLE)

    @classmethod
    def limited(cls, name: ComponentName, reason: str) -> "ComponentStatus":
        return cls(name=name, state=ComponentState.LIMITED, reason=reason)

    @classmethod
    def unavailable(cls, name: ComponentName, reason: str) -> "ComponentStatus":
        return cls(name=name, state=ComponentState.UNAVAILABLE, reason=reason)


@dataclass(frozen=True)
class BlockingReason:
    component: ComponentName
    reason: str


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reasons: tuple[BlockingReason, ...]


# ARCHITECTURE.md § 10.1: what each action needs. Storage blocks all three: without
# PostgreSQL no data route answers and a simulation needs the worker and PostgreSQL.
REQUIRED: Mapping[str, frozenset[ComponentName]] = {
    "can_build_instances": frozenset(
        {
            ComponentName.STORAGE,
            ComponentName.RUNNER,
            ComponentName.PACKAGE,
            ComponentName.TRIP_PLANNER,
            ComponentName.CITY_DATA,
        }
    ),
    "can_run_pricing": frozenset(
        {
            ComponentName.STORAGE,
            ComponentName.RUNNER,
            ComponentName.PACKAGE,
            ComponentName.SOLVER,
        }
    ),
    "can_simulate": frozenset({ComponentName.STORAGE, ComponentName.RUNNER}),
}


@dataclass(frozen=True)
class SystemStatus:
    """One status per component, in `ComponentName` order, and the traveller simulation rule
    of the worker with the latest live heartbeat (None when no worker is live)."""

    components: tuple[ComponentStatus, ...]
    simulation_rule: SimulationRule | None = None

    def __post_init__(self) -> None:
        if tuple(status.name for status in self.components) != tuple(ComponentName):
            raise IncompleteSystemStatus(
                "A system status holds exactly one status per component, "
                f"in the order {', '.join(ComponentName)}."
            )

    @classmethod
    def of(
        cls,
        statuses: Iterable[ComponentStatus],
        simulation_rule: SimulationRule | None = None,
    ) -> "SystemStatus":
        order = {name: position for position, name in enumerate(ComponentName)}
        return cls(tuple(sorted(statuses, key=lambda status: order[status.name])), simulation_rule)

    @property
    def can_build_instances(self) -> Verdict:
        return self._verdict("can_build_instances")

    @property
    def can_run_pricing(self) -> Verdict:
        return self._verdict("can_run_pricing")

    @property
    def can_simulate(self) -> Verdict:
        return self._verdict("can_simulate")

    def _verdict(self, action: str) -> Verdict:
        return self.verdict_for(REQUIRED[action])

    def verdict_for(self, needed: frozenset[ComponentName]) -> Verdict:
        """Whether every component in `needed` is available, and what blocks if not."""
        reasons = tuple(
            BlockingReason(status.name, status.reason or "")
            for status in self.components
            if status.name in needed and status.state is not ComponentState.AVAILABLE
        )
        return Verdict(allowed=not reasons, reasons=reasons)


NO_FINGERPRINT_REASON = (
    "The runner has not reported the pricing model's package yet: start the worker."
)
NO_MANIFEST_REASON = "The trip planner's graph has no manifest: build it with make otp-graph."


def build_verdict(
    status: SystemStatus,
    needs_trip_planner: bool,
    *,
    package_missing: bool = False,
    manifest_missing: bool = False,
) -> Verdict:
    """`can_build_instances` for one plan (ARCHITECTURE.md § 10.1): storage, the runner, the
    package and the city data always, the trip planner only when a routes step is rebuilt, the
    solver never. A plan that has no package fingerprint, or no graph manifest while routes are
    rebuilt, cannot name its artefacts: that is a reason too, unless the component already
    gives one."""
    needed = {
        ComponentName.STORAGE,
        ComponentName.RUNNER,
        ComponentName.PACKAGE,
        ComponentName.CITY_DATA,
    }
    if needs_trip_planner:
        needed.add(ComponentName.TRIP_PLANNER)
    verdict = status.verdict_for(frozenset(needed))
    reasons = list(verdict.reasons)
    blocked = {item.component for item in reasons}
    if package_missing and ComponentName.PACKAGE not in blocked:
        reasons.append(BlockingReason(ComponentName.PACKAGE, NO_FINGERPRINT_REASON))
    if manifest_missing and needs_trip_planner and ComponentName.TRIP_PLANNER not in blocked:
        reasons.append(BlockingReason(ComponentName.TRIP_PLANNER, NO_MANIFEST_REASON))
    order = {name: position for position, name in enumerate(ComponentName)}
    reasons.sort(key=lambda item: order[item.component])
    return Verdict(allowed=not reasons, reasons=tuple(reasons))


@dataclass(frozen=True)
class ComponentReport:
    """What a worker reported about a probed component, and when its worker last beat."""

    status: ComponentStatus
    reported_at: datetime
    worker_id: str
    worker_heartbeat_at: datetime | None
    details: Mapping[str, object]


def system_status_from(
    storage: ComponentStatus,
    latest_worker_heartbeat: datetime | None,
    reports: Sequence[ComponentReport],
    server_time: datetime,
    city_data: ComponentStatus,
    simulation_rule: Mapping[str, object] | None = None,
) -> SystemStatus:
    """The six components from the API's own storage probe, the `workers` heartbeats, the
    reports and the count of city data sets, judged on the API's clock. The current rule is
    the latest heartbeat's `simulation_rule`, when that heartbeat is live."""
    if storage.state is not ComponentState.AVAILABLE:
        unknown = [
            ComponentStatus.unavailable(name, STORAGE_UNKNOWN_REASON)
            for name in ComponentName
            if name is not ComponentName.STORAGE
        ]
        return SystemStatus.of([storage, *unknown])
    runner_alive = is_alive(latest_worker_heartbeat, server_time)
    if runner_alive:
        runner = ComponentStatus.ready(ComponentName.RUNNER)
    else:
        runner = ComponentStatus.unavailable(ComponentName.RUNNER, NO_RUNNER_REASON)
    fresh = {
        report.status.name: report.status
        for report in reports
        if is_alive(report.worker_heartbeat_at, server_time)
    }
    probed = [
        fresh.get(name) or ComponentStatus.unavailable(name, not_reported_reason(name))
        for name in PROBED_COMPONENTS
    ]
    current = SimulationRule.from_record(simulation_rule) if runner_alive else None
    return SystemStatus.of([storage, runner, *probed, city_data], current)
