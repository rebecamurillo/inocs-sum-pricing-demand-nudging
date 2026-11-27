import math

import pytest

from pricing_demo.domain.read_model import HubRow, RouteLeg, RouteOptionRow, StationRow
from pricing_demo.domain.solves import SolveRow
from pricing_demo.domain.trip_quotes import (
    NO_HUB_MARGIN_M,
    MalformedPoint,
    PointMatch,
    distance_to_outline_m,
    has_car_option,
    haversine_m,
    hub_name,
    leg_geometry,
    leg_line_string,
    match_point,
    nearest_stop_name,
    parse_point,
    quote_status,
    quoted_options,
    transfers,
)

CENTRE = (46.2, 6.15)
METRES = 111_320.0


def at(east: float, north: float, origin: tuple[float, float] = CENTRE) -> tuple[float, float]:
    return (
        origin[0] + north / METRES,
        origin[1] + east / (METRES * math.cos(math.radians(origin[0]))),
    )


def square(origin: tuple[float, float], half: float = 50) -> dict[str, object]:
    corners = [at(-half, -half, origin), at(half, -half, origin), at(half, half, origin)]
    corners += [at(-half, half, origin), at(-half, -half, origin)]
    return {"type": "Polygon", "coordinates": [[[lon, lat] for lat, lon in corners]]}


def hub(hub_id: str, east: float, north: float, **changes: object) -> HubRow:
    lat, lon = at(east, north)
    values: dict[str, object] = {
        "hub_id": hub_id,
        "label": "PT+bike station",
        "lat": lat,
        "lon": lon,
        "outline": square((lat, lon)),
        "pt_station_ids": (f"pt-{hub_id}",),
        "bike_station_ids": (f"bs-{hub_id}",),
        "lines": (),
    }
    return HubRow(**{**values, **changes})  # type: ignore[arg-type]


def station(station_id: str, kind: str, name: str, east: float, north: float) -> StationRow:
    lat, lon = at(east, north)
    return StationRow(station_id, kind, name, lat, lon)  # type: ignore[arg-type]


HUBS = [hub("H1", 0, 0), hub("H2", 1000, 0)]
STATIONS = [
    station("pt-H1", "pt", "Stop one", 10, 0),
    station("bs-H1", "bs", "Bikes one", 5, 0),
    station("pt-H2", "pt", "Stop two", 1010, 0),
    station("bs-H2", "bs", "Bikes two", 1005, 0),
]


def match(east: float, north: float, radius: float = 3000) -> PointMatch:
    return match_point(at(east, north), CENTRE, radius, HUBS, STATIONS)


def test_the_distance_between_two_points_is_the_great_circle_distance() -> None:
    assert haversine_m(CENTRE, at(1000, 0)) == pytest.approx(1000, rel=2e-3)
    assert haversine_m(CENTRE, CENTRE) == 0


def test_a_point_inside_an_outline_is_at_distance_zero() -> None:
    assert distance_to_outline_m(at(10, 10), HUBS[0].outline or {}) == 0


def test_a_point_outside_an_outline_is_at_the_distance_of_its_nearest_edge() -> None:
    assert distance_to_outline_m(at(150, 0), HUBS[0].outline or {}) == pytest.approx(100, rel=1e-2)


def test_the_distance_to_the_outline_of_a_multipolygon_is_that_of_its_nearest_part() -> None:
    first, second = square(at(0, 0)), square(at(1000, 0))
    multi = {"type": "MultiPolygon", "coordinates": [first["coordinates"], second["coordinates"]]}
    assert distance_to_outline_m(at(1010, 0), multi) == 0
    assert distance_to_outline_m(at(1100, 0), multi) == pytest.approx(50, rel=1e-2)


def test_a_point_in_the_hole_of_a_polygon_is_not_inside_it() -> None:
    outer = square(CENTRE, 100)["coordinates"]
    hole = square(CENTRE, 40)["coordinates"]
    polygon = {"type": "Polygon", "coordinates": [outer[0], hole[0]]}  # type: ignore[index]
    assert distance_to_outline_m(CENTRE, polygon) == pytest.approx(40, rel=1e-2)


