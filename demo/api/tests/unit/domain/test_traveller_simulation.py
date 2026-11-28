import pytest

from pricing_demo.domain.read_model import OptionStationDeltaRow, RouteMode, StationBikesRow
from pricing_demo.domain.traveller_simulation import (
    BalancedScore,
    FlatPrice,
    ModelPrices,
    SimulationCheckFailed,
    SimulationInstance,
    SimulationOption,
    SimulationPair,
)

RULE = BalancedScore()
FARE = 2.0
PARKING = 1.0


def opt(
    arc: str,
    mode: RouteMode,
    time_s: float = 600,
    transfer_s: float = 0,
    pair: tuple[str, str] = ("A", "B"),
    legs: int = 1,
    car_cost: float | None = None,
    parking_min: float | None = None,
) -> SimulationOption:
    if mode == "car":
        car_cost = 5.0 if car_cost is None else car_cost
        parking_min = 0.0 if parking_min is None else parking_min
    return SimulationOption(
        arc, pair[0], pair[1], mode, time_s, transfer_s,
        legs if mode == "pt_bike" else 0, car_cost, parking_min,
    )  # fmt: skip


def inst(
    pairs: list[tuple[str, str, int]],
    options: list[SimulationOption],
    stations: list[tuple[str, float, float]] | None = None,
    deltas: list[tuple[str, str, float]] | None = None,
) -> SimulationInstance:
    return SimulationInstance(
        tuple(SimulationPair(*p) for p in pairs),
        tuple(options),
        tuple(StationBikesRow(*s) for s in stations or []),
        tuple(OptionStationDeltaRow(*d) for d in deltas or []),
    )


def flat(price: float = 1.0) -> FlatPrice:
    return FlatPrice(price, FARE, PARKING)


def model(prices: dict[str, float]) -> ModelPrices:
    return ModelPrices(prices, FARE, PARKING)


def by_arc(out_options: object) -> dict[str, int]:
    return {o.arc_id: o.travellers for o in out_options}  # type: ignore[attr-defined]


def test_outputs_carry_rule_and_scheme() -> None:
    out = RULE.simulate(inst([("A", "B", 1)], [opt("x", "pt_only")]), flat())
    assert (out.rule_id, out.rule_version) == ("balanced-score", 1)
    assert out.parameters == {"price_weight": 0.5, "time_weight": 0.5}
    assert out.scheme_kind == "flat"
    assert RULE.simulate(inst([("A", "B", 1)], [opt("x", "pt_only")]), model({})).scheme_kind == (
        "model_prices"
    )


def test_lowest_score_wins() -> None:
    # pt_only: cheaper and faster than the car
    options = [opt("car", "car", 300, car_cost=9.0), opt("pt", "pt_only", 600)]
    out = RULE.simulate(inst([("A", "B", 1)], options), flat())
    assert by_arc(out.options) == {"pt": 1}
    assert out.travellers_per_mode == {"pt_bike": 0, "pt_only": 1, "car": 0}


def test_score_is_half_scaled_price_half_scaled_time() -> None:
    # two options: the dearer one scales to price 1, the slower to time 1; here the car is
    # dearer and faster, the PT slower and cheaper: both score 0.5, so PT alone wins the tie
    options = [opt("pt", "pt_only", 1000), opt("car", "car", 100, car_cost=4.5)]
    out = RULE.simulate(inst([("A", "B", 1)], options), flat())
    assert by_arc(out.options) == {"pt": 1}
    # a third option dominating on time changes the scaling: car is no longer worth 0.5
    options = [
        opt("pt", "pt_only", 1000),
        opt("car", "car", 100, car_cost=4.5),
        opt("bike", "pt_bike", 100),
    ]
    out = RULE.simulate(inst([("A", "B", 1)], options), model({"bike": 0.0}))
    # bike: price 2 (0), time 100 (0) -> 0
    assert by_arc(out.options) == {"bike": 1}
    options = [opt("pt", "pt_only", 1000), opt("car", "car", 100, car_cost=0.5)]
    out = RULE.simulate(inst([("A", "B", 1)], options), flat())
    assert by_arc(out.options) == {"car": 1}


