from pathlib import Path

import pytest

from pricing_demo.domain import read_model as rows
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from tests.support.city_files import FakeCity

SHAPES = frozenset({"1"})


@pytest.fixture
def city(tmp_path: Path) -> FakeCity:
    return FakeCity(tmp_path)


def failure(origin: str, destination: str, query: str) -> RouteFailure:
    return RouteFailure(origin, destination, query, "no_route", "none", 1)  # type: ignore[arg-type]


def test_the_stations_are_read_in_id_order(city: FakeCity) -> None:
    stations = rows.stations_from(city.files["stations.json"])

    assert len(stations) == 42
    assert [item.station_id for item in stations] == sorted(item.station_id for item in stations)
    assert rows.area_counts(stations) == {"stops": 30, "bike_stations": 12}
    assert city.counts[StepName.AREA] == rows.area_counts(stations)


def test_a_station_of_another_type_is_refused(city: FakeCity) -> None:
    bad = {"stations": [{**city.files["stations.json"]["stations"][0], "type": "x"}]}

    with pytest.raises(ValueError, match="neither pt nor bs"):
        rows.stations_from(bad)


def test_the_hubs_carry_their_outline_stations_and_lines(city: FakeCity) -> None:
    hubs = rows.hubs_from(city.files["hubs.geojson"], city.files["hub_polygons.geojson"])

    assert [item.hub_id for item in hubs] == ["H1", "H2", "H3", "H4", "H5", "H6"]
    first = hubs[0]
    assert first.outline is not None
    assert first.outline["type"] == "Polygon"
    assert len(first.pt_station_ids) == 5
    assert len(first.bike_station_ids) == 2
    assert first.lines == ("1", "2")
    assert rows.hubs_counts(hubs) == {"hubs": 6}


def test_a_hub_without_a_polygon_has_no_outline(city: FakeCity) -> None:
    hubs = rows.hubs_from(city.files["hubs.geojson"], {"type": "FeatureCollection", "features": []})

    assert all(item.outline is None for item in hubs)


def test_the_stations_are_linked_to_their_hubs(city: FakeCity) -> None:
    links = rows.station_hubs_from(city.files["stations_hubs.geojson"])

    assert len(links) == 42
    assert rows.StationHubRow("pts_FAKEH10", "H1") in links


def test_the_hub_pairs_come_with_the_packages_own_distance(city: FakeCity) -> None:
    pairs = rows.hub_pairs_from(city.files["Instance_1.json"])

    assert len(pairs) == 24
    assert pairs == tuple(sorted(pairs, key=lambda item: (item.origin_hub, item.destination_hub)))
    assert all(item.euclid_dist_m > 0 for item in pairs)


@pytest.mark.parametrize("mode", ["BICYCLE", "CAR", "FOOT", "WALK"])
def test_a_street_mode_follows_the_street(mode: str) -> None:
    assert rows.line_kind(mode, None, SHAPES) == "street"


def test_a_bus_with_a_shape_follows_it_and_one_without_is_a_straight_line() -> None:
    assert rows.line_kind("BUS", "1", SHAPES) == "shape"
    assert rows.line_kind("BUS", "12", SHAPES) == "straight"
    assert rows.line_kind("BUS", None, SHAPES) == "straight"


def test_a_tram_is_a_transit_leg_like_a_bus() -> None:
    assert rows.line_kind("TRAM", "1", SHAPES) == "shape"
    assert rows.line_kind("TRAM", "T2", SHAPES) == "straight"


def test_the_options_are_the_arcs_of_the_instance_with_their_legs_and_geometry(
    city: FakeCity,
) -> None:
    options = rows.route_options_from(
        city.files["od_routes.json"],
        city.files["od_geometry.json"],
        city.files["Instance_1.json"],
        SHAPES,
    )

    assert rows.instance_counts(city.files["Instance_1.json"])["options"] == {
        "pt_bike": 23,
        "pt_only": 24,
        "car": 24,
    }
    by_mode = {
        mode: [o for o in options if o.mode == mode] for mode in ("pt_bike", "pt_only", "car")
    }
    assert {mode: len(found) for mode, found in by_mode.items()} == {
        "pt_bike": 23,
        "pt_only": 24,
        "car": 24,
    }
    option = by_mode["pt_bike"][0]
    assert (option.origin_hub, option.destination_hub) != ("", "")
    assert [leg.line_kind for leg in option.legs] == ["street", "shape"]
    assert option.geometry
    assert {leg.line_kind for o in options for leg in o.legs} == {"street", "shape", "straight"}
    assert {o.arc_id for o in options if o.mode == "pt_only" and o.legs[1].mode == "TRAM"}