def test_an_outline_of_another_type_is_refused() -> None:
    with pytest.raises(ValueError, match="Polygon"):
        distance_to_outline_m(CENTRE, {"type": "Point", "coordinates": [0, 0]})


def test_a_point_on_the_circle_side_in_is_matched_and_outside_is_outside_zone() -> None:
    assert match(0, 0, radius=100).status == "matched"
    assert match(150, 0, radius=100).status == "outside_zone"


def test_a_point_within_the_margin_of_an_outline_is_matched() -> None:
    found = match(50 + NO_HUB_MARGIN_M - 20, 0)
    assert found.status == "matched"
    assert found.hub_id == "H1"


def test_a_point_beyond_the_margin_of_every_outline_is_no_hub_here() -> None:
    found = match(450, 0)
    assert found.status == "no_hub_here"
    assert found.nearest_hub_id == "H1"
    assert found.distance_from_outline_m == pytest.approx(400, rel=1e-2)


def test_no_hub_here_names_the_hub_of_the_nearest_outline() -> None:
    found = match(600, 0)
    assert found.status == "no_hub_here"
    assert found.nearest_hub_id == "H2"


def test_hubs_without_an_outline_do_not_make_a_no_hub_here() -> None:
    bare = [hub("H1", 0, 0, outline=None)]
    found = match_point(at(2000, 0), CENTRE, 3000, bare, STATIONS)
    assert found.status == "matched"


def test_a_matched_point_takes_the_hub_with_the_nearest_centre() -> None:
    found = match(760, 0)
    assert found.hub_id == "H2"
    assert found.distance_to_hub_centre_m == pytest.approx(240, rel=1e-2)
    assert found.hub_name == "Stop two"


def test_the_nearest_stop_is_a_stop_never_a_bike_station() -> None:
    assert nearest_stop_name(at(4, 0), STATIONS) == "Stop one"
    assert nearest_stop_name(at(0, 0), [STATIONS[1]]) is None


def test_a_hub_is_named_after_its_stop_nearest_to_its_centre() -> None:
    near = station("pt-b", "pt", "Closer stop", 2, 0)
    assert hub_name(hub("H1", 0, 0, pt_station_ids=("pt-H1", "pt-b")), [*STATIONS, near]) == (
        "Closer stop"
    )


def test_a_hub_without_a_stop_is_named_after_its_nearest_bike_station() -> None:
    assert hub_name(hub("H1", 0, 0, pt_station_ids=()), STATIONS) == "Bikes one"


def test_a_hub_without_any_station_is_named_by_its_id() -> None:
    assert hub_name(hub("H1", 0, 0, pt_station_ids=(), bike_station_ids=()), STATIONS) == "H1"


A = PointMatch("matched", "H1")
B = PointMatch("matched", "H2")


def status(
    origin: PointMatch | None = A,
    destination: PointMatch | None = B,
    distance: float | None = 1000,
    minimum: float = 500,
    in_pairs: bool = True,
    failed: bool = False,
    bike: bool = True,
) -> str:
    return quote_status(origin, destination, distance, minimum, in_pairs, failed, bike)


def test_a_quote_with_one_point_is_one_point() -> None:
    assert status(destination=None) == "one_point"
    assert status(origin=None) == "one_point"


def test_a_point_outside_the_circle_makes_the_quote_outside_zone() -> None:
    assert status(origin=PointMatch("outside_zone")) == "outside_zone"


def test_outside_zone_wins_over_no_hub_here() -> None:
    assert status(PointMatch("no_hub_here"), PointMatch("outside_zone")) == "outside_zone"


def test_a_point_in_no_hub_makes_the_quote_no_hub_here() -> None:
    assert status(destination=PointMatch("no_hub_here")) == "no_hub_here"


def test_two_points_in_one_hub_are_same_hub() -> None:
    assert status(destination=PointMatch("matched", "H1"), in_pairs=False) == "same_hub"


def test_a_pair_closer_than_the_minimum_trip_distance_is_under_minimum_distance() -> None:
    assert status(distance=300, failed=True) == "under_minimum_distance"