def test_tie_goes_to_pt_bike_then_pt_then_car_then_order() -> None:
    same = [
        opt("car", "car", 600, car_cost=1.0),
        opt("pt", "pt_only", 600),
        opt("bike", "pt_bike", 600),
    ]
    # prices: car 2, pt 2, bike 1*0 + 2 = 2 (bike price 0): all equal, scaled 0
    out = RULE.simulate(inst([("A", "B", 1)], same), model({"bike": 0.0}))
    assert by_arc(out.options) == {"bike": 1}
    out = RULE.simulate(inst([("A", "B", 1)], same), model({}))
    assert by_arc(out.options) == {"pt": 1}
    out = RULE.simulate(inst([("A", "B", 1)], [same[0]]), model({}))
    assert by_arc(out.options) == {"car": 1}
    two = [opt("b2", "pt_bike", 600), opt("b1", "pt_bike", 600)]
    out = RULE.simulate(inst([("A", "B", 1)], two), model({"b1": 0.0, "b2": 0.0}))
    assert by_arc(out.options) == {"b2": 1}


def test_equal_values_scale_to_zero() -> None:
    options = [opt("pt", "pt_only", 600), opt("car", "car", 600, car_cost=1.0)]
    out = RULE.simulate(inst([("A", "B", 1)], options), flat())
    assert by_arc(out.options) == {"pt": 1}  # scores 0 and 0: tie by mode


def test_travel_time_adds_transfer_and_car_parking_time() -> None:
    car = opt("car", "car", 100, transfer_s=0, car_cost=1.0, parking_min=10)
    assert car.travel_time_s == 700
    assert opt("pt", "pt_only", 100, transfer_s=50).travel_time_s == 150
    # with parking time the car (price 2, time 700) loses to PT (price 2, time 150)
    out = RULE.simulate(inst([("A", "B", 1)], [car, opt("pt", "pt_only", 100, 50)]), flat())
    assert by_arc(out.options) == {"pt": 1}


def test_car_without_cost_or_parking_time_is_refused() -> None:
    with pytest.raises(ValueError, match="car option"):
        SimulationOption("c", "A", "B", "car", 1, 0, 0, None, 1.0)
    with pytest.raises(ValueError, match="car option"):
        SimulationOption("c", "A", "B", "car", 1, 0, 0, 1.0, None)


def bike_instance(travellers: int, inventory: float = 1, capacity: float = 5) -> SimulationInstance:
    return inst(
        [("A", "B", travellers)],
        [opt("bike", "pt_bike", 300), opt("pt", "pt_only", 900)],
        [("s1", capacity, inventory), ("s2", capacity, 0)],
        [("bike", "s1", -1), ("bike", "s2", 1)],
    )


def test_no_bike_displaces_to_the_next_option() -> None:
    out = RULE.simulate(bike_instance(3), model({"bike": 0.0}))
    # first takes the bike (s1 1->0, s2 0->1), then s1 is empty: refused
    assert by_arc(out.options) == {"bike": 1, "pt": 2}
    assert out.displaced == 2
    assert [o.displaced for o in out.options] == [0, 2]
    assert out.unserved == 0


def test_returned_bike_is_used_by_the_next_traveller() -> None:
    inventory = inst(
        [("A", "B", 2), ("B", "A", 1)],
        [
            opt("ab", "pt_bike", 300),
            opt("ba", "pt_bike", 300, pair=("B", "A")),
            opt("ab_pt", "pt_only", 900),
            opt("ba_pt", "pt_only", 900, pair=("B", "A")),
        ],
        [("s1", 5, 1), ("s2", 5, 0)],
        [("ab", "s1", -1), ("ab", "s2", 1), ("ba", "s2", -1), ("ba", "s1", 1)],
    )
    out = RULE.simulate(inventory, model({"ab": 0.0, "ba": 0.0}))
    # order: A->B (bike s1->s2), B->A (bike s2->s1), A->B (bike again)
    assert by_arc(out.options) == {"ab": 2, "ba": 1}
    assert out.displaced == 0


def test_full_destination_dock_displaces() -> None:
    full = inst(
        [("A", "B", 1)],
        [opt("bike", "pt_bike", 300), opt("pt", "pt_only", 900)],
        [("s1", 5, 3), ("s2", 2, 2)],
        [("bike", "s1", -1), ("bike", "s2", 1)],
    )
    out = RULE.simulate(full, model({"bike": 0.0}))
    assert by_arc(out.options) == {"pt": 1}
    assert out.displaced == 1


def test_unserved_when_only_bike_options_and_refused() -> None:
    only = inst(
        [("A", "B", 2)],
        [opt("bike", "pt_bike")],
        [("s1", 5, 1), ("s2", 5, 0)],
        [("bike", "s1", -1), ("bike", "s2", 1)],
    )
    out = RULE.simulate(only, model({"bike": 1.0}))
    assert out.unserved == 1
    assert out.unserved_per_pair == (("A", "B", 1),)
    assert out.displaced == 0
    assert out.travellers_per_mode["pt_bike"] == 1


