"""The traveller simulation's placeholder rule `balanced-score`, version 1
(ARCHITECTURE.md § 6.3).

The travellers of one period choose one at a time among the options a price scheme offers
their hub pair. Nothing is random: the same inputs give equal outputs. The rule is provisional
until the model's author states the real one (Q-39). This module does not import the port.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.failure_codes import SIMULATION_CHECK_FAILED, failure_reason
from pricing_demo.domain.option_prices import option_price, option_travel_time_s
from pricing_demo.domain.read_model import OptionStationDeltaRow, RouteMode, StationBikesRow

RULE_ID = "balanced-score"
RULE_VERSION = 1
CHECK_CONSERVATION = "conservation"
CHECK_STATION_BOUNDS = "station bounds"

# Tie-break between options of equal score: PT + bike, then PT alone, then the car.
_MODE_RANK: Mapping[RouteMode, int] = {"pt_bike": 0, "pt_only": 1, "car": 2}
_MODES: tuple[RouteMode, ...] = ("pt_bike", "pt_only", "car")


@dataclass(frozen=True)
class SimulationOption:
    arc_id: str
    origin_hub: str
    destination_hub: str
    mode: RouteMode
    total_travel_time_s: float
    total_transfer_time_s: float
    bike_legs: int = 0
    car_cost_chf: float | None = None
    parking_time_min: float | None = None

    def __post_init__(self) -> None:
        if self.mode == "car" and (self.car_cost_chf is None or self.parking_time_min is None):
            raise ValueError(
                f"Option {self.arc_id} is a car option without its cost or parking time."
            )

    @property
    def travel_time_s(self) -> float:
        return option_travel_time_s(
            self.mode, self.total_travel_time_s, self.total_transfer_time_s, self.parking_time_min
        )


@dataclass(frozen=True)
class SimulationPair:
    origin_hub: str
    destination_hub: str
    travellers: int


@dataclass(frozen=True)
class SimulationInstance:
    pairs: tuple[SimulationPair, ...]
    options: tuple[SimulationOption, ...]
    stations: tuple[StationBikesRow, ...]
    deltas: tuple[OptionStationDeltaRow, ...]


@dataclass(frozen=True)
class ModelPrices:
    """The PT + bike options the model offers, at its price; an arc id absent is not offered."""

    bike_prices: Mapping[str, float]
    pt_fare_chf: float
    car_parking_fee_chf: float
    kind: ClassVar[Literal["model_prices"]] = "model_prices"


@dataclass(frozen=True)
class FlatPrice:
    """Every PT + bike option, at `bike legs x price_per_ride_chf`."""

    price_per_ride_chf: float
    pt_fare_chf: float
    car_parking_fee_chf: float
    kind: ClassVar[Literal["flat"]] = "flat"


PriceScheme = ModelPrices | FlatPrice


@dataclass(frozen=True)
class OptionOutcome:
    origin_hub: str
    destination_hub: str
    arc_id: str
    mode: RouteMode
    travellers: int
    price_paid_chf: float  # per traveller, through `option_price`
    displaced: int


@dataclass(frozen=True)
class StationEnd:
    station_id: str
    bikes: float
    capacity: float


@dataclass(frozen=True)
class SimulationOutputs:
    rule_id: str
    rule_version: int
    parameters: Mapping[str, float]
    scheme_kind: str
    travellers_per_mode: Mapping[RouteMode, int]
    options: tuple[OptionOutcome, ...]
    unserved_per_pair: tuple[tuple[str, str, int], ...]
    bike_rides: int
    bike_revenue_chf: float
    stations_end: tuple[StationEnd, ...]
    stations_empty: tuple[str, ...]
    stations_full: tuple[str, ...]
    displaced: int
    unserved: int


class SimulationCheckFailed(DomainError):
    code = SIMULATION_CHECK_FAILED

    def __init__(self, check: str) -> None:
        self.check = check
        super().__init__(failure_reason(SIMULATION_CHECK_FAILED, check=check))


@dataclass(frozen=True)
class _Offer:
    option: SimulationOption
    bike_price: float
    price: float


def _offers(
    pair: SimulationPair, instance: SimulationInstance, scheme: PriceScheme
) -> list[_Offer]:
    offers = []
    for option in instance.options:
        if (option.origin_hub, option.destination_hub) != (
            pair.origin_hub,
            pair.destination_hub,
        ):
            continue
        bike_price = 0.0
        if option.mode == "pt_bike":
            if isinstance(scheme, ModelPrices):
                if option.arc_id not in scheme.bike_prices:
                    continue
                bike_price = scheme.bike_prices[option.arc_id]
            else:
                bike_price = scheme.price_per_ride_chf
        price = option_price(
            option.mode,
            option.bike_legs,
            bike_price,
            scheme.pt_fare_chf,
            option.car_cost_chf or 0.0,
            scheme.car_parking_fee_chf,
        )
        offers.append(_Offer(option, bike_price, price))
    return offers


def _scaled(values: Sequence[float]) -> list[float]:
    low, high = min(values), max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


class _NamedRule(Protocol):
    @property
    def rule_id(self) -> str: ...
    @property
    def rule_version(self) -> int: ...
    @property
    def parameters(self) -> Mapping[str, float]: ...


@dataclass(frozen=True)
class SimulationRule:
    """ "The rule" of a simulation: the triple (rule id, rule version, rule parameters). Two
    rules are equal when the triple is equal, parameters compared as floats."""

    id: str
    version: int
    parameters: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameters", {name: float(value) for name, value in self.parameters.items()}
        )

    @classmethod
    def of(cls, rule: _NamedRule) -> "SimulationRule":
        return cls(rule.rule_id, rule.rule_version, rule.parameters)

    def record(self) -> dict[str, object]:
        """The shape of `workers.simulation_rule`."""
        return {"id": self.id, "version": self.version, "parameters": dict(self.parameters)}

    @classmethod
    def from_record(cls, record: Mapping[str, object] | None) -> "SimulationRule | None":
        """None for an absent or malformed record."""
        if not record or not isinstance(record, Mapping):
            return None
        rule_id, version, parameters = (
            record.get("id"),
            record.get("version"),
            record.get("parameters"),
        )
        if not isinstance(rule_id, str) or not isinstance(version, int):
            return None
        if isinstance(version, bool) or not isinstance(parameters, Mapping):
            return None
        values: dict[str, float] = {}
        for name, value in parameters.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            try:
                values[str(name)] = float(value)
            except OverflowError:  # an integer beyond a float, which jsonb accepts
                return None
        return cls(rule_id, version, values)


@dataclass(frozen=True)
class BalancedScore:
    """Half price, half travel time, each scaled among the traveller's own options."""

    price_weight: float = 0.5
    time_weight: float = 0.5
    rule_id: str = RULE_ID
    rule_version: int = RULE_VERSION

    @property
    def parameters(self) -> Mapping[str, float]:
        return {"price_weight": self.price_weight, "time_weight": self.time_weight}

    def _ranked(self, offers: list[_Offer]) -> list[_Offer]:
        if not offers:
            return []
        prices = _scaled([offer.price for offer in offers])
        times = _scaled([offer.option.travel_time_s for offer in offers])
        scored = sorted(
            range(len(offers)),
            key=lambda i: (
                self.price_weight * prices[i] + self.time_weight * times[i],
                _MODE_RANK[offers[i].option.mode],
                i,
            ),
        )
        return [offers[i] for i in scored]

    def simulate(self, instance: SimulationInstance, scheme: PriceScheme) -> SimulationOutputs:
        pairs = sorted(
            (pair for pair in instance.pairs if pair.travellers > 0),
            key=lambda pair: (pair.origin_hub, pair.destination_hub),
        )
        ranked = {
            (pair.origin_hub, pair.destination_hub): self._ranked(_offers(pair, instance, scheme))
            for pair in pairs
        }
        deltas: dict[str, list[tuple[str, float]]] = {}
        for row in instance.deltas:
            deltas.setdefault(row.arc_id, []).append((row.station_id, row.delta))
        capacity = {row.station_id: row.capacity for row in instance.stations}
        bikes = {row.station_id: row.inventory_start for row in instance.stations}

        taken: dict[tuple[str, str, str], list[int]] = {}  # [travellers, displaced]
        unserved: dict[tuple[str, str], int] = {}
        per_mode: dict[RouteMode, int] = dict.fromkeys(_MODES, 0)
        offer_of: dict[tuple[str, str, str], _Offer] = {}

        def available(option: SimulationOption) -> bool:
            if option.mode != "pt_bike":
                return True
            return all(
                0 <= bikes[station] + delta <= capacity[station]
                for station, delta in deltas.get(option.arc_id, [])
            )

        remaining = {(pair.origin_hub, pair.destination_hub): pair.travellers for pair in pairs}
        while any(remaining.values()):
            for key in sorted(remaining):
                if remaining[key] == 0:
                    continue
                remaining[key] -= 1
                chosen: _Offer | None = None
                refused = False
                for offer in ranked[key]:
                    if available(offer.option):
                        chosen = offer
                        break
                    refused = True
                if chosen is None:
                    unserved[key] = unserved.get(key, 0) + 1
                else:
                    option = chosen.option
                    for station, delta in deltas.get(option.arc_id, []):
                        if option.mode == "pt_bike":
                            bikes[station] += delta
                    slot = (*key, option.arc_id)
                    offer_of[slot] = chosen
                    counts = taken.setdefault(slot, [0, 0])
                    counts[0] += 1
                    counts[1] += 1 if refused else 0
                    per_mode[option.mode] += 1
                for station, count in bikes.items():
                    if not 0 <= count <= capacity[station]:
                        raise SimulationCheckFailed(CHECK_STATION_BOUNDS)

        total = sum(pair.travellers for pair in pairs)
        if sum(per_mode.values()) + sum(unserved.values()) != total:
            raise SimulationCheckFailed(CHECK_CONSERVATION)

        outcomes = []
        for option in instance.options:
            slot = (option.origin_hub, option.destination_hub, option.arc_id)
            if slot in taken:
                outcomes.append(
                    OptionOutcome(
                        option.origin_hub,
                        option.destination_hub,
                        option.arc_id,
                        option.mode,
                        taken[slot][0],
                        offer_of[slot].price,
                        taken[slot][1],
                    )
                )
        rides = 0
        revenue = 0.0
        for slot, (count, _) in taken.items():
            offer = offer_of[slot]
            if offer.option.mode == "pt_bike":
                rides += offer.option.bike_legs * count
                revenue += offer.option.bike_legs * offer.bike_price * count
        return SimulationOutputs(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            parameters=self.parameters,
            scheme_kind=scheme.kind,
            travellers_per_mode=per_mode,
            options=tuple(outcomes),
            unserved_per_pair=tuple((o, d, n) for (o, d), n in sorted(unserved.items())),
            bike_rides=rides,
            bike_revenue_chf=revenue,
            stations_end=tuple(
                StationEnd(row.station_id, bikes[row.station_id], row.capacity)
                for row in instance.stations
            ),
            stations_empty=tuple(
                row.station_id for row in instance.stations if bikes[row.station_id] < 1
            ),
            stations_full=tuple(
                row.station_id
                for row in instance.stations
                if bikes[row.station_id] > row.capacity - 1
            ),
            displaced=sum(counts[1] for counts in taken.values()),
            unserved=sum(unserved.values()),
        )