def test_a_pair_exactly_at_the_minimum_trip_distance_is_not_under_it() -> None:
    assert status(distance=500) == "priced"


def test_a_pair_with_a_pt_bike_route_failure_is_no_route() -> None:
    assert status(failed=True, in_pairs=False) == "no_route"


def test_a_pair_not_in_the_instance_is_removed_by_the_quality_check() -> None:
    assert status(in_pairs=False) == "removed_by_quality_check"


def test_a_pair_without_an_offered_bike_option_is_no_bike_option() -> None:
    assert status(bike=False) == "no_bike_option"


def test_a_pair_with_an_offered_bike_option_is_priced() -> None:
    assert status() == "priced"


def leg(mode: str, duration: float = 60) -> RouteLeg:
    return RouteLeg(mode, duration, 100, "street", "L1", "here", "there")


def option(
    arc_id: str,
    mode: str,
    legs: tuple[RouteLeg, ...] = (),
    bike_legs: int | None = None,
    car_cost: float | None = None,
    parking: float | None = None,
    travel: float = 600,
    transfer: float = 60,
) -> RouteOptionRow:
    return RouteOptionRow(
        arc_id,
        "H1",
        "H2",
        mode,  # type: ignore[arg-type]
        travel,
        transfer,
        1000,
        legs,
        [],
        bike_legs,
        car_cost,
        parking,
    )


def row(arc_id: str, kind: str, flow: float, bike_price: float | None = None) -> SolveRow:
    return SolveRow(arc_id, "H1", "H2", kind, 0.0, flow, bike_price, None, None, None)  # type: ignore[arg-type]


OPTIONS = [
    option("1b", "pt_bike", (leg("BICYCLE"), leg("BUS")), bike_legs=1),
    option("1p", "pt_only", (leg("FOOT"), leg("BUS"))),
    option("car_1", "car", (leg("CAR"),), car_cost=5.0, parking=10, travel=300, transfer=0),
]
ROWS = {
    "1b": row("1b", "PT+Bike", 7, 2.0),
    "1p": row("1p", "PT-Only", 5),
    "car_1": row("car_1", "Car", 3),
}


def quoted(options: list[RouteOptionRow] = OPTIONS, rows: dict[str, SolveRow] = ROWS):  # type: ignore[no-untyped-def]
    return {item.arc_id: item for item in quoted_options(options, rows, 3.0, 4.0)}


def test_a_pt_bike_price_is_bike_legs_times_bike_price_plus_the_fare() -> None:
    found = quoted()["1b"]
    assert found.price.value == 5.0
    assert (found.price.unit, found.price.source, found.price.group) == (
        "chf",
        "derived",
        "headline",
    )
    assert found.bike_price is not None
    assert found.bike_price.source == "model"
    assert found.pt_fare is not None
    assert found.pt_fare.source == "input"


def test_a_two_leg_pt_bike_option_pays_the_bike_price_twice() -> None:
    two = option("2b", "pt_bike", (leg("BICYCLE"), leg("BUS"), leg("BICYCLE")), bike_legs=2)
    found = quoted([two], {"2b": row("2b", "PT+Bike", 1, 2.0)})["2b"]
    assert found.price.value == 7.0
    assert found.bike_legs.value == 2


def test_a_pt_only_price_is_the_fare() -> None:
    found = quoted()["1p"]
    assert found.price.value == 3.0
    assert found.bike_price is None
    assert found.bike_legs.value == 0


def test_a_car_price_is_its_cost_plus_the_parking_fee() -> None:
    found = quoted()["car_1"]
    assert found.price.value == 9.0
    assert found.car_cost is not None
    assert found.car_cost.value == 5.0
    assert found.car_parking_fee is not None
    assert found.car_parking_fee.value == 4.0
    assert found.pt_fare is None


def test_the_duration_is_the_option_travel_time_with_the_parking_search_for_a_car() -> None:
    found = quoted()
    assert found["1b"].duration_s.value == 660
    assert found["car_1"].duration_s.value == 900
    assert found["car_1"].duration_s.source == "trip_planner"


