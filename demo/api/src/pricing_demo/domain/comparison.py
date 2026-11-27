"""The comparison of two to four pricing versions of one instance version (ARCHITECTURE.md
§ 6.1 to § 6.3, § 7 `/comparisons`).

Nothing here is stored: a comparison is computed from the stored results on each request. Every
number keeps its source (AR-16). The best value is judged among the compared versions only,
within one row of one group, never against a flat column.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pricing_demo.domain.derived_result import ResultNumbers, SimulationSummary, simulated_goals
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import GOAL_NAMES, PricingGoals

MIN_VERSIONS = 2
MAX_VERSIONS = 4

Direction = Literal["lowest", "highest"]
# The rows the insight title and the mockup mark, wherever the row exists.
BEST_DIRECTIONS: Mapping[str, Direction] = {
    "share_car": "lowest",
    "ridership": "highest",
    "profit": "highest",
    "stations_empty_or_full": "lowest",
}

GROUP_ORDER = ("simulated", "model", "derived", "goals_that_differ", "solver")
MODE_ROWS = {"share_car": "car", "share_pt_only": "pt_only", "share_pt_bike": "pt_bike"}
# Of the eight goals, the five that the comparison lists when they differ between versions.
DIFFERING_GOALS = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "flat_price_per_ride_chf",
)
_GOAL_UNITS = {
    "cost_bike_chf": "chf",
    "lowest_price_chf": "chf",
    "pt_fare_chf": "chf",
    "car_parking_fee_chf": "chf",
    "flat_price_per_ride_chf": "chf",
    "ridership_weight": "none",
    "station_balance_weight": "none",
    "max_displayed_options": "none",
}
_PRICE_UNIT = "chf_per_bike_leg"
_TOLERANCE = 1e-9


class DifferentInstances(DomainError):
    def __init__(self, instance_version_ids: Sequence[str]) -> None:
        self.instance_version_ids = tuple(instance_version_ids)
        super().__init__(
            "The pricing versions belong to different instance versions: "
            f"{', '.join(self.instance_version_ids)}."
        )


class VersionCountOutOfRange(DomainError):
    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"A comparison takes {MIN_VERSIONS} to {MAX_VERSIONS} pricing versions, not {count}."
        )


@dataclass(frozen=True)
class ComparedVersion:
    """What the comparison reads of one finished version."""

    letter: str
    goals: PricingGoals
    numbers: ResultNumbers
    model_prices: SimulationSummary
    flat: SimulationSummary
    flat_rule_current: bool
    solve_key: str
    advanced: Mapping[str, Number]
    bike_options_offered: int

    @property
    def flat_key(self) -> str:
        return self.flat.key


@dataclass(frozen=True)
class ComparisonRow:
    """`values` has a key per compared letter, `changes` and `flats` are filled for the
    simulated group only; a value a version does not have is None."""

    key: str
    values: Mapping[str, Number | None]
    changes: Mapping[str, Number | None]
    flats: Mapping[str, Number | None]
    best: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonGroup:
    name: str
    rows: tuple[ComparisonRow, ...]


@dataclass(frozen=True)
class FlatReference:
    """One flat simulation, shared by every version whose flat price, fare, parking fee and
    rule are the same (the storage key of § 6.3)."""

    id: str
    letters: tuple[str, ...]
    values: Mapping[str, Number]
    rule_id: str
    rule_version: int
    rule_parameters: Mapping[str, float]
    rule_current: bool


@dataclass(frozen=True)
class PairDifference:
    origin_hub: str
    destination_hub: str
    mean_price_a: Number
    mean_price_b: Number
    price_difference: Number
    travellers_a: Number
    travellers_b: Number
    travellers_difference: Number


@dataclass(frozen=True)
class HubDifference:
    hub_id: str
    mean_price_a: Number | None
    mean_price_b: Number | None
    price_difference: Number | None
    price_b_minus_flat: Number | None
    rides_starting_a: Number | None
    rides_starting_b: Number | None
    rides_starting_difference: Number | None


def check_version_count(count: int) -> None:
    if not MIN_VERSIONS <= count <= MAX_VERSIONS:
        raise VersionCountOutOfRange(count)


def goal_numbers(goals: PricingGoals) -> dict[str, Number]:
    """The eight goals of a version as inputs, in the order of `GOAL_NAMES`."""
    return {
        name: Number(goals.as_dict()[name], _GOAL_UNITS[name], "input", "headline")
        for name in GOAL_NAMES
    }


def best_letters(values: Mapping[str, Number | None], direction: Direction) -> tuple[str, ...]:
    """The letters holding the best value; none when every value is equal (or fewer than two
    versions have one). A tie marks every tied letter."""
    found = {letter: item.value for letter, item in values.items() if item is not None}
    if len(found) < 2:
        return ()
    best = min(found.values()) if direction == "lowest" else max(found.values())
    if all(
        math.isclose(item, best, rel_tol=_TOLERANCE, abs_tol=_TOLERANCE) for item in found.values()
    ):
        return ()
    return tuple(
        letter
        for letter, item in found.items()
        if math.isclose(item, best, rel_tol=_TOLERANCE, abs_tol=_TOLERANCE)
    )


def flat_references(versions: Sequence[ComparedVersion]) -> tuple[FlatReference, ...]:
    """One reference per flat simulation key, in the order of the first version it serves."""
    served: dict[str, list[ComparedVersion]] = {}
    for version in versions:
        served.setdefault(version.flat_key, []).append(version)
    found = []
    for key, group in served.items():
        first = group[0]
        goals = goal_numbers(first.goals)
        found.append(
            FlatReference(
                key,
                tuple(item.letter for item in group),
                {
                    name: goals[name]
                    for name in ("flat_price_per_ride_chf", "pt_fare_chf", "car_parking_fee_chf")
                },
                first.flat.rule_id,
                first.flat.rule_version,
                dict(first.flat.rule_parameters),
                first.flat_rule_current,
            )
        )
    return tuple(found)


def identical_solve_groups(versions: Sequence[ComparedVersion]) -> tuple[tuple[str, ...], ...]:
    """The letters of versions that share one stored solve, groups of two or more."""
    by_solve: dict[str, list[str]] = {}
    for version in versions:
        by_solve.setdefault(version.solve_key, []).append(version.letter)
    return tuple(tuple(letters) for letters in by_solve.values() if len(letters) > 1)


def _difference(b: Number, a: Number, unit: str | None = None) -> Number:
    return Number(b.value - a.value, unit or b.unit, "derived", "headline")


def derived_pair_differences(a: ComparedVersion, b: ComparedVersion) -> tuple[PairDifference, ...]:
    """Per hub pair with a mean bike price in both versions, `b` minus `a`, the largest price
    difference first. Versions that share one solve differ nowhere: no pair is listed."""
    if a.solve_key == b.solve_key:
        return ()
    in_a = {(item.origin_hub, item.destination_hub): item for item in a.numbers.pairs}
    found = []
    for pair in b.numbers.pairs:
        other = in_a.get((pair.origin_hub, pair.destination_hub))
        if other is None or other.mean_bike_price is None or pair.mean_bike_price is None:
            continue
        riders_a = other.travellers["pt_bike"]
        riders_b = pair.travellers["pt_bike"]
        found.append(
            PairDifference(
                pair.origin_hub,
                pair.destination_hub,
                _derived(other.mean_bike_price),
                _derived(pair.mean_bike_price),
                _difference(pair.mean_bike_price, other.mean_bike_price),
                riders_a,
                riders_b,
                _difference(riders_b, riders_a),
            )
        )
    return tuple(
        sorted(
            found,
            key=lambda item: (
                -abs(item.price_difference.value),
                item.origin_hub,
                item.destination_hub,
            ),
        )
    )


def _derived(item: Number) -> Number:
    return Number(item.value, item.unit, "derived", "headline")


def derived_hub_differences(a: ComparedVersion, b: ComparedVersion) -> tuple[HubDifference, ...]:
    """Per hub: the mean bike price from it in each version and `b` minus `a`; `b`'s mean minus
    `b`'s flat price per ride; the bike rides starting there in each version and `b` minus `a`."""
    hubs_a = {item.hub_id: item for item in a.numbers.hubs}
    hubs_b = {item.hub_id: item for item in b.numbers.hubs}
    flat_price = float(b.goals.flat_price_per_ride_chf)
    found = []
    for hub_id in sorted(set(hubs_a) | set(hubs_b)):
        own_a, own_b = hubs_a.get(hub_id), hubs_b.get(hub_id)
        mean_a = None if own_a is None else own_a.mean_bike_price
        mean_b = None if own_b is None else own_b.mean_bike_price
        rides_a = None if own_a is None else own_a.rides_starting
        rides_b = None if own_b is None else own_b.rides_starting
        found.append(
            HubDifference(
                hub_id,
                None if mean_a is None else _derived(mean_a),
                None if mean_b is None else _derived(mean_b),
                None if mean_a is None or mean_b is None else _difference(mean_b, mean_a),
                None
                if mean_b is None
                else Number(mean_b.value - flat_price, _PRICE_UNIT, "derived", "headline"),
                rides_a,
                rides_b,
                None if rides_a is None or rides_b is None else _difference(rides_b, rides_a),
            )
        )
    return tuple(found)


