"""The numbers of a result the demonstrator derives from the model's rows, computed once
(ARCHITECTURE.md § 6.2). Notation: `q` = flow, `p` = bike price, `z` = z value, `k` = bike legs
of the option, `δ` = the option's bike movement at a station, `inv` and `cap` = a station's
bikes at the start and its capacity.

A number the model writes is read from its rows (`source` `model`); a number computed here is
named `derived_*` and carries `source` `derived`. A change of any formula raises
`DERIVATION_VERSION`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import PricingGoals
from pricing_demo.domain.read_model import (
    HubPairRow,
    HubRow,
    OptionStationDeltaRow,
    RouteOptionRow,
    StationBikesRow,
)
from pricing_demo.domain.solves import PT_BIKE, SolveRow

DERIVATION_VERSION = 1
# The objective's terms are kept only when their sum is this close to the solver's value.
OBJECTIVE_TOLERANCE = 1e-6
MODES = ("pt_bike", "pt_only", "car")
_TYPE_MODE = {"PT+Bike": "pt_bike", "PT-Only": "pt_only", "Car": "car"}


@dataclass(frozen=True)
class Ride:
    """An option the model offers (a `PT+Bike` row) with the bike legs of its trip."""

    arc_id: str
    origin_hub: str
    destination_hub: str
    flow: float
    bike_price: float
    z_value: float
    bike_legs: int

    @property
    def rides(self) -> float:
        return self.bike_legs * self.flow


@dataclass(frozen=True)
class StationBalance:
    end_bikes: Mapping[str, float]
    empty_start: int
    full_start: int
    empty_end: int
    full_end: int


@dataclass(frozen=True)
class SimulationSummary:
    """What a stored simulation says about itself, enough for the goals of § 6.2."""

    key: str
    price_scheme: str
    rule_id: str
    rule_version: int
    rule_parameters: Mapping[str, float]
    travellers: int
    travellers_per_mode: Mapping[str, int]
    displaced: int
    unserved: int
    bike_rides: int
    bike_revenue_chf: float
    stations_empty: int
    stations_full: int
    created_at: datetime | None = None


def _n(value: float | int, unit: str, source: Any, group: Any = "headline") -> Number:
    return Number(value, unit, source, group)


def offered_rides(rows: Sequence[SolveRow], options: Sequence[RouteOptionRow]) -> list[Ride]:
    """The offered options: the package writes a `PT+Bike` row only for them."""
    legs = {option.arc_id: option.bike_legs for option in options}
    found: list[Ride] = []
    for row in rows:
        if row.type != PT_BIKE or row.bike_price is None:
            continue
        if legs.get(row.arc_id) is None:
            raise ValueError(f"The offered option {row.arc_id} has no stored bike legs.")
        found.append(
            Ride(
                row.arc_id,
                row.origin_hub,
                row.destination_hub,
                row.flow,
                row.bike_price,
                row.z_value or 0.0,
                legs[row.arc_id] or 0,
            )
        )
    return found


def derived_mean_bike_price(
    rides: Sequence[Ride],
) -> tuple[float | None, float | None, float | None]:
    """The ride-weighted mean Σ p·k·q / Σ k·q, with the lowest and the highest price. The mean
    is absent without a ride; the range is absent without an offered option."""
    if not rides:
        return None, None, None
    weight = sum(item.rides for item in rides)
    mean = sum(item.bike_price * item.rides for item in rides) / weight if weight else None
    prices = [item.bike_price for item in rides]
    return mean, min(prices), max(prices)


def derived_pair_bike_rides(
    rides: Sequence[Ride],
) -> dict[tuple[str, str], tuple[float, float | None]]:
    """Per (origin hub, destination hub) pair the bike rides Σ k·q and the ride-weighted mean
    bike price Σ p·k·q / Σ k·q, for the pairs with at least one ride."""
    by_pair: dict[tuple[str, str], list[Ride]] = {}
    for item in rides:
        by_pair.setdefault((item.origin_hub, item.destination_hub), []).append(item)
    found: dict[tuple[str, str], tuple[float, float | None]] = {}
    for pair, items in by_pair.items():
        total = sum(item.rides for item in items)
        if total > 0:
            found[pair] = (total, derived_mean_bike_price(items)[0])
    return found


def derived_revenue(rides: Sequence[Ride]) -> float:
    return sum(item.bike_price * item.rides for item in rides)


def derived_cost(rides: Sequence[Ride], cost_bike: float) -> float:
    return sum(cost_bike * item.rides for item in rides)


def derived_rides_under_cost(rides: Sequence[Ride], cost_bike: float) -> tuple[float, float]:
    """The rides priced under the cost, and all rides."""
    return (
        sum(item.rides for item in rides if item.bike_price < cost_bike),
        sum(item.rides for item in rides),
    )


def _deltas_by_arc(deltas: Sequence[OptionStationDeltaRow]) -> dict[str, list[tuple[str, float]]]:
    found: dict[str, list[tuple[str, float]]] = {}
    for item in deltas:
        found.setdefault(item.arc_id, []).append((item.station_id, item.delta))
    return found


def _empty(bikes: float) -> bool:
    return bikes < 1


def _full(bikes: float, capacity: float) -> bool:
    return bikes > capacity - 1


def derived_station_balance(
    stations: Sequence[StationBikesRow],
    deltas: Sequence[OptionStationDeltaRow],
    rides: Sequence[Ride],
) -> StationBalance:
    """A station is empty below 1 bike and full above its capacity - 1 (provisional, Q-31)."""
    by_arc = _deltas_by_arc(deltas)
    end = {item.station_id: item.inventory_start for item in stations}
    for ride in rides:
        for station, delta in by_arc.get(ride.arc_id, []):
            if station in end:
                end[station] += ride.flow * delta
    return StationBalance(
        end,
        sum(1 for item in stations if _empty(item.inventory_start)),
        sum(1 for item in stations if _full(item.inventory_start, item.capacity)),
        sum(1 for item in stations if _empty(end[item.station_id])),
        sum(1 for item in stations if _full(end[item.station_id], item.capacity)),
    )


def derived_hub_rides(
    hubs: Sequence[HubRow],
    deltas: Sequence[OptionStationDeltaRow],
    rides: Sequence[Ride],
) -> dict[str, tuple[float, float]]:
    """Per hub, the bike rides that start and end at its stations: Σ q·max(0, -δ) and
    Σ q·max(0, δ)."""
    by_arc = _deltas_by_arc(deltas)
    found: dict[str, tuple[float, float]] = {}
    for hub in hubs:
        own = set(hub.bike_station_ids)
        starting = ending = 0.0
        for ride in rides:
            for station, delta in by_arc.get(ride.arc_id, []):
                if station in own:
                    starting += ride.flow * max(0.0, -delta)
                    ending += ride.flow * max(0.0, delta)
        found[hub.hub_id] = (starting, ending)
    return found


def derived_objective_terms(
    rides: Sequence[Ride],
    deltas: Sequence[OptionStationDeltaRow],
    stations: Sequence[StationBikesRow],
    goals: PricingGoals,
) -> dict[str, float]:
    """The four terms of the solver's objective (`solver.py:577-589`): the objective is
    ridership + revenue - cost + station balance."""
    by_arc = _deltas_by_arc(deltas)
    known = {item.station_id: item for item in stations}
    balance = 0.0
    for ride in rides:
        for station, delta in by_arc.get(ride.arc_id, []):
            found = known.get(station)
            if found is None or found.capacity <= 0:
                continue
            balance += ride.flow * delta * (1 - found.inventory_start / found.capacity)
    return {
        "ridership": goals.ridership_weight * sum(item.flow for item in rides),
        "revenue": sum(item.z_value * item.bike_legs for item in rides),
        "cost": derived_cost(rides, goals.cost_bike_chf),
        "station_balance": goals.station_balance_weight * balance,
    }


def objective_residual(terms_sum: float, objective: float) -> float:
    return abs(terms_sum - objective) / max(1.0, abs(objective))


def terms_total(terms: Mapping[str, float]) -> float:
    return terms["ridership"] + terms["revenue"] - terms["cost"] + terms["station_balance"]


@dataclass(frozen=True)
class PairNumbers:
    origin_hub: str
    destination_hub: str
    travellers: Mapping[str, Number]
    mean_bike_price: Number | None
    min_bike_price: Number | None
    max_bike_price: Number | None


@dataclass(frozen=True)
class HubNumbers:
    hub_id: str
    rides_starting: Number
    rides_ending: Number
    mean_bike_price: Number | None


def _number_record(item: Number | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"value": item.value, "unit": item.unit, "source": item.source, "group": item.group}


def _number_from(record: Mapping[str, Any] | None) -> Number | None:
    if record is None:
        return None
    return Number(record["value"], record["unit"], record["source"], record["group"])


def _required(record: Mapping[str, Any]) -> Number:
    found = _number_from(record)
    assert found is not None
    return found


@dataclass(frozen=True)
class ResultNumbers:
    """Every number of a solve's result. `objective_terms` is None when their sum differs from
    the objective by more than the tolerance (or there is no objective): the residual says by
    how much."""

    numbers: Mapping[str, Number]
    pairs: tuple[PairNumbers, ...]
    hubs: tuple[HubNumbers, ...]
    objective_terms: Mapping[str, Number] | None
    objective_residual: float | None

    def record(self) -> dict[str, Any]:
        return {
            "numbers": {name: _number_record(item) for name, item in self.numbers.items()},
            "pairs": [
                {
                    "origin_hub": pair.origin_hub,
                    "destination_hub": pair.destination_hub,
                    "travellers": {m: _number_record(i) for m, i in pair.travellers.items()},
                    "mean_bike_price": _number_record(pair.mean_bike_price),
                    "min_bike_price": _number_record(pair.min_bike_price),
                    "max_bike_price": _number_record(pair.max_bike_price),
                }
                for pair in self.pairs
            ],
            "hubs": [
                {
                    "hub_id": hub.hub_id,
                    "rides_starting": _number_record(hub.rides_starting),
                    "rides_ending": _number_record(hub.rides_ending),
                    "mean_bike_price": _number_record(hub.mean_bike_price),
                }
                for hub in self.hubs
            ],
            "objective_terms": None
            if self.objective_terms is None
            else {name: _number_record(item) for name, item in self.objective_terms.items()},
            "objective_residual": self.objective_residual,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ResultNumbers":
        terms = record["objective_terms"]
        return cls(
            {name: _required(item) for name, item in record["numbers"].items()},
            tuple(
                PairNumbers(
                    pair["origin_hub"],
                    pair["destination_hub"],
                    {m: _required(i) for m, i in pair["travellers"].items()},
                    _number_from(pair["mean_bike_price"]),
                    _number_from(pair["min_bike_price"]),
                    _number_from(pair["max_bike_price"]),
                )
                for pair in record["pairs"]
            ),
            tuple(
                HubNumbers(
                    hub["hub_id"],
                    _required(hub["rides_starting"]),
                    _required(hub["rides_ending"]),
                    _number_from(hub["mean_bike_price"]),
                )
                for hub in record["hubs"]
            ),
            None if terms is None else {name: _required(item) for name, item in terms.items()},
            record["objective_residual"],
        )


def _price_number(value: float | None, source: str) -> Number | None:
    return None if value is None else _n(value, "chf_per_bike_leg", source)


def summarise_result(
    rows: Sequence[SolveRow],
    options: Sequence[RouteOptionRow],
    deltas: Sequence[OptionStationDeltaRow],
    station_bikes: Sequence[StationBikesRow],
    hubs: Sequence[HubRow],
    hub_pairs: Sequence[HubPairRow],
    goals: PricingGoals,
    objective_value: float | None,
) -> ResultNumbers:
    rides = offered_rides(rows, options)
    cost_bike = float(goals.cost_bike_chf)
    flows = dict.fromkeys(MODES, 0.0)
    pair_flows: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        mode = _TYPE_MODE[row.type]
        flows[mode] += row.flow
        by_mode = pair_flows.setdefault(
            (row.origin_hub, row.destination_hub), dict.fromkeys(MODES, 0.0)
        )
        by_mode[mode] += row.flow
    demand = sum(item.demand for item in hub_pairs)

    numbers: dict[str, Number] = {"ridership": _n(flows["pt_bike"], "travellers", "model")}
    for mode in MODES:
        numbers[f"travellers_{mode}"] = _n(flows[mode], "travellers", "model")
        if demand:
            numbers[f"modal_split_{mode}"] = _n(flows[mode] / demand, "share", "model")
    mean, low, high = derived_mean_bike_price(rides)
    if low is not None and high is not None:
        numbers["bike_price_min"] = _n(low, "chf_per_bike_leg", "model")
        numbers["bike_price_max"] = _n(high, "chf_per_bike_leg", "model")
    if mean is not None:
        numbers["mean_bike_price"] = _n(mean, "chf_per_bike_leg", "derived")
    revenue = derived_revenue(rides)
    cost = derived_cost(rides, cost_bike)
    under, total_rides = derived_rides_under_cost(rides, cost_bike)
    numbers["revenue"] = _n(revenue, "chf", "derived")
    numbers["cost"] = _n(cost, "chf", "derived")
    numbers["profit"] = _n(revenue - cost, "chf", "derived")
    numbers["bike_rides"] = _n(total_rides, "bike_rides", "derived")
    numbers["rides_under_cost"] = _n(under, "bike_rides", "derived")
    if total_rides:
        numbers["rides_under_cost_share"] = _n(under / total_rides, "share", "derived")
    balance = derived_station_balance(station_bikes, deltas, rides)
    numbers["stations_empty_end"] = _n(balance.empty_end, "stations", "derived")
    numbers["stations_full_end"] = _n(balance.full_end, "stations", "derived")
    numbers["stations_empty_start"] = _n(balance.empty_start, "stations", "input")
    numbers["stations_full_start"] = _n(balance.full_start, "stations", "input")
    offered_pairs = {(item.origin_hub, item.destination_hub) for item in rides}
    numbers["hub_pairs_with_bike_option"] = _n(len(offered_pairs), "hub_pairs", "model")

    terms: dict[str, Number] | None = None
    residual: float | None = None
    if objective_value is not None:
        raw = derived_objective_terms(rides, deltas, station_bikes, goals)
        residual = objective_residual(terms_total(raw), objective_value)
        if residual <= OBJECTIVE_TOLERANCE:
            terms = {
                name: _n(value, "objective", "derived", "advanced") for name, value in raw.items()
            }

    pairs = []
    for pair in sorted(hub_pairs, key=lambda item: (item.origin_hub, item.destination_hub)):
        key = (pair.origin_hub, pair.destination_hub)
        own = [item for item in rides if (item.origin_hub, item.destination_hub) == key]
        pair_mean, pair_low, pair_high = derived_mean_bike_price(own)
        found = pair_flows.get(key, dict.fromkeys(MODES, 0.0))
        pairs.append(
            PairNumbers(
                pair.origin_hub,
                pair.destination_hub,
                {mode: _n(found[mode], "travellers", "model") for mode in MODES},
                _price_number(pair_mean, "derived"),
                _price_number(pair_low, "derived"),
                _price_number(pair_high, "derived"),
            )
        )
    hub_rides = derived_hub_rides(hubs, deltas, rides)
    hub_numbers = []
    for hub in sorted(hubs, key=lambda item: item.hub_id):
        starting, ending = hub_rides[hub.hub_id]
        hub_mean, _, _ = derived_mean_bike_price(
            [item for item in rides if item.origin_hub == hub.hub_id]
        )
        hub_numbers.append(
            HubNumbers(
                hub.hub_id,
                _n(starting, "bike_rides", "derived"),
                _n(ending, "bike_rides", "derived"),
                _price_number(hub_mean, "derived"),
            )
        )
    return ResultNumbers(numbers, tuple(pairs), tuple(hub_numbers), terms, residual)


def simulated_goals(summary: SimulationSummary, cost_bike_chf: float) -> dict[str, Number]:
    """The goals of § 6.2 "Goals against the flat price" for one simulation."""
    cost = cost_bike_chf * summary.bike_rides
    goals = {
        "ridership": _n(summary.travellers_per_mode.get("pt_bike", 0), "travellers", "simulation"),
        "revenue": _n(summary.bike_revenue_chf, "chf", "simulation"),
        "cost": _n(cost, "chf", "simulation"),
        "profit": _n(summary.bike_revenue_chf - cost, "chf", "simulation"),
    }
    if summary.bike_rides:
        goals["mean_bike_price"] = _n(
            summary.bike_revenue_chf / summary.bike_rides, "chf_per_bike_leg", "simulation"
        )
    goals["stations_empty"] = _n(summary.stations_empty, "stations", "simulation")
    goals["stations_full"] = _n(summary.stations_full, "stations", "simulation")
    return goals


# The goals of § 6.2, in the order a result lists them, with the number of the model's result
# each one is compared with.
GOAL_ORDER = (
    "ridership",
    "revenue",
    "cost",
    "profit",
    "mean_bike_price",
    "stations_empty",
    "stations_full",
)
MODEL_GOAL_NUMBERS = {
    "ridership": "ridership",
    "revenue": "revenue",
    "cost": "cost",
    "profit": "profit",
    "mean_bike_price": "mean_bike_price",
    "stations_empty": "stations_empty_end",
    "stations_full": "stations_full_end",
}
# The numbers a result shows first, and the ones that make the model's own split.
HEADLINE_NUMBERS = (
    "ridership",
    "mean_bike_price",
    "bike_price_min",
    "bike_price_max",
    "profit",
    "revenue",
    "cost",
    "bike_rides",
    "rides_under_cost",
    "rides_under_cost_share",
    "stations_empty_end",
    "stations_full_end",
    "stations_empty_start",
    "stations_full_start",
)
SPLIT_NUMBERS = tuple(
    f"{prefix}_{mode}" for prefix in ("travellers", "modal_split") for mode in MODES
)

_PARAMETER_UNITS = {
    "cost_bike": "chf",
    "P_bar": "chf",
    "ridership_weight": "weight",
    "theta": "weight",
    "pt_price": "chf",
    "parking_fee": "chf",
    "max_displayed_alternatives": "options",
}


def parameter_numbers(
    goals: Mapping[str, float | int], names: Mapping[str, str]
) -> dict[str, Number]:
    """The goals a solve ran with under the package's names (advanced view only)."""
    return {
        package: _n(goals[goal], _PARAMETER_UNITS[package], "input", "advanced")
        for goal, package in names.items()
    }