def test_a_pt_bike_option_the_model_does_not_offer_is_left_out() -> None:
    assert "1b" not in quoted(OPTIONS, {k: v for k, v in ROWS.items() if k != "1b"})


def test_the_options_come_by_mode_then_arc_id() -> None:
    assert [o.arc_id for o in quoted_options(OPTIONS[::-1], ROWS, 3.0, 4.0)] == [
        "1b",
        "1p",
        "car_1",
    ]


def test_the_model_flow_is_carried_on_each_option() -> None:
    found = quoted()["1b"].flow
    assert found is not None
    assert (found.value, found.unit, found.source) == (7, "travellers", "model")


def test_most_taken_marks_the_largest_flow_of_each_mode() -> None:
    second = option("3b", "pt_bike", (leg("BICYCLE"), leg("BUS")), bike_legs=1)
    found = quoted([*OPTIONS, second], {**ROWS, "3b": row("3b", "PT+Bike", 9, 2.0)})
    assert [a for a, o in found.items() if o.most_taken] == ["3b", "1p", "car_1"]


def test_a_tie_on_flow_goes_to_the_lower_arc_id() -> None:
    second = option("0b", "pt_bike", (leg("BICYCLE"), leg("BUS")), bike_legs=1)
    found = quoted([*OPTIONS, second], {**ROWS, "0b": row("0b", "PT+Bike", 7, 2.0)})
    assert found["0b"].most_taken
    assert not found["1b"].most_taken


def test_an_option_without_a_solve_row_has_no_flow_and_is_never_most_taken() -> None:
    found = quoted(OPTIONS, {k: v for k, v in ROWS.items() if k != "1p"})["1p"]
    assert found.flow is None
    assert not found.most_taken


def test_a_pair_has_a_car_option_only_with_a_stored_car_cost() -> None:
    assert has_car_option(OPTIONS)
    assert not has_car_option(OPTIONS[:2])
    assert not has_car_option([option("car_9", "car")])


def test_a_car_option_without_a_cost_is_not_quoted() -> None:
    assert "car_9" not in quoted([*OPTIONS, option("car_9", "car")])


def test_transfers_are_the_legs_that_are_not_walking_minus_one() -> None:
    assert transfers([leg("BICYCLE"), leg("BUS")]) == 1
    assert transfers([leg("FOOT"), leg("BUS"), leg("WALK"), leg("TRAM")]) == 1
    assert transfers([leg("CAR")]) == 0
    assert transfers([leg("FOOT")]) == 0
    assert transfers([]) == 0


def test_every_leg_carries_its_names_and_its_duration() -> None:
    found = quoted()["1b"].legs[1]
    assert (found.mode, found.line, found.from_name, found.to_name) == (
        "BUS",
        "L1",
        "here",
        "there",
    )
    assert found.duration_s.value == 60


@pytest.mark.parametrize(
    "text", ["abc", "46.2", "1,2,3", "91,6", "-91,6", "46,181", "nan,6", "inf,1", ""]
)
def test_a_malformed_point_is_refused(text: str) -> None:
    with pytest.raises(MalformedPoint):
        parse_point(text)


def test_a_point_is_lat_then_lon() -> None:
    assert parse_point("46.2, 6.15") == (46.2, 6.15)
    assert parse_point("-90,-180") == (-90.0, -180.0)


def test_a_stored_leg_geometry_swaps_lat_lon_into_lon_lat() -> None:
    assert leg_line_string([[46.2, 6.1], [46.3, 6.2]]) == {
        "type": "LineString",
        "coordinates": [[6.1, 46.2], [6.2, 46.3]],
    }


def test_a_leg_without_geometry_has_no_line_string() -> None:
    assert leg_line_string(None) is None
    assert leg_line_string([]) is None


def test_the_geometry_of_a_leg_is_found_by_its_index() -> None:
    stored = [{"leg_idx": 0, "geometry": [[1, 2]]}, {"leg_idx": 1, "geometry": [[3, 4]]}]
    assert leg_geometry(stored, 1) == [[3, 4]]
    assert leg_geometry(stored, 2) is None
    assert leg_geometry([], 0) is None