def test_an_arc_the_instance_dropped_is_not_an_option(city: FakeCity) -> None:
    instance = {**city.files["Instance_1.json"], "arcs_pt_only": []}

    options = rows.route_options_from(
        city.files["od_routes.json"], city.files["od_geometry.json"], instance, SHAPES
    )

    assert not [o for o in options if o.mode == "pt_only"]


def test_the_bikes_and_the_deltas_are_read_from_the_instance(city: FakeCity) -> None:
    bikes = rows.station_bikes_from(city.files["Instance_1.json"])
    deltas = rows.deltas_from(city.files["Instance_1.json"])

    assert len(bikes) == 12
    assert any(item.inventory_start == 0 for item in bikes)
    assert len(deltas) == 23


def test_the_routes_counts_are_two_queries_per_pair_requested(city: FakeCity) -> None:
    counts = rows.routes_counts(
        city.files["od_routes.json"],
        city.counts[StepName.ROUTES],
        [failure("H1", "H2", "pt_bike"), failure("H1", "H2", "car")],
    )

    assert counts == {
        "hub_pairs_requested": 24,
        "hub_pairs_with_routes": 24,
        "hub_pairs_removed": 0,
        "queries": 48,
        "queries_failed": 2,
        "failure_pct": pytest.approx(4.1666666),
        "retries": 3,
    }


def test_the_failure_rate_of_no_queries_is_zero() -> None:
    assert rows.failure_pct(0, 0) == 0.0
    assert rows.failure_pct(2, 48) == pytest.approx(4.1666666)


def test_a_routes_file_without_pairs_is_malformed() -> None:
    with pytest.raises(ValueError, match=r"od_routes\.json"):
        rows.routes_counts({}, {}, [])


def test_the_instance_counts_come_from_the_instance(city: FakeCity) -> None:
    counts = rows.instance_counts(city.files["Instance_1.json"])

    assert counts["hub_pairs"] == 24
    assert counts["bike_stations"] == 12
    assert counts["travellers"] == city.files["Instance_1.json"]["info"]["total_demand"]
    assert counts == city.counts[StepName.TRAVELLERS_AND_BIKES]


def test_a_pair_that_failed_both_queries_counts_as_without_public_transport_only() -> None:
    failures = [
        failure("H1", "H2", "pt_bike"),
        failure("H1", "H2", "car"),
        failure("H1", "H6", "car"),
        failure("H2", "H1", "pt_bike"),
    ]
    counts = {"queries": 48, "queries_failed": 4, "failure_pct": 8.0, "retries": 3}

    summary = rows.routes_summary(counts, failures, "run-1")

    assert summary == rows.RoutesSummary(48, 4, 8.0, 2, 1, 3, "run-1")


def test_the_headline_counts_are_five_inputs_in_screen_order() -> None:
    headline = rows.headline_counts(
        {"stops": 30, "bike_stations": 12},
        {"hubs": 6},
        {"hub_pairs_with_routes": 24},
        {"travellers": 700},
    )

    assert list(headline) == [
        "stops",
        "bike_stations",
        "hubs",
        "hub_pairs_with_routes",
        "travellers",
    ]
    assert headline["hub_pairs_with_routes"] == Number(24, "hub_pairs", "input", "headline")
    assert [item.unit for item in headline.values()] == [
        "stops",
        "bike_stations",
        "hubs",
        "hub_pairs",
        "travellers",
    ]
    assert {(item.source, item.group) for item in headline.values()} == {("input", "headline")}


@pytest.mark.parametrize(
    "reader",
    [
        lambda: rows.stations_from({}),
        lambda: rows.hubs_from({}, {"features": []}),
        lambda: rows.station_hubs_from({"features": [{}]}),
        lambda: rows.hub_pairs_from({"OD_pairs": [{"origin": "a"}]}),
        lambda: rows.route_options_from({}, {}, {}, SHAPES),
        lambda: rows.station_bikes_from({}),
        lambda: rows.deltas_from({}),
        lambda: rows.instance_counts({}),
    ],
)
def test_a_malformed_file_raises_a_value_error(reader) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="not in the expected shape"):
        reader()
