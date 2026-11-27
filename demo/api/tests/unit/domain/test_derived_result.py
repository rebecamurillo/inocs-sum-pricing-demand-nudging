"""Each formula of ARCHITECTURE.md § 6.2 on one small instance worked out by hand.

Two hubs (H1: stations s1, s2; H2: station s3), two pairs (H1 to H2: 10 travellers, H2 to H1:
6), five options:

    a1 pt_bike k=1  q=4  p=1.0  z=3     a2 pt_bike k=2  q=2  p=0.5  z=1
    a3 pt_only      q=4                 b1 pt_bike k=1  q=3  p=0.8  z=2
    b2 car          q=3

Rides k*q: 4, 4 and 3, so 11. Revenue sum(p*k*q) = 4 + 2 + 2.4 = 8.4; cost at 0.6 = 6.6.
"""

import pytest

from pricing_demo.domain.derived_result import (
    DERIVATION_VERSION,
    OBJECTIVE_TOLERANCE,
    ResultNumbers,
    Ride,
    SimulationSummary,
    derived_cost,
    derived_hub_rides,
    derived_mean_bike_price,
    derived_objective_terms,
    derived_revenue,
    derived_rides_under_cost,
    derived_station_balance,
    objective_residual,
    offered_rides,
    simulated_goals,
    summarise_result,
)
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.read_model import (
    HubPairRow,
    HubRow,
    OptionStationDeltaRow,
    RouteOptionRow,
    StationBikesRow,
)
from pricing_demo.domain.solves import SolveRow


def row(
    arc: str, origin: str, destination: str, kind: str, flow: float, price: float | None, z: float
) -> SolveRow:
    return SolveRow(arc, origin, destination, kind, 1.0, flow, price, None, z, 0.0)  # type: ignore[arg-type]


ROWS = [
    row("a1", "H1", "H2", "PT+Bike", 4, 1.0, 3.0),
    row("a2", "H1", "H2", "PT+Bike", 2, 0.5, 1.0),
    row("a3", "H1", "H2", "PT-Only", 4, None, 0.0),
    row("b1", "H2", "H1", "PT+Bike", 3, 0.8, 2.0),
    row("b2", "H2", "H1", "Car", 3, None, 0.0),
]


def option(arc: str, origin: str, destination: str, mode: str, legs: int | None) -> RouteOptionRow:
    return RouteOptionRow(arc, origin, destination, mode, 600.0, 0.0, 1000.0, (), [], legs)  # type: ignore[arg-type]


OPTIONS = [
    option("a1", "H1", "H2", "pt_bike", 1),
    option("a2", "H1", "H2", "pt_bike", 2),
    option("a3", "H1", "H2", "pt_only", 0),
    option("b1", "H2", "H1", "pt_bike", 1),
    option("b2", "H2", "H1", "car", 0),
]
DELTAS = [
    OptionStationDeltaRow("a1", "s1", -1),
    OptionStationDeltaRow("a1", "s3", 1),
    OptionStationDeltaRow("a2", "s1", -1),
    OptionStationDeltaRow("a2", "s2", -1),
    OptionStationDeltaRow("a2", "s3", 1),
    OptionStationDeltaRow("b1", "s3", -1),
    OptionStationDeltaRow("b1", "s1", 1),
]
STATIONS = [
    StationBikesRow("s1", 10, 5),
    StationBikesRow("s2", 10, 0.5),
    StationBikesRow("s3", 4, 3),
]
HUBS = [
    HubRow("H1", "H1", 46.2, 6.1, None, (), ("s1", "s2"), ()),
    HubRow("H2", "H2", 46.21, 6.15, None, (), ("s3",), ()),
]
PAIRS = [HubPairRow("H1", "H2", 10, 900.0), HubPairRow("H2", "H1", 6, 900.0)]
GOALS = new_draft_goals(None).replacing({"ridership_weight": 8.0, "station_balance_weight": 0.5})
# 8*9 ridership + 7 revenue - 6.6 cost + 0.5*(-2.65) station balance.
OBJECTIVE = 71.075


def rides() -> list[Ride]:
    return offered_rides(ROWS, OPTIONS)


def summarised(objective: float | None = OBJECTIVE) -> ResultNumbers:
    return summarise_result(ROWS, OPTIONS, DELTAS, STATIONS, HUBS, PAIRS, GOALS, objective)


def test_the_derivation_version_is_one() -> None:
    assert DERIVATION_VERSION == 1


def test_offered_rides_are_the_pt_bike_rows_with_their_bike_legs() -> None:
    assert [(item.arc_id, item.bike_legs) for item in rides()] == [("a1", 1), ("a2", 2), ("b1", 1)]


def test_an_offered_option_without_bike_legs_is_refused() -> None:
    options = [option("a1", "H1", "H2", "pt_bike", None), *OPTIONS[1:]]

    with pytest.raises(ValueError, match="a1"):
        offered_rides(ROWS, options)


def test_the_mean_bike_price_is_weighted_by_the_rides() -> None:
    mean, low, high = derived_mean_bike_price(rides())

    assert mean == pytest.approx(8.4 / 11)
    assert (low, high) == (0.5, 1.0)