def _sim(value: float | int | None, unit: str) -> Number | None:
    return None if value is None else Number(value, unit, "simulation", "headline")


def _simulated_values(summary: SimulationSummary, cost_bike: float) -> dict[str, Number | None]:
    goals = simulated_goals(summary, cost_bike)
    values: dict[str, Number | None] = {}
    for key, mode in MODE_ROWS.items():
        share = (
            summary.travellers_per_mode.get(mode, 0) / summary.travellers
            if summary.travellers
            else None
        )
        values[key] = _sim(share, "share")
    values["ridership"] = goals["ridership"]
    values["profit"] = goals["profit"]
    values["mean_bike_price"] = goals.get("mean_bike_price")
    values["stations_empty_or_full"] = _sim(
        summary.stations_empty + summary.stations_full, "stations"
    )
    values["displaced"] = _sim(summary.displaced, "travellers")
    return values


def _change(model: Number | None, flat: Number | None, key: str) -> Number | None:
    if model is None or flat is None:
        return None
    if key in MODE_ROWS:
        return Number((model.value - flat.value) * 100, "share_points", "simulation", "headline")
    return Number(model.value - flat.value, model.unit, "simulation", "headline")


def _row(
    key: str,
    values: Mapping[str, Number | None],
    changes: Mapping[str, Number | None] | None = None,
    flats: Mapping[str, Number | None] | None = None,
) -> ComparisonRow:
    direction = BEST_DIRECTIONS.get(key)
    best = () if direction is None else best_letters(values, direction)
    return ComparisonRow(key, dict(values), dict(changes or {}), dict(flats or {}), best)


