"""The built instance as rows: pure readers of the files the build steps write (the package's
JSON shapes, ARCHITECTURE.md § 4.1), and the counts derived from them.

Nothing here computes what the model computes: route times, distances and demands are read
as they are. A file that does not have the expected shape raises `ValueError`; the ingestion
turns it into a failed step.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pricing_demo.domain.numbers import Number

ROUTE_QUERIES = ("pt_bike", "car")
FAILURE_KINDS = ("technical", "no_route")
STREET_MODES = frozenset({"BICYCLE", "CAR", "FOOT", "WALK"})

LineKind = Literal["street", "shape", "straight"]
RouteMode = Literal["pt_bike", "pt_only", "car"]
# The arc list of an `od_routes.json` pair, and the arc list of the instance, of each mode.
ROUTE_ARC_LISTS: Mapping[RouteMode, str] = {
    "pt_bike": "arc_pt_bike",
    "pt_only": "arc_pt_only",
    "car": "arc_car",
}
INSTANCE_ARC_LISTS: Mapping[RouteMode, str] = {
    "pt_bike": "arcs_pt_bike",
    "pt_only": "arcs_pt_only",
    "car": "car_paths",
}


@dataclass(frozen=True)
class StationRow:
    station_id: str
    kind: Literal["pt", "bs"]
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class HubRow:
    hub_id: str
    label: str
    lat: float
    lon: float
    outline: Mapping[str, Any] | None
    pt_station_ids: tuple[str, ...]
    bike_station_ids: tuple[str, ...]
    lines: tuple[str, ...]


@dataclass(frozen=True)
class StationHubRow:
    station_id: str
    hub_id: str


@dataclass(frozen=True)
class HubPairRow:
    origin_hub: str
    destination_hub: str
    demand: float
    euclid_dist_m: float


@dataclass(frozen=True)
class RoutePairRow:
    """A hub pair the routes step routed: the pair has at least one route in `od_routes.json`."""

    origin_hub: str
    destination_hub: str


@dataclass(frozen=True)
class RouteLeg:
    mode: str
    duration_s: float
    distance_m: float
    line_kind: LineKind


@dataclass(frozen=True)
class RouteOptionRow:
    """`bike_legs` is filled from the package's parser through `option_bike_legs.json`; the
    other parser columns (`bike_time_min` ...) are not part of the row and stay null."""

    arc_id: str
    origin_hub: str
    destination_hub: str
    mode: RouteMode
    total_travel_time_s: float
    total_transfer_time_s: float
    total_distance_m: float
    legs: tuple[RouteLeg, ...]
    geometry: Any
    bike_legs: int | None = None


@dataclass(frozen=True)
class StationBikesRow:
    station_id: str
    capacity: float
    inventory_start: float


@dataclass(frozen=True)
class OptionStationDeltaRow:
    arc_id: str
    station_id: str
    delta: float


@dataclass(frozen=True)
class RouteFailure:
    origin_hub: str
    destination_hub: str
    query: Literal["pt_bike", "car"]
    kind: Literal["technical", "no_route"]
    message: str
    attempts: int


@dataclass(frozen=True)
class RoutesSummary:
    queries: int
    queries_failed: int
    failure_pct: float
    pairs_without_public_transport: int
    pairs_without_car: int
    retries: int
    run_id: str | None


def _malformed(name: str, error: Exception) -> ValueError:
    return ValueError(f"{name} is not in the expected shape: {type(error).__name__}: {error}")


def _features(collection: Any, name: str) -> list[Mapping[str, Any]]:
    try:
        features = collection["features"]
        for feature in features:
            feature["properties"], feature["geometry"]
    except (KeyError, TypeError) as error:
        raise _malformed(name, error) from error
    return list(features)


def stations_from(stations_json: Any) -> tuple[StationRow, ...]:
    try:
        rows = tuple(
            StationRow(
                str(item["station_id"]),
                item["type"],
                str(item["name"]),
                float(item["lat"]),
                float(item["lon"]),
            )
            for item in stations_json["stations"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _malformed("stations.json", error) from error
    if any(row.kind not in ("pt", "bs") for row in rows):
        raise ValueError("stations.json has a station whose type is neither pt nor bs.")
    return tuple(sorted(rows, key=lambda row: row.station_id))


def hubs_from(hubs_geojson: Any, polygons_geojson: Any) -> tuple[HubRow, ...]:
    outlines = {
        str(item["properties"]["cluster"]): item["geometry"]
        for item in _features(polygons_geojson, "hub_polygons.geojson")
    }
    try:
        rows = tuple(
            HubRow(
                hub_id=str(feature["properties"]["hub_id"]),
                label=str(feature["properties"]["label"]),
                lat=float(feature["geometry"]["coordinates"][1]),
                lon=float(feature["geometry"]["coordinates"][0]),
                outline=outlines.get(str(feature["properties"]["hub_id"])),
                pt_station_ids=tuple(feature["properties"]["pt_stations"]),
                bike_station_ids=tuple(feature["properties"]["bike_stations"]),
                lines=tuple(str(line) for line in feature["properties"]["lines"]),
            )
            for feature in _features(hubs_geojson, "hubs.geojson")
        )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise _malformed("hubs.geojson", error) from error
    return tuple(sorted(rows, key=lambda row: row.hub_id))


def station_hubs_from(stations_hubs_geojson: Any) -> tuple[StationHubRow, ...]:
    try:
        rows = tuple(
            StationHubRow(
                str(feature["properties"]["identifier"]), str(feature["properties"]["hub_id"])
            )
            for feature in _features(stations_hubs_geojson, "stations_hubs.geojson")
        )
    except (KeyError, TypeError) as error:
        raise _malformed("stations_hubs.geojson", error) from error
    return tuple(sorted(rows, key=lambda row: row.station_id))


def hub_pairs_from(instance: Any) -> tuple[HubPairRow, ...]:
    try:
        rows = tuple(
            HubPairRow(
                str(item["origin"]),
                str(item["destination"]),
                item["demand"],
                item["euclid_dist"],
            )
            for item in instance["OD_pairs"]
        )
    except (KeyError, TypeError) as error:
        raise _malformed("Instance_1.json", error) from error
    return tuple(sorted(rows, key=lambda row: (row.origin_hub, row.destination_hub)))


def route_pairs(od_routes: Any) -> tuple[RoutePairRow, ...]:
    try:
        rows = tuple(
            RoutePairRow(str(pair["from_id"]), str(pair["to_id"]))
            for pair in od_routes["od_results"]
        )
    except (KeyError, TypeError) as error:
        raise _malformed("od_routes.json", error) from error
    return tuple(sorted(rows, key=lambda row: (row.origin_hub, row.destination_hub)))


def line_kind(mode: str, public_code: str | None, routes_with_shapes: Collection[str]) -> LineKind:
    """Street modes follow a street path; a transit leg follows its timetable shape when its
    route has one in the feed, and is drawn straight otherwise."""
    if mode in STREET_MODES:
        return "street"
    if public_code is not None and public_code in routes_with_shapes:
        return "shape"
    return "straight"


def _legs(arc: Mapping[str, Any], routes_with_shapes: Collection[str]) -> tuple[RouteLeg, ...]:
    legs = []
    for leg in arc["legs"]:
        code = (leg.get("line_publicCode") or {}).get("publicCode")
        legs.append(
            RouteLeg(
                leg["mode"],
                leg["duration_s"],
                leg["distance_m"],
                line_kind(leg["mode"], code, routes_with_shapes),
            )
        )
    return tuple(legs)


def route_options_from(
    od_routes: Any,
    od_geometry: Any,
    instance: Any,
    routes_with_shapes: Collection[str],
    bike_legs: Mapping[str, int] | None = None,
) -> tuple[RouteOptionRow, ...]:
    """The options of the instance: each arc of `od_routes.json` that the instance kept, with
    its pair, its mode (the list it sits in), its legs and its geometry."""
    try:
        in_instance = {
            mode: {arc["arc_id"] for arc in _instance_arcs(instance[name])}
            for mode, name in INSTANCE_ARC_LISTS.items()
        }
        geometries = {item["arc_id"]: item["legs_geometry"] for item in od_geometry["geometries"]}
        rows: list[RouteOptionRow] = []
        for pair in od_routes["od_results"]:
            for mode, name in ROUTE_ARC_LISTS.items():
                for arc in pair[name]:
                    if arc["arc_id"] not in in_instance[mode]:
                        continue
                    rows.append(
                        RouteOptionRow(
                            str(arc["arc_id"]),
                            str(pair["from_id"]),
                            str(pair["to_id"]),
                            mode,
                            arc["total_travel_time_s"],
                            arc["total_transfer_time_s"],
                            arc["total_distance_m"],
                            _legs(arc, routes_with_shapes),
                            geometries.get(arc["arc_id"], []),
                            _bike_legs(bike_legs, str(arc["arc_id"])),
                        )
                    )
    except (KeyError, TypeError) as error:
        raise _malformed("od_routes.json, od_geometry.json or Instance_1.json", error) from error
    return tuple(sorted(rows, key=lambda row: row.arc_id))


def _instance_arcs(found: Any) -> list[Any]:
    """The package writes the arcs of an instance as one list per pair, keyed `{from}_{to}`."""
    if isinstance(found, Mapping):
        return [arc for arcs in found.values() for arc in arcs]
    return list(found)


def _bike_legs(found: Mapping[str, int] | None, arc_id: str) -> int | None:
    if found is None or arc_id not in found:
        return None
    value = found[arc_id]
    if isinstance(value, bool) or not isinstance(value, int):
        raise _malformed("option_bike_legs.json", TypeError(f"arc {arc_id}: {value!r}"))
    return value


def station_bikes_from(instance: Any) -> tuple[StationBikesRow, ...]:
    try:
        bikes = instance["bike_stations"]
        rows = tuple(
            StationBikesRow(
                str(station),
                bikes["station_capacity"][station],
                bikes["station_inventory"][station],
            )
            for station in bikes["station_list"]
        )
    except (KeyError, TypeError) as error:
        raise _malformed("Instance_1.json", error) from error
    return tuple(sorted(rows, key=lambda row: row.station_id))


def deltas_from(instance: Any) -> tuple[OptionStationDeltaRow, ...]:
    try:
        rows = tuple(
            OptionStationDeltaRow(str(arc), str(station), delta)
            for arc, by_station in instance["delta_ia"].items()
            for station, delta in by_station.items()
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise _malformed("Instance_1.json", error) from error
    return tuple(sorted(rows, key=lambda row: (row.arc_id, row.station_id)))


def area_counts(stations: Sequence[StationRow]) -> dict[str, int]:
    stops = sum(1 for row in stations if row.kind == "pt")
    return {"stops": stops, "bike_stations": len(stations) - stops}


def hubs_counts(hubs: Sequence[HubRow]) -> dict[str, int]:
    return {"hubs": len(hubs)}


def failure_pct(queries_failed: int, queries: int) -> float:
    return queries_failed / queries * 100 if queries else 0.0


def routes_counts(
    od_routes: Any, reported: Mapping[str, Any], failures: Sequence[RouteFailure]
) -> dict[str, int | float]:
    """The pairs and retries the step reported, the pairs of `od_routes.json`, and the
    failed queries the step recorded: `queries` is two per pair requested."""
    try:
        with_routes = len(od_routes["od_results"])
    except (KeyError, TypeError) as error:
        raise _malformed("od_routes.json", error) from error
    removed = int(reported.get("hub_pairs_removed", 0))
    requested = int(reported.get("hub_pairs_requested", with_routes + removed))
    queries = 2 * requested
    return {
        "hub_pairs_requested": requested,
        "hub_pairs_with_routes": with_routes,
        "hub_pairs_removed": removed,
        "queries": queries,
        "queries_failed": len(failures),
        "failure_pct": failure_pct(len(failures), queries),
        "retries": int(reported.get("retries", 0)),
    }


def instance_counts(instance: Any) -> dict[str, Any]:
    try:
        return {
            "hub_pairs": len(instance["OD_pairs"]),
            "travellers": instance["info"]["total_demand"],
            "bike_stations": len(instance["bike_stations"]["station_list"]),
            "options": {
                mode: len(_instance_arcs(instance[name]))
                for mode, name in INSTANCE_ARC_LISTS.items()
            },
        }
    except (KeyError, TypeError) as error:
        raise _malformed("Instance_1.json", error) from error


def routes_summary(
    counts: Mapping[str, Any], failures: Sequence[RouteFailure], run_id: str | None
) -> RoutesSummary:
    without_public_transport = {
        (item.origin_hub, item.destination_hub) for item in failures if item.query == "pt_bike"
    }
    without_car = {
        (item.origin_hub, item.destination_hub) for item in failures if item.query == "car"
    } - without_public_transport
    return RoutesSummary(
        queries=counts["queries"],
        queries_failed=counts["queries_failed"],
        failure_pct=counts["failure_pct"],
        pairs_without_public_transport=len(without_public_transport),
        pairs_without_car=len(without_car),
        retries=counts["retries"],
        run_id=run_id,
    )


def headline_counts(
    area: Mapping[str, Any],
    hubs: Mapping[str, Any],
    routes: Mapping[str, Any],
    instance: Mapping[str, Any],
) -> dict[str, Number]:
    """The five numbers of the first screen, in the order the screen lists them."""

    def read(value: float | int, unit: str) -> Number:
        return Number(value, unit, "input", "headline")

    return {
        "stops": read(area["stops"], "stops"),
        "bike_stations": read(area["bike_stations"], "bike_stations"),
        "hubs": read(hubs["hubs"], "hubs"),
        "hub_pairs_with_routes": read(routes["hub_pairs_with_routes"], "hub_pairs"),
        "travellers": read(instance["travellers"], "travellers"),
    }