def test_the_mean_is_absent_when_no_ride_is_made_but_the_range_stays() -> None:
    nobody = [item for item in rides() if item.bike_legs == 0] or [
        item.__class__(item.arc_id, item.origin_hub, item.destination_hub, 4.0, 0.7, 0.0, 0)
        for item in rides()[:1]
    ]

    mean, low, high = derived_mean_bike_price(nobody)

    assert mean is None
    assert (low, high) == (0.7, 0.7)


def test_no_offered_option_gives_no_mean_and_no_range() -> None:
    assert derived_mean_bike_price([]) == (None, None, None)


def test_revenue_cost_and_the_rides_under_the_cost() -> None:
    assert derived_revenue(rides()) == pytest.approx(8.4)
    assert derived_cost(rides(), 0.6) == pytest.approx(6.6)
    assert derived_rides_under_cost(rides(), 0.6) == (4.0, 11.0)


def test_a_price_equal_to_the_cost_is_not_under_it() -> None:
    assert derived_rides_under_cost(rides(), 0.5)[0] == 0.0


def test_end_bikes_and_the_empty_and_full_stations_at_both_ends() -> None:
    balance = derived_station_balance(STATIONS, DELTAS, rides())

    assert balance.end_bikes == {"s1": 2.0, "s2": -1.5, "s3": 6.0}
    assert (balance.empty_end, balance.full_end) == (1, 1)
    # s2 starts below one bike; s3 starts at capacity - 1, which is not full.
    assert (balance.empty_start, balance.full_start) == (1, 0)


def test_rides_starting_and_ending_at_each_hub() -> None:
    found = derived_hub_rides(HUBS, DELTAS, rides())

    assert found == {"H1": (8.0, 3.0), "H2": (3.0, 6.0)}


def test_the_four_terms_of_the_objective() -> None:
    terms = derived_objective_terms(rides(), DELTAS, STATIONS, GOALS)

    assert terms["ridership"] == pytest.approx(72.0)
    assert terms["revenue"] == pytest.approx(7.0)
    assert terms["cost"] == pytest.approx(6.6)
    assert terms["station_balance"] == pytest.approx(-1.325)


def test_a_station_without_capacity_adds_nothing_to_the_station_balance_term() -> None:
    stations = [*STATIONS[:2], StationBikesRow("s3", 0, 0)]

    terms = derived_objective_terms(rides(), DELTAS, stations, GOALS)

    assert terms["station_balance"] == pytest.approx(0.5 * (4 * -0.5 + 2 * -1.45 + 3 * 0.5))


def test_the_residual_is_relative_to_the_objective_with_a_floor_of_one() -> None:
    assert objective_residual(10.5, 10.0) == pytest.approx(0.05)
    assert objective_residual(0.5, 0.0) == pytest.approx(0.5)


def test_terms_at_exactly_the_tolerance_are_kept_and_above_it_dropped() -> None:
    assert OBJECTIVE_TOLERANCE == 1e-6
    assert objective_residual(1_000_001.0, 1_000_000.0) <= OBJECTIVE_TOLERANCE
    assert objective_residual(1_000_001.1, 1_000_000.0) > OBJECTIVE_TOLERANCE


def test_terms_that_add_up_to_the_objective_are_kept_with_a_zero_residual() -> None:
    result = summarised()

    assert result.objective_residual == pytest.approx(0.0, abs=1e-9)
    assert result.objective_terms is not None
    assert result.objective_terms["station_balance"].value == pytest.approx(-1.325)
    assert {item.source for item in result.objective_terms.values()} == {"derived"}
    assert {item.group for item in result.objective_terms.values()} == {"advanced"}


def test_terms_that_do_not_add_up_are_absent_and_the_residual_is_kept() -> None:
    result = summarised(71.0)

    assert result.objective_terms is None
    assert result.objective_residual == pytest.approx(0.075 / 71.0)


def test_no_objective_value_gives_no_terms_and_no_residual() -> None:
    result = summarised(None)

    assert result.objective_terms is None
    assert result.objective_residual is None


def test_the_model_numbers_come_from_its_flows() -> None:
    numbers = summarised().numbers

    assert numbers["ridership"].value == 9
    assert (numbers["ridership"].source, numbers["ridership"].group) == ("model", "headline")
    assert numbers["travellers_pt_bike"].value == 9
    assert numbers["travellers_pt_only"].value == 4
    assert numbers["travellers_car"].value == 3
    assert numbers["modal_split_pt_bike"].value == pytest.approx(9 / 16)
    assert numbers["modal_split_pt_only"].value == pytest.approx(4 / 16)
    assert numbers["modal_split_car"].value == pytest.approx(3 / 16)
    assert numbers["bike_price_min"].value == 0.5
    assert numbers["bike_price_max"].value == 1.0
    assert numbers["bike_price_min"].source == "model"


