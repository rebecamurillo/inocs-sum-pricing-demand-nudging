"""Quoting a trip between two points from stored data: which hub each point belongs to, why a
pair has no price, and the options of a priced pair with their make-up (ARCHITECTURE.md § 6.5).

Nothing here routes or prices with the model: a route and a flow are read as stored, and the
price and the travel time go through `option_price` and `option_travel_time_s`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.numbers import Number, NumberSource
from pricing_demo.domain.option_prices import option_price, option_travel_time_s
from pricing_demo.domain.read_model import (
    HubRow,
    LineKind,
    RouteLeg,
    RouteMode,
    RouteOptionRow,
    StationRow,
)
from pricing_demo.domain.solves import PT_BIKE, SolveRow

EARTH_RADIUS_M = 6_371_000.0
# A point farther than this from every hub outline is in no hub's reach (tech-lead decision,
# step 5 of the traveller view).
NO_HUB_MARGIN_M = 300.0
WALKING_MODES = frozenset({"FOOT", "WALK"})
MODE_ORDER: tuple[RouteMode, ...] = ("pt_bike", "pt_only", "car")
LineKindName = Literal["street_path", "timetable_shape", "straight_line"]
LINE_KINDS: Mapping[LineKind, LineKindName] = {
    "street": "street_path",
    "shape": "timetable_shape",
    "straight": "straight_line",
}

Point = tuple[float, float]  # (lat, lon)
PointStatus = Literal["matched", "outside_zone", "no_hub_here"]
QuoteStatus = Literal[
    "one_point",
    "outside_zone",
    "no_hub_here",
    "same_hub",
    "under_minimum_distance",
    "no_route",
    "removed_by_quality_check",
    "no_bike_option",
    "priced",
]


class NoPoint(DomainError):
    def __init__(self) -> None:
        super().__init__("A trip quote needs at least one point: from, to, or both.")


class MalformedPoint(DomainError):
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__(f"{text!r} is not a point: write it as lat,lon in degrees.")


class PeriodNotPriced(DomainError):
    def __init__(self, version_id: str, period: str) -> None:
        super().__init__(f"The pricing version {version_id} did not price the period {period}.")


class UnknownPeriodKey(DomainError):
    def __init__(self, version_id: str, period: str) -> None:
        super().__init__(f"The instance version {version_id} has no period {period}.")


class HubPairNotFound(DomainError):
    def __init__(self, origin_hub: str, destination_hub: str) -> None:
        super().__init__(f"The instance has no hub pair {origin_hub} to {destination_hub}.")


def parse_point(text: str) -> Point:
    """`lat,lon` in degrees; anything else raises `MalformedPoint`."""
    parts = text.split(",")
    try:
        if len(parts) != 2:
            raise ValueError(text)
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        raise MalformedPoint(text) from None
    if not (math.isfinite(lat) and math.isfinite(lon)) or abs(lat) > 90 or abs(lon) > 180:
        raise MalformedPoint(text)
    return lat, lon


def haversine_m(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _project(point: Point, lat: float, lon: float) -> tuple[float, float]:
    """Metres east and north of `point`, in a plane tangent at it (equirectangular)."""
    north = math.radians(lat - point[0]) * EARTH_RADIUS_M
    east = math.radians(lon - point[1]) * EARTH_RADIUS_M * math.cos(math.radians(point[0]))
    return east, north


def _segment_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from the origin to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(a[0] * dx + a[1] * dy) / length_sq))
    return math.hypot(a[0] + t * dx, a[1] + t * dy)


def _inside_ring(ring: Sequence[tuple[float, float]]) -> bool:
    """Whether the origin is inside the ring (ray casting)."""
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > 0) != (y2 > 0) and x1 + (0 - y1) * (x2 - x1) / (y2 - y1) > 0:
            inside = not inside
    return inside


def _polygon_distance(point: Point, rings: Sequence[Sequence[Sequence[float]]]) -> float:
    projected = [[_project(point, position[1], position[0]) for position in ring] for ring in rings]
    if projected and _inside_ring(projected[0]) and not any(_inside_ring(r) for r in projected[1:]):
        return 0.0
    return min(
        (_segment_distance(a, b) for ring in projected for a, b in pairwise(ring)),
        default=math.inf,
    )


def distance_to_outline_m(point: Point, outline: Mapping[str, Any]) -> float:
    """0 inside a GeoJSON `Polygon` or `MultiPolygon`, else the distance to its nearest edge."""
    kind = outline["type"]
    if kind == "Polygon":
        return _polygon_distance(point, outline["coordinates"])
    if kind == "MultiPolygon":
        return min(
            (_polygon_distance(point, rings) for rings in outline["coordinates"]), default=math.inf
        )
    raise ValueError(f"An outline is a Polygon or a MultiPolygon, not a {kind}.")


@dataclass(frozen=True)
class PointMatch:
    status: PointStatus
    hub_id: str | None = None
    hub_name: str | None = None
    nearest_stop_name: str | None = None
    distance_to_hub_centre_m: float | None = None
    nearest_hub_id: str | None = None
    distance_from_outline_m: float | None = None


def nearest_stop_name(point: Point, stations: Sequence[StationRow]) -> str | None:
    stops = [station for station in stations if station.kind == "pt"]
    if not stops:
        return None
    return min(stops, key=lambda s: (haversine_m(point, (s.lat, s.lon)), s.station_id)).name


def hub_name(hub: HubRow, stations: Sequence[StationRow]) -> str:
    """A hub has no place name in the package: it is called after its stop nearest to its
    centre, or after its nearest bike station when it has no stop."""
    centre = (hub.lat, hub.lon)
    for kind, ids in (("pt", hub.pt_station_ids), ("bs", hub.bike_station_ids)):
        members = [s for s in stations if s.kind == kind and s.station_id in ids]
        if members:
            return min(
                members, key=lambda s: (haversine_m(centre, (s.lat, s.lon)), s.station_id)
            ).name
    return hub.hub_id


def match_point(
    point: Point,
    centre: Point,
    radius_m: float,
    hubs: Sequence[HubRow],
    stations: Sequence[StationRow],
) -> PointMatch:
    """Outside the study circle; else farther than `NO_HUB_MARGIN_M` from every hub outline;
    else the hub with the nearest centre."""
    if haversine_m(point, centre) > radius_m:
        return PointMatch("outside_zone")
    outlined = [
        (distance_to_outline_m(point, hub.outline), hub.hub_id)
        for hub in hubs
        if hub.outline is not None
    ]
    if outlined:
        distance, nearest = min(outlined)
        if distance > NO_HUB_MARGIN_M:
            return PointMatch(
                "no_hub_here", nearest_hub_id=nearest, distance_from_outline_m=distance
            )
    hub = min(hubs, key=lambda h: (haversine_m(point, (h.lat, h.lon)), h.hub_id))
    return PointMatch(
        "matched",
        hub_id=hub.hub_id,
        hub_name=hub_name(hub, stations),
        nearest_stop_name=nearest_stop_name(point, stations),
        distance_to_hub_centre_m=haversine_m(point, (hub.lat, hub.lon)),
    )


def quote_status(
    origin: PointMatch | None,
    destination: PointMatch | None,
    hub_distance_m: float | None,
    min_od_distance_m: float,
    in_hub_pairs: bool,
    pt_bike_failed: bool,
    offers_bike_option: bool,
) -> QuoteStatus:
    """The first status that applies. `hub_distance_m` is the haversine distance between the
    two hubs' centres; the three flags describe the pair and are read only once both points
    are matched to two hubs."""
    if origin is None or destination is None:
        return "one_point"
    points = (origin, destination)
    if any(item.status == "outside_zone" for item in points):
        return "outside_zone"
    if any(item.status == "no_hub_here" for item in points):
        return "no_hub_here"
    if origin.hub_id == destination.hub_id:
        return "same_hub"
    # The package's rule at `routing/od_permutations.py:30-35`.
    if hub_distance_m is not None and hub_distance_m < min_od_distance_m:
        return "under_minimum_distance"
    if pt_bike_failed:
        return "no_route"
    if not in_hub_pairs:
        return "removed_by_quality_check"
    if not offers_bike_option:
        return "no_bike_option"
    return "priced"


@dataclass(frozen=True)
class QuotedLeg:
    mode: str
    line: str | None
    from_name: str | None
    to_name: str | None
    duration_s: Number


@dataclass(frozen=True)
class QuotedOption:
    arc_id: str
    mode: RouteMode
    bike_legs: Number
    bike_price: Number | None
    pt_fare: Number | None
    car_parking_fee: Number | None
    car_cost: Number | None
    price: Number
    duration_s: Number
    transfers: Number
    legs: tuple[QuotedLeg, ...]
    flow: Number | None
    most_taken: bool


def transfers(legs: Sequence[RouteLeg]) -> int:
    return max(0, sum(1 for leg in legs if leg.mode not in WALKING_MODES) - 1)


def quoted_leg(leg: RouteLeg) -> QuotedLeg:
    return QuotedLeg(
        leg.mode,
        leg.line,
        leg.from_place,
        leg.to_place,
        Number(leg.duration_s, "seconds", "trip_planner", "headline"),
    )


def _headline(value: float | int, unit: str, source: NumberSource) -> Number:
    return Number(value, unit, source, "headline")


def has_car_option(options: Sequence[RouteOptionRow]) -> bool:
    return any(_is_quotable_car(option) for option in options)


def _is_quotable_car(option: RouteOptionRow) -> bool:
    return option.mode == "car" and option.car_cost_chf is not None


def offered_bike_options(
    options: Sequence[RouteOptionRow], solve_rows: Mapping[str, SolveRow]
) -> list[RouteOptionRow]:
    """The PT + bike options the model offers: those with a `PT+Bike` row and a bike price."""
    return [
        option
        for option in options
        if option.mode == "pt_bike"
        and (row := solve_rows.get(option.arc_id)) is not None
        and row.type == PT_BIKE
        and row.bike_price is not None
    ]


def quoted_options(
    options: Sequence[RouteOptionRow],
    solve_rows: Mapping[str, SolveRow],
    pt_fare_chf: float,
    car_parking_fee_chf: float,
) -> tuple[QuotedOption, ...]:
    """Every offered PT + bike option, the PT-only options and the car options of a pair, by
    mode then arc id; `most_taken` marks the largest flow of each mode."""
    offered = {option.arc_id for option in offered_bike_options(options, solve_rows)}
    kept = [
        option
        for option in options
        if (option.mode == "pt_bike" and option.arc_id in offered)
        or option.mode == "pt_only"
        or _is_quotable_car(option)
    ]
    kept.sort(key=lambda option: (MODE_ORDER.index(option.mode), option.arc_id))
    most_taken: set[str] = set()
    for mode in MODE_ORDER:
        flows = [
            (-solve_rows[o.arc_id].flow, o.arc_id)
            for o in kept
            if o.mode == mode and o.arc_id in solve_rows
        ]
        if flows:
            most_taken.add(min(flows)[1])
    return tuple(
        _quoted(
            option,
            solve_rows.get(option.arc_id),
            pt_fare_chf,
            car_parking_fee_chf,
            option.arc_id in most_taken,
        )
        for option in kept
    )


def _quoted(
    option: RouteOptionRow,
    row: SolveRow | None,
    pt_fare_chf: float,
    car_parking_fee_chf: float,
    most_taken: bool,
) -> QuotedOption:
    bike_legs = (option.bike_legs or 0) if option.mode == "pt_bike" else 0
    bike_price = row.bike_price if option.mode == "pt_bike" and row is not None else None
    price = option_price(
        option.mode,
        bike_legs,
        bike_price or 0.0,
        pt_fare_chf,
        option.car_cost_chf or 0.0,
        car_parking_fee_chf,
    )
    is_car = option.mode == "car"
    return QuotedOption(
        arc_id=option.arc_id,
        mode=option.mode,
        bike_legs=_headline(bike_legs, "bike_legs", "input"),
        bike_price=None
        if bike_price is None
        else _headline(bike_price, "chf_per_bike_leg", "model"),
        pt_fare=None if is_car else _headline(pt_fare_chf, "chf", "input"),
        car_parking_fee=_headline(car_parking_fee_chf, "chf", "input") if is_car else None,
        car_cost=_headline(option.car_cost_chf or 0.0, "chf", "input") if is_car else None,
        price=_headline(price, "chf", "derived"),
        duration_s=_headline(
            option_travel_time_s(
                option.mode,
                option.total_travel_time_s,
                option.total_transfer_time_s,
                option.parking_time_min,
            ),
            "seconds",
            "trip_planner",
        ),
        transfers=_headline(transfers(option.legs), "transfers", "derived"),
        legs=tuple(quoted_leg(leg) for leg in option.legs),
        flow=None if row is None else _headline(row.flow, "travellers", "model"),
        most_taken=most_taken,
    )


def leg_line_string(stored_leg_geometry: Sequence[Sequence[float]] | None) -> dict[str, Any] | None:
    """The stored geometry of a leg is `[lat, lon]` pairs; GeoJSON wants `[lon, lat]`."""
    if not stored_leg_geometry:
        return None
    return {
        "type": "LineString",
        "coordinates": [[position[1], position[0]] for position in stored_leg_geometry],
    }


def leg_geometry(option_geometry: Any, leg_index: int) -> Sequence[Sequence[float]] | None:
    """The stored geometry of the leg at `leg_index` of an option, when it has one."""
    for item in option_geometry or []:
        if item.get("leg_idx") == leg_index:
            geometry: Sequence[Sequence[float]] | None = item.get("geometry")
            return geometry
    return None
