from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.runner_liveness import is_alive


class ComponentName(StrEnum):
    """The parts of the system an action depends on, in the order they are reported."""

    STORAGE = "storage"
    RUNNER = "runner"
    SOLVER = "solver"
    PACKAGE = "package"
    TRIP_PLANNER = "trip_planner"


class ComponentState(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


# The components the worker probes and reports; the API probes storage and derives the runner.
PROBED_COMPONENTS = (ComponentName.SOLVER, ComponentName.PACKAGE, ComponentName.TRIP_PLANNER)

NO_RUNNER_REASON = "No runner has reported in the last 30 s."
STORAGE_UNKNOWN_REASON = "Not known: the database does not answer."
_REPORT_LABELS = {
    ComponentName.SOLVER: "solver",
    ComponentName.PACKAGE: "pricing package",
    ComponentName.TRIP_PLANNER: "trip planner",
}


def not_reported_reason(name: ComponentName) -> str:
    return f"The runner has not reported the {_REPORT_LABELS[name]}."


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
    """One status per component, in `ComponentName` order."""

    components: tuple[ComponentStatus, ...]

    def __post_init__(self) -> None:
        if tuple(status.name for status in self.components) != tuple(ComponentName):
            raise IncompleteSystemStatus(
                "A system status holds exactly one status per component, "
                f"in the order {', '.join(ComponentName)}."
            )

    @classmethod
    def of(cls, statuses: Iterable[ComponentStatus]) -> "SystemStatus":
        order = {name: position for position, name in enumerate(ComponentName)}
        return cls(tuple(sorted(statuses, key=lambda status: order[status.name])))

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
        needed = REQUIRED[action]
        reasons = tuple(
            BlockingReason(status.name, status.reason or "")
            for status in self.components
            if status.name in needed and status.state is not ComponentState.AVAILABLE
        )
        return Verdict(allowed=not reasons, reasons=reasons)


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
) -> SystemStatus:
    """The five components from the API's own storage probe, the `workers` heartbeats and the
    reports, judged on the API's clock."""
    if storage.state is not ComponentState.AVAILABLE:
        unknown = [
            ComponentStatus.unavailable(name, STORAGE_UNKNOWN_REASON)
            for name in ComponentName
            if name is not ComponentName.STORAGE
        ]
        return SystemStatus.of([storage, *unknown])
    if is_alive(latest_worker_heartbeat, server_time):
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
    return SystemStatus.of([storage, runner, *probed])