def test_the_derived_numbers_say_so() -> None:
    numbers = summarised().numbers

    assert numbers["mean_bike_price"].value == pytest.approx(8.4 / 11)
    assert numbers["revenue"].value == pytest.approx(8.4)
    assert numbers["cost"].value == pytest.approx(6.6)
    assert numbers["profit"].value == pytest.approx(1.8)
    assert numbers["bike_rides"].value == 11
    assert numbers["rides_under_cost"].value == 4
    assert numbers["rides_under_cost_share"].value == pytest.approx(4 / 11)
    assert numbers["stations_empty_end"].value == 1
    assert numbers["stations_full_end"].value == 1
    for name in (
        "mean_bike_price",
        "revenue",
        "cost",
        "profit",
        "rides_under_cost",
        "rides_under_cost_share",
        "stations_empty_end",
        "stations_full_end",
    ):
        assert numbers[name].source == "derived", name


def test_the_stations_at_the_start_are_an_input() -> None:
    numbers = summarised().numbers

    assert (numbers["stations_empty_start"].value, numbers["stations_full_start"].value) == (1, 0)
    assert numbers["stations_empty_start"].source == "input"
    assert numbers["stations_full_start"].source == "input"


def test_the_pairs_with_a_pt_bike_option_are_counted() -> None:
    assert summarised().numbers["hub_pairs_with_bike_option"].value == 2

    without = [item for item in ROWS if item.arc_id not in ("b1",)]
    result = summarise_result(without, OPTIONS, DELTAS, STATIONS, HUBS, PAIRS, GOALS, None)
    assert result.numbers["hub_pairs_with_bike_option"].value == 1


def test_each_pair_has_its_mean_range_and_travellers_per_mode() -> None:
    first, second = summarised().pairs

    assert (first.origin_hub, first.destination_hub) == ("H1", "H2")
    assert first.mean_bike_price is not None
    assert first.mean_bike_price.value == 0.75
    assert first.min_bike_price is not None
    assert first.min_bike_price.value == 0.5
    assert first.max_bike_price is not None
    assert first.max_bike_price.value == 1.0
    assert first.mean_bike_price.source == "derived"
    assert {mode: item.value for mode, item in first.travellers.items()} == {
        "pt_bike": 6,
        "pt_only": 4,
        "car": 0,
    }
    assert first.travellers["pt_bike"].source == "model"
    assert second.mean_bike_price is not None
    assert second.mean_bike_price.value == pytest.approx(0.8)


def test_a_pair_without_an_offered_option_has_no_price() -> None:
    rows = [item for item in ROWS if item.arc_id != "b1"]
    result = summarise_result(rows, OPTIONS, DELTAS, STATIONS, HUBS, PAIRS, GOALS, None)

    second = result.pairs[1]

    assert second.mean_bike_price is None
    assert second.min_bike_price is None
    assert second.max_bike_price is None


def test_each_hub_has_its_rides_and_the_mean_price_of_the_options_that_start_there() -> None:
    first, second = summarised().hubs

    assert (first.hub_id, first.rides_starting.value, first.rides_ending.value) == ("H1", 8, 3)
    assert first.rides_starting.source == "derived"
    assert first.mean_bike_price is not None
    assert first.mean_bike_price.value == 0.75
    assert (second.hub_id, second.rides_starting.value, second.rides_ending.value) == ("H2", 3, 6)
    assert second.mean_bike_price is not None
    assert second.mean_bike_price.value == pytest.approx(0.8)


def test_the_record_round_trips() -> None:
    result = summarised()

    assert ResultNumbers.from_record(result.record()) == result
    dropped = summarised(71.0)
    assert ResultNumbers.from_record(dropped.record()) == dropped


def summary(**changes: object) -> SimulationSummary:
    values: dict[str, object] = {
        "key": "sim",
        "price_scheme": "model_prices",
        "rule_id": "balanced-score",
        "rule_version": 1,
        "rule_parameters": {"price_weight": 0.5},
        "travellers": 16,
        "travellers_per_mode": {"pt_bike": 7, "pt_only": 5, "car": 4},
        "displaced": 1,
        "unserved": 0,
        "bike_rides": 10,
        "bike_revenue_chf": 9.0,
        "stations_empty": 2,
        "stations_full": 1,
    }
    values.update(changes)
    return SimulationSummary(**values)  # type: ignore[arg-type]


def test_the_simulated_goals_follow_the_formulas_of_the_architecture() -> None:
    goals = simulated_goals(summary(), 0.6)

    assert goals["ridership"].value == 7
    assert goals["revenue"].value == 9.0
    assert goals["cost"].value == pytest.approx(6.0)
    assert goals["profit"].value == pytest.approx(3.0)
    assert goals["mean_bike_price"].value == pytest.approx(0.9)
    assert goals["stations_empty"].value == 2
    assert goals["stations_full"].value == 1
    assert {item.source for item in goals.values()} == {"simulation"}


def test_the_simulated_mean_price_is_absent_without_a_ride() -> None:
    goals = simulated_goals(summary(bike_rides=0, bike_revenue_chf=0.0), 0.6)

    assert "mean_bike_price" not in goals
    assert goals["cost"].value == 0.0