def _simulated_group(
    versions: Sequence[ComparedVersion], references: Sequence[FlatReference]
) -> ComparisonGroup:
    own = {
        item.letter: _simulated_values(item.model_prices, float(item.goals.cost_bike_chf))
        for item in versions
    }
    own_flat = {
        item.letter: _simulated_values(item.flat, float(item.goals.cost_bike_chf))
        for item in versions
    }
    by_letter = {item.letter: item for item in versions}
    # A shared reference shows the figures with the cost of the first version it serves.
    shown = {
        reference.id: _simulated_values(
            by_letter[reference.letters[0]].flat,
            float(by_letter[reference.letters[0]].goals.cost_bike_chf),
        )
        for reference in references
    }
    rows = []
    for key in next(iter(own.values())):
        rows.append(
            _row(
                key,
                {letter: values[key] for letter, values in own.items()},
                {letter: _change(own[letter][key], own_flat[letter][key], key) for letter in own},
                {reference: values[key] for reference, values in shown.items()},
            )
        )
    return ComparisonGroup("simulated", tuple(rows))


def _model_group(versions: Sequence[ComparedVersion]) -> ComparisonGroup:
    names = (
        ("share_car", "modal_split_car"),
        ("share_pt_only", "modal_split_pt_only"),
        ("share_pt_bike", "modal_split_pt_bike"),
        ("ridership", "ridership"),
        ("bike_price_min", "bike_price_min"),
        ("bike_price_max", "bike_price_max"),
    )
    return ComparisonGroup(
        "model",
        tuple(
            _row(key, {item.letter: item.numbers.numbers.get(name) for item in versions})
            for key, name in names
        ),
    )


def _stations(item: ComparedVersion) -> Number | None:
    empty = item.numbers.numbers.get("stations_empty_end")
    full = item.numbers.numbers.get("stations_full_end")
    if empty is None or full is None:
        return None
    return Number(empty.value + full.value, "stations", "derived", "headline")


def _derived_group(versions: Sequence[ComparedVersion]) -> ComparisonGroup:
    names = ("profit", "revenue", "cost", "mean_bike_price", "rides_under_cost")
    rows = [
        _row(name, {item.letter: item.numbers.numbers.get(name) for item in versions})
        for name in names
    ]
    rows.append(_row("stations_empty_or_full", {item.letter: _stations(item) for item in versions}))
    return ComparisonGroup("derived", tuple(rows))


def _goals_group(versions: Sequence[ComparedVersion]) -> ComparisonGroup:
    rows = []
    for name in DIFFERING_GOALS:
        values = {item.letter: goal_numbers(item.goals)[name] for item in versions}
        if len({item.value for item in values.values()}) > 1:
            rows.append(_row(name, values))
    return ComparisonGroup("goals_that_differ", tuple(rows))


def _advanced(item: Number | None) -> Number | None:
    return None if item is None else Number(item.value, item.unit, item.source, "advanced")


def _solver_group(versions: Sequence[ComparedVersion]) -> ComparisonGroup:
    rows = []
    terms = ("ridership", "revenue", "cost", "station_balance")
    if any(f"objective_term_{name}" in item.advanced for item in versions for name in terms):
        for name in terms:
            key = f"objective_term_{name}"
            rows.append(_row(key, {item.letter: item.advanced.get(key) for item in versions}))
    for key in ("objective_value", "solution_time_s", "gap_pct", "solver_status"):
        rows.append(_row(key, {item.letter: item.advanced.get(key) for item in versions}))
    rows.append(
        _row(
            "hub_pairs_with_bike_option",
            {
                item.letter: _advanced(item.numbers.numbers.get("hub_pairs_with_bike_option"))
                for item in versions
            },
        )
    )
    rows.append(
        _row(
            "bike_options_offered",
            {
                item.letter: Number(item.bike_options_offered, "options", "model", "advanced")
                for item in versions
            },
        )
    )
    return ComparisonGroup("solver", tuple(rows))


def comparison_groups(
    versions: Sequence[ComparedVersion], references: Sequence[FlatReference]
) -> tuple[ComparisonGroup, ...]:
    """The five groups in the order the screen and the export read them."""
    return (
        _simulated_group(versions, references),
        _model_group(versions),
        _derived_group(versions),
        _goals_group(versions),
        _solver_group(versions),
    )
