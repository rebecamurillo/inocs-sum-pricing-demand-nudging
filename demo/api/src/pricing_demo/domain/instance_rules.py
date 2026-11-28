"""The ten rules a draft is checked against, each naming the two values it compares.

Rules report; they never correct a value. The list is provisional (author follow-up Q-30).
"""

from dataclasses import dataclass

from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import InstanceParameters, InstancePeriod, Number

SHARE = "share of docks"
PACKAGE_UNITS = "package units"

RULE_IDS = (
    "min_trip_distance_above_grouping",
    "radius_1_to_5_km",
    "travellers_lowest_not_above_highest",
    "bikes_0_to_100_pct",
    "centre_inside_area",
    "routing_date_inside_timetable",
    "docks_at_least_1",
    "bikes_and_parking_lowest_not_above_highest",
    "seed_whole_number",
    "grouping_above_0_margin_0_or_more",
)


@dataclass(frozen=True)
class RuleValue:
    name: str
    value: Number | str
    unit: str | None


@dataclass(frozen=True)
class RuleResult:
    rule: str
    passed: bool
    values: tuple[RuleValue, RuleValue]


def _is_whole(value: Number) -> bool:
    return float(value).is_integer()


def check_rules(
    parameters: InstanceParameters, dataset: CityDataset, period: InstancePeriod
) -> list[RuleResult]:
    p = parameters
    area = dataset.available_area
    gtfs = dataset.gtfs
    bike_pair_ok = p.min_inventory_pct <= p.max_inventory_pct
    parking_pair_ok = p.min_park_time_min <= p.max_park_time_min
    bikes = (
        RuleValue("lowest bikes", p.min_inventory_pct, SHARE),
        RuleValue("highest bikes", p.max_inventory_pct, SHARE),
    )
    parking = (
        RuleValue("lowest parking time", p.min_park_time_min, "min"),
        RuleValue("highest parking time", p.max_park_time_min, "min"),
    )
    # A failing pair is the one named; when both hold, the bikes pair is.
    pair = parking if bike_pair_ok and not parking_pair_ok else bikes
    return [
        RuleResult(
            RULE_IDS[0],
            p.min_od_distance_m > p.clustering_threshold_m,
            (
                RuleValue("minimum trip distance", p.min_od_distance_m, "m"),
                RuleValue("grouping distance", p.clustering_threshold_m, "m"),
            ),
        ),
        RuleResult(
            RULE_IDS[1],
            1000 <= p.radius_m <= 5000,
            (RuleValue("radius", p.radius_m, "m"), RuleValue("allowed range", "1 to 5 km", None)),
        ),
        RuleResult(
            RULE_IDS[2],
            p.min_demand <= p.max_demand,
            (
                RuleValue("lowest travellers", p.min_demand, "travellers"),
                RuleValue("highest travellers", p.max_demand, "travellers"),
            ),
        ),
        RuleResult(
            RULE_IDS[3],
            0 <= p.min_inventory_pct <= 1 and 0 <= p.max_inventory_pct <= 1,
            bikes,
        ),
        RuleResult(
            RULE_IDS[4],
            area.min_lat <= p.center_lat <= area.max_lat
            and area.min_lon <= p.center_lon <= area.max_lon,
            (
                RuleValue("centre", f"{p.center_lat}, {p.center_lon}", None),
                RuleValue("available area", dataset.name, None),
            ),
        ),
        RuleResult(
            RULE_IDS[5],
            gtfs.valid_from <= period.routing_date <= gtfs.valid_to,
            (
                RuleValue("routing date", period.routing_date.isoformat(), None),
                RuleValue(
                    "timetable validity",
                    f"{gtfs.valid_from.isoformat()} to {gtfs.valid_to.isoformat()}",
                    None,
                ),
            ),
        ),
        RuleResult(
            RULE_IDS[6],
            p.fixed_capacity >= 1,
            (RuleValue("docks", p.fixed_capacity, "docks"), RuleValue("minimum", 1, "docks")),
        ),
        RuleResult(RULE_IDS[7], bike_pair_ok and parking_pair_ok, pair),
        RuleResult(
            RULE_IDS[8],
            _is_whole(p.seed) and p.seed >= 0,
            (
                RuleValue("seed", p.seed, None),
                RuleValue("allowed values", "whole number, 0 or more", None),
            ),
        ),
        RuleResult(
            RULE_IDS[9],
            p.clustering_threshold_m > 0 and p.clustering_buffer_m >= 0,
            (
                RuleValue("grouping distance", p.clustering_threshold_m, PACKAGE_UNITS),
                RuleValue("margin", p.clustering_buffer_m, PACKAGE_UNITS),
            ),
        ),
    ]
