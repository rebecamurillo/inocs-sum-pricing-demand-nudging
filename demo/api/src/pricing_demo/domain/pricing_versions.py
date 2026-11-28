"""Pricing versions: the goals of one built instance version, saved under a letter."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from pricing_demo.domain.city_instances import Number, VersionStatus
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.runs import RunState

# The package's `OptimizerParams` defaults (cost, lowest price, ridership weight, station
# balance weight), provisional until the author answers follow-up Q-17.
DEFAULT_GOALS: tuple[Number, Number, Number, Number] = (0.60, 0.60, 8.0, 0.5)
# What a first pricing version keeps: fare, parking fee, options shown, flat price per ride.
FALLBACK_KEPT: tuple[Number, Number, Number, Number] = (2.0, 2.8, 10, 1.00)

PricingState = Literal["draft", "queued", "running", "failed", "cancelled", "result"]

_RUN_STATES: dict[RunState, PricingState] = {
    RunState.QUEUED: "queued",
    RunState.RUNNING: "running",
    RunState.FAILED: "failed",
    RunState.CANCELLED: "cancelled",
    RunState.SUCCEEDED: "result",
}


class PricingVersionNotFound(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"There is no pricing version {version_id}.")


class InstanceNotBuilt(DomainError):
    def __init__(self, instance_version_id: str) -> None:
        self.instance_version_id = instance_version_id
        super().__init__(
            f"The instance version {instance_version_id} is not built: "
            "a pricing version needs a successful build."
        )


class UnknownBasedOn(DomainError):
    def __init__(self, based_on_id: str) -> None:
        self.based_on_id = based_on_id
        super().__init__(f"{based_on_id} is not a pricing version of the same instance version.")


class HasPricingVersions(DomainError):
    def __init__(self, pricing_version_ids: list[str]) -> None:
        self.pricing_version_ids = tuple(pricing_version_ids)
        super().__init__(
            f"{len(self.pricing_version_ids)} pricing version(s) belong to it: "
            f"{', '.join(self.pricing_version_ids)}."
        )


class AlreadyRun(DomainError):
    """The version is sealed and its last run succeeded: its result exists."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The pricing version {version_id} already has its result.")


class NoResult(DomainError):
    """The version has no succeeded pricing run: there is nothing to simulate again."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The pricing version {version_id} has no result yet.")


class ResultNotFound(DomainError):
    """A result route was asked for a version whose pricing run and both simulations have not
    all succeeded."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The pricing version {version_id} has no result yet.")


class IsShowcase(DomainError):
    """The version is the showcase: it cannot be deleted while it is marked."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The pricing version {version_id} is the showcase.")


class NoShowcase(DomainError):
    def __init__(self) -> None:
        super().__init__("No pricing version is marked as the showcase.")


class SimulationCurrent(DomainError):
    """Both schemes are already simulated with the rule the live worker uses."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(
            f"The pricing version {version_id} is already simulated with the current rule."
        )


class SealedWithoutRun(DomainError):
    """A sealed pricing version always has a run: sealing and queueing are one transaction."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The pricing version {version_id} is sealed and has no run.")


@dataclass(frozen=True)
class PricingGoals:
    """The eight values of a pricing version. Whatever was sent is kept: a value that breaks a
    rule is reported by `check_pricing_rules`, never corrected."""

    cost_bike_chf: Number
    lowest_price_chf: Number
    ridership_weight: Number
    station_balance_weight: Number
    pt_fare_chf: Number
    car_parking_fee_chf: Number
    max_displayed_options: Number
    flat_price_per_ride_chf: Number
    flat_price_kind: Literal["per_ride"] = "per_ride"

    def as_dict(self) -> dict[str, Number]:
        return {name: getattr(self, name) for name in GOAL_NAMES}

    def replacing(self, changes: dict[str, Number]) -> "PricingGoals":
        return replace(self, **changes)  # type: ignore[arg-type]


GOAL_NAMES = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
    "flat_price_per_ride_chf",
)


@dataclass(frozen=True)
class PricingVersion:
    id: str
    instance_version_id: str
    letter: str
    name: str
    status: VersionStatus
    based_on_id: str | None
    goals: PricingGoals
    created_at: datetime
    sealed_at: datetime | None = None
    # The sealed version whose fare, parking fee, options shown and flat price this draft kept;
    # None when it started from the fallback values or that version was deleted.
    kept_from_id: str | None = None


@dataclass(frozen=True)
class PricingVersionSummary:
    """A version with the state of its last run, as the list shows it."""

    version: PricingVersion
    state: PricingState


def pricing_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 27 -> AB (spreadsheet order)."""
    letters = ""
    number = index + 1
    while number > 0:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def pricing_version_id(instance_version_id: str, letter: str) -> str:
    return f"{instance_version_id}.{letter}"


def instance_version_of(pricing_version_id: str) -> str:
    """`geneva-3km.v1.B` -> `geneva-3km.v1` (ids are dotted slugs, ARCHITECTURE.md 5.1)."""
    return pricing_version_id.rsplit(".", 1)[0]


def city_instance_of(instance_version_id: str) -> str:
    """`geneva-3km.v1` -> `geneva-3km`."""
    return instance_version_id.rsplit(".", 1)[0]


def new_draft_goals(previous_sealed: PricingGoals | None) -> PricingGoals:
    """The four goals start from the defaults; the fare, parking fee, options shown and flat
    price are kept from the last sealed pricing version of the instance version."""
    cost, lowest, ridership, balance = DEFAULT_GOALS
    if previous_sealed is None:
        fare, parking, options, flat = FALLBACK_KEPT
    else:
        fare = previous_sealed.pt_fare_chf
        parking = previous_sealed.car_parking_fee_chf
        options = previous_sealed.max_displayed_options
        flat = previous_sealed.flat_price_per_ride_chf
    return PricingGoals(cost, lowest, ridership, balance, fare, parking, options, flat)


def duplicated_goals(source: PricingGoals) -> PricingGoals:
    return replace(source)


def pricing_version_state(
    status: VersionStatus, last_run_state: RunState | None, version_id: str
) -> PricingState:
    if status == "draft":
        return "draft"
    if last_run_state is None:
        raise SealedWithoutRun(version_id)
    return _RUN_STATES[last_run_state]