def test_pair_without_any_option_is_unserved() -> None:
    out = RULE.simulate(inst([("A", "B", 3)], []), flat())
    assert out.unserved_per_pair == (("A", "B", 3),)
    assert out.unserved == 3
    assert out.displaced == 0


def test_round_robin_over_pairs_sorted_by_origin_then_destination() -> None:
    # one bike in s1; both pairs want it; the first pair in sorted order gets it
    instance = inst(
        [("B", "A", 1), ("A", "B", 1)],
        [
            opt("ba", "pt_bike", 300, pair=("B", "A")),
            opt("ab", "pt_bike", 300),
            opt("ba_pt", "pt_only", 900, pair=("B", "A")),
            opt("ab_pt", "pt_only", 900),
        ],
        [("s1", 5, 1), ("s2", 5, 0)],
        [("ab", "s1", -1), ("ab", "s2", 1), ("ba", "s1", -1), ("ba", "s2", 1)],
    )
    out = RULE.simulate(instance, model({"ab": 0.0, "ba": 0.0}))
    taken = {o.arc_id for o in out.options}
    assert taken == {"ab", "ba_pt"}


def test_no_pair_takes_all_the_bikes() -> None:
    instance = inst(
        [("A", "B", 2), ("C", "D", 1)],
        [
            opt("ab", "pt_bike", 300),
            opt("ab_pt", "pt_only", 900),
            opt("cd", "pt_bike", 300, pair=("C", "D")),
            opt("cd_pt", "pt_only", 900, pair=("C", "D")),
        ],
        [("s1", 5, 2), ("s2", 5, 0)],
        [("ab", "s1", -1), ("cd", "s1", -1)],
    )
    out = RULE.simulate(instance, model({"ab": 0.0, "cd": 0.0}))
    assert by_arc(out.options) == {"ab": 1, "ab_pt": 1, "cd": 1}


def test_determinism() -> None:
    instance = bike_instance(7, inventory=3)
    assert RULE.simulate(instance, flat()) == RULE.simulate(instance, flat())


def test_conservation() -> None:
    out = RULE.simulate(bike_instance(5), flat())
    assert sum(out.travellers_per_mode.values()) + out.unserved == 5


def test_station_bounds_check_names_the_check() -> None:
    broken = inst(
        [("A", "B", 1)], [opt("pt", "pt_only")], [("s1", 2, 5)]
    )  # starts above its capacity
    with pytest.raises(SimulationCheckFailed) as raised:
        RULE.simulate(broken, flat())
    assert raised.value.code == "simulation_check_failed"
    assert raised.value.check == "station bounds"
    assert "station bounds" in str(raised.value)


def test_model_prices_without_a_row_is_not_offered() -> None:
    out = RULE.simulate(bike_instance(1, inventory=5), model({}))
    assert by_arc(out.options) == {"pt": 1}


def test_flat_offers_every_bike_option_at_legs_times_price() -> None:
    two = inst(
        [("A", "B", 1)],
        [opt("bike", "pt_bike", 300, legs=2), opt("pt", "pt_only", 900)],
        [("s1", 5, 2), ("s2", 5, 0)],
        [("bike", "s1", -1), ("bike", "s2", 1)],
    )
    out = RULE.simulate(two, flat(1.5))
    (outcome,) = out.options
    assert outcome.arc_id == "bike"
    assert outcome.price_paid_chf == 2 * 1.5 + FARE
    assert out.bike_rides == 2
    assert out.bike_revenue_chf == 3.0


def test_bike_rides_revenue_and_end_stations() -> None:
    out = RULE.simulate(bike_instance(1, inventory=1, capacity=5), model({"bike": 1.25}))
    assert out.bike_rides == 1
    assert out.bike_revenue_chf == 1.25
    ends = {s.station_id: s.bikes for s in out.stations_end}
    assert ends == {"s1": 0, "s2": 1}
    assert out.stations_empty == ("s1",)
    assert out.stations_full == ()


def test_full_threshold_is_above_capacity_minus_one() -> None:
    instance = inst(
        [("A", "B", 1)],
        [opt("bike", "pt_bike", 300), opt("pt", "pt_only", 900)],
        [("s1", 5, 2), ("s2", 1, 0), ("s3", 5, 3)],
        [("bike", "s1", -1), ("bike", "s2", 1)],
    )
    out = RULE.simulate(instance, model({"bike": 0.0}))
    assert [s.bikes for s in out.stations_end] == [1, 1, 3]
    assert out.stations_full == ("s2",)
    assert out.stations_empty == ()
