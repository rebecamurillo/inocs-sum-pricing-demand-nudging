"""City instances: the parameters of a city, saved as numbered versions that never change."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date, datetime, time
from typing import Literal

from pricing_demo.domain.city_datasets import CityDataset, Preset, RoutingMoment
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.package_fingerprint import instance_defaults
from pricing_demo.domain.runs import RunState

Number = int | float
VersionStatus = Literal["draft", "sealed"]

# Provisional until the author answers follow-up Q-29: one period, Monday 08:00-09:00.
FIRST_PERIOD_KEY = "mon-08"
FIRST_PERIOD_LABEL = "Monday 08:00–09:00"  # noqa: RUF001  # the en dash of the product text
# The package's default seed is None and the column is not null: the demonstrator shows 42.
DEFAULT_SEED = 42


class CityInstanceNameTaken(DomainError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A city instance named {name} (or with the same identifier) exists.")


class InvalidInstanceName(DomainError):
    def __init__(self, name: str) -> None:
        super().__init__(f"The name {name!r} has no letter or digit to build an identifier from.")


class DraftExists(DomainError):
    def __init__(self, instance_id: str, draft_id: str) -> None:
        self.instance_id = instance_id
        self.draft_id = draft_id
        super().__init__(f"{instance_id} already has the draft {draft_id}.")


class VersionSealed(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The version {version_id} is saved and cannot change.")


class InstanceVersionNotFound(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"There is no instance version {version_id}.")


class CityInstanceNotFound(DomainError):
    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        super().__init__(f"There is no city instance {instance_id}.")


WHOLE_NUMBER_PARAMETERS = ("seed", "fixed_capacity", "min_demand", "max_demand")


@dataclass(frozen=True)
class InstanceParameters:
    """The 14 values of an instance version. Whatever was sent is kept: a value that breaks a
    rule is reported by `check_rules`, never corrected, so any of them may hold a float."""

    center_lat: Number
    center_lon: Number
    radius_m: Number
    clustering_threshold_m: Number
    clustering_buffer_m: Number
    min_od_distance_m: Number
    seed: Number
    fixed_capacity: Number
    min_demand: Number
    max_demand: Number
    min_inventory_pct: Number
    max_inventory_pct: Number
    min_park_time_min: Number
    max_park_time_min: Number

    def __post_init__(self) -> None:
        # A whole number in a count column reads the same as the integer, whichever way it was
        # sent or stored; a 1.5 stays a 1.5.
        for name in WHOLE_NUMBER_PARAMETERS:
            value = getattr(self, name)
            if isinstance(value, float) and value.is_integer():
                object.__setattr__(self, name, int(value))

    def as_dict(self) -> dict[str, Number]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    def replacing(self, changes: Mapping[str, Number]) -> "InstanceParameters":
        return replace(self, **changes)


PARAMETER_NAMES = tuple(item.name for item in fields(InstanceParameters))


@dataclass(frozen=True)
class ParameterChange:
    parameter: str
    before: Number
    after: Number


@dataclass(frozen=True)
class CityInstance:
    id: str
    name: str
    dataset_id: str
    next_number: int
    created_at: datetime


@dataclass(frozen=True)
class InstanceVersion:
    id: str
    instance_id: str
    number: int
    based_on_id: str | None
    status: VersionStatus
    parameters: InstanceParameters
    created_at: datetime
    sealed_at: datetime | None = None


@dataclass(frozen=True)
class InstancePeriod:
    id: str
    instance_version_id: str
    key: str
    label: str
    weekday: int
    start_time: time
    end_time: time
    routing_date: date
    routing_time: time
    arrive_by: bool
    routing_date_provisional: bool


@dataclass(frozen=True)
class InstanceWithVersions:
    instance: CityInstance
    versions: Sequence[InstanceVersion]


def instance_slug(name: str) -> str:
    """`Geneva 3 km` -> `geneva-3km`: lowercase ASCII, a space between a digit and a letter
    removed, every other run outside `a-z0-9` a hyphen."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    lowered = re.sub(r"(?<=\d) +(?=[a-z])", "", folded.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        raise InvalidInstanceName(name)
    return slug


def version_id(instance_id: str, number: int) -> str:
    return f"{instance_id}.v{number}"


def first_period(version: str, dataset: CityDataset) -> InstancePeriod:
    moment: RoutingMoment = dataset.routing_moment
    return InstancePeriod(
        id=f"{version}.{FIRST_PERIOD_KEY}",
        instance_version_id=version,
        key=FIRST_PERIOD_KEY,
        label=FIRST_PERIOD_LABEL,
        weekday=0,
        start_time=time(8),
        end_time=time(9),
        routing_date=moment.date,
        routing_time=moment.time,
        arrive_by=moment.arrive_by,
        routing_date_provisional=moment.provisional,
    )


def parameters_from_defaults(
    defaults: Mapping[str, Mapping[str, object]], preset: Preset
) -> InstanceParameters:
    values = instance_defaults(defaults)
    if values.get("seed") is None:
        values["seed"] = DEFAULT_SEED
    return InstanceParameters(
        center_lat=preset.centre_lat,
        center_lon=preset.centre_lon,
        radius_m=preset.radius_m,
        **values,  # type: ignore[arg-type]
    )


def what_changes(before: InstanceParameters, after: InstanceParameters) -> list[ParameterChange]:
    """Each parameter whose value differs, in column order; 20 and 20.0 are the same value."""
    old, new = before.as_dict(), after.as_dict()
    return [
        ParameterChange(name, old[name], new[name])
        for name in PARAMETER_NAMES
        if old[name] != new[name]
    ]


_BUILD_STATES = {
    RunState.QUEUED: "queued",
    RunState.RUNNING: "building",
    RunState.SUCCEEDED: "ready",
    RunState.FAILED: "failed",
    RunState.CANCELLED: "cancelled",
}


def version_state(status: VersionStatus, latest_build_state: RunState | None) -> str:
    """What a client reads as a version's state: `draft`, then the state of its latest build
    (`queued`, `building`, `ready`, `failed`, `cancelled`), `sealed` while no build exists."""
    if status == "draft":
        return "draft"
    if latest_build_state is None:
        return "sealed"
    return _BUILD_STATES[latest_build_state]
