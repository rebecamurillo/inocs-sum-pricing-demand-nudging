from dataclasses import replace
from datetime import date

import pytest

from pricing_demo.domain.city_instances import (
    InstanceParameters,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.instance_rules import RULE_IDS, RuleResult, check_rules
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PERIOD = first_period("g.v1", DATASET)
DEFAULTS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
GOOD = replace(DEFAULTS, min_od_distance_m=600.0)


def result(rule: str, parameters: InstanceParameters = GOOD, period=PERIOD) -> RuleResult:  # type: ignore[no-untyped-def]
    (found,) = [item for item in check_rules(parameters, DATASET, period) if item.rule == rule]
    return found


def test_the_ten_rules_come_in_the_order_of_the_specification() -> None:
    assert [item.rule for item in check_rules(GOOD, DATASET, PERIOD)] == list(RULE_IDS)
    assert len(RULE_IDS) == 10


def test_good_values_pass_every_rule() -> None:
    assert [item.rule for item in check_rules(GOOD, DATASET, PERIOD) if not item.passed] == []


def test_the_package_defaults_tie_the_trip_distance_with_the_grouping_distance() -> None:
    # 500 m is not above 500 m: the rule is strict, as the specification words it.
    failed = [item.rule for item in check_rules(DEFAULTS, DATASET, PERIOD) if not item.passed]

    assert failed == ["min_trip_distance_above_grouping"]


def test_every_rule_names_two_values() -> None:
    for item in check_rules(GOOD, DATASET, PERIOD):
        assert len(item.values) == 2
        assert all(value.name for value in item.values)
    broken = replace(GOOD, radius_m=6000, seed=-1, fixed_capacity=0, center_lat=0.0)
    for item in check_rules(broken, DATASET, PERIOD):
        assert len(item.values) == 2


@pytest.mark.parametrize(
    ("changes", "passed"),
    [
        ({"min_od_distance_m": 501.0}, True),
        ({"min_od_distance_m": 500.0}, False),
        ({"min_od_distance_m": 100.0}, False),
    ],
)
def test_minimum_trip_distance_above_grouping(changes: dict[str, float], passed: bool) -> None:
    parameters = replace(GOOD, **changes)

    found = result("min_trip_distance_above_grouping", parameters)

    assert found.passed is passed
    assert [(v.name, v.value, v.unit) for v in found.values] == [
        ("minimum trip distance", parameters.min_od_distance_m, "m"),
        ("grouping distance", parameters.clustering_threshold_m, "m"),
    ]


@pytest.mark.parametrize(
    ("radius", "passed"),
    [(1000, True), (3000, True), (5000, True), (999, False), (6000, False), (0, False)],
)
def test_radius_from_1_to_5_km(radius: float, passed: bool) -> None:
    found = result("radius_1_to_5_km", replace(GOOD, radius_m=radius))

    assert found.passed is passed
    assert (found.values[0].name, found.values[0].value, found.values[0].unit) == (
        "radius",
        radius,
        "m",
    )
    assert (found.values[1].name, found.values[1].value) == ("allowed range", "1 to 5 km")


@pytest.mark.parametrize(
    ("low", "high", "passed"), [(10, 70, True), (70, 70, True), (71, 70, False)]
)
def test_travellers_lowest_not_above_highest(low: int, high: int, passed: bool) -> None:
    found = result(
        "travellers_lowest_not_above_highest", replace(GOOD, min_demand=low, max_demand=high)
    )

    assert found.passed is passed
    assert [(v.name, v.value) for v in found.values] == [
        ("lowest travellers", low),
        ("highest travellers", high),
    ]


@pytest.mark.parametrize(
    ("low", "high", "passed"),
    [
        (0.0, 1.0, True),
        (0.2, 0.8, True),
        (-0.1, 1.0, False),
        (0.0, 1.5, False),
        (0.0, 100.0, False),
    ],
)
def test_bikes_from_0_to_100_percent(low: float, high: float, passed: bool) -> None:
    found = result(
        "bikes_0_to_100_pct", replace(GOOD, min_inventory_pct=low, max_inventory_pct=high)
    )

    assert found.passed is passed
    assert [(v.name, v.value, v.unit) for v in found.values] == [
        ("lowest bikes", low, "share of docks"),
        ("highest bikes", high, "share of docks"),
    ]


@pytest.mark.parametrize(
    ("lat", "lon", "passed"),
    [(46.2, 6.15, True), (46.2, 7.0, False), (47.0, 6.15, False), (46.12, 6.05, True)],
)
def test_centre_inside_the_available_area(lat: float, lon: float, passed: bool) -> None:
    found = result("centre_inside_area", replace(GOOD, center_lat=lat, center_lon=lon))

    assert found.passed is passed
    assert (found.values[0].name, found.values[0].value) == ("centre", f"{lat}, {lon}")
    assert (found.values[1].name, found.values[1].value) == ("available area", DATASET.name)


@pytest.mark.parametrize(
    ("routing", "passed"),
    [
        (date(2025, 3, 10), True),
        (date(2024, 12, 15), True),
        (date(2025, 12, 13), True),
        (date(2024, 12, 14), False),
        (date(2025, 12, 14), False),
    ],
)
def test_routing_date_inside_the_timetable(routing: date, passed: bool) -> None:
    found = result("routing_date_inside_timetable", period=replace(PERIOD, routing_date=routing))

    assert found.passed is passed
    assert (found.values[0].name, found.values[0].value) == ("routing date", routing.isoformat())
    assert (found.values[1].name, found.values[1].value) == (
        "timetable validity",
        "2024-12-15 to 2025-12-13",
    )


@pytest.mark.parametrize(
    ("docks", "passed"), [(20, True), (1, True), (0, False), (-3, False), (0.5, False)]
)
def test_docks_at_least_1(docks: float, passed: bool) -> None:
    found = result("docks_at_least_1", replace(GOOD, fixed_capacity=docks))

    assert found.passed is passed
    assert (found.values[0].name, found.values[0].value) == ("docks", docks)
    assert (found.values[1].name, found.values[1].value) == ("minimum", 1)


@pytest.mark.parametrize(
    ("changes", "passed", "named"),
    [
        ({}, True, ("lowest bikes", "highest bikes")),
        (
            {"min_inventory_pct": 0.9, "max_inventory_pct": 0.5},
            False,
            ("lowest bikes", "highest bikes"),
        ),
        ({"min_park_time_min": 6.0}, False, ("lowest parking time", "highest parking time")),
        (
            {"min_inventory_pct": 0.9, "max_inventory_pct": 0.5, "min_park_time_min": 6.0},
            False,
            ("lowest bikes", "highest bikes"),
        ),
    ],
)
def test_bikes_and_parking_lowest_not_above_highest(
    changes: dict[str, float], passed: bool, named: tuple[str, str]
) -> None:
    found = result("bikes_and_parking_lowest_not_above_highest", replace(GOOD, **changes))

    assert found.passed is passed
    assert tuple(v.name for v in found.values) == named


@pytest.mark.parametrize(
    ("seed", "passed"), [(42, True), (0, True), (42.0, True), (-1, False), (1.5, False)]
)
def test_the_seed_is_a_whole_number_of_0_or_more(seed: float, passed: bool) -> None:
    found = result("seed_whole_number", replace(GOOD, seed=seed))

    assert found.passed is passed
    assert (found.values[0].name, found.values[0].value) == ("seed", seed)
    assert (found.values[1].name, found.values[1].value) == (
        "allowed values",
        "whole number, 0 or more",
    )


@pytest.mark.parametrize(
    ("grouping", "margin", "passed"),
    [(500, 100, True), (500, 0, True), (0, 100, False), (-1, 100, False), (500, -1, False)],
)
def test_grouping_above_0_and_margin_0_or_more(
    grouping: float, margin: float, passed: bool
) -> None:
    found = result(
        "grouping_above_0_margin_0_or_more",
        replace(GOOD, clustering_threshold_m=grouping, clustering_buffer_m=margin),
    )

    assert found.passed is passed
    assert [(v.name, v.value, v.unit) for v in found.values] == [
        ("grouping distance", grouping, "package units"),
        ("margin", margin, "package units"),
    ]
