from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pricing_demo.domain.errors import DomainError


class ComponentName(StrEnum):
    """The parts of the system a run depends on, in the order they are reported."""

    STORAGE = "storage"
    PRICING_MODEL = "pricing_model"
    SOLVER = "solver"
    TRIP_PLANNER = "trip_planner"


class InvalidComponentStatus(DomainError):
    pass


class IncompleteSystemStatus(DomainError):
    pass


@dataclass(frozen=True)
class ComponentStatus:
    name: ComponentName
    available: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.available and self.reason is not None:
            raise InvalidComponentStatus(f"{self.name}: an available component has no reason.")
        if not self.available and not self.reason:
            raise InvalidComponentStatus(f"{self.name}: an unavailable component needs a reason.")

    @classmethod
    def ready(cls, name: ComponentName) -> "ComponentStatus":
        return cls(name=name, available=True)

    @classmethod
    def unavailable(cls, name: ComponentName, reason: str) -> "ComponentStatus":
        return cls(name=name, available=False, reason=reason)


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
    def can_read_stored_results(self) -> bool:
        return self._is_available(ComponentName.STORAGE)

    @property
    def can_start_runs(self) -> bool:
        return all(status.available for status in self.components)

    def _is_available(self, name: ComponentName) -> bool:
        return any(status.available for status in self.components if status.name == name)
