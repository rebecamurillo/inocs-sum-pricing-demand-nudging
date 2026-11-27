"""The fake `CityPreparation`: a small deterministic city written in the package's file shapes.

About 30 stops, 12 bike stations, 6 hubs and 24 hub pairs, every mode present, two pairs closer
than the default minimum trip distance, one pair without a bike option, stations that run out
of bikes or docks; all within 1 km of the Geneva preset centre (ARCHITECTURE.md § 11.1).
What it does besides is read from the `pricing_model` entry of the fake settings: fail a step
with a code, hold a step until its run is released, pace the routes step pair by pair.
"""

import json
import math
import random
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from pricing_demo.application.ports.city_preparation import (
    PreparationRequest,
    Progress,
    RouteFailed,
    ignore_route_failure,
)
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.domain.city_datasets import GENEVA_PRESET
from pricing_demo.domain.failure_codes import failure_reason
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.hold import hold_until_released

METRES_PER_DEGREE_LATITUDE = 111_320.0

# East and north of the preset centre, in metres. H1 and H2 are 300 m apart: both of their
# pairs are under the default minimum trip distance (500 m).
HUB_METRES: Mapping[str, tuple[float, float]] = {
    "H1": (0, 0),
    "H2": (300, 0),
    "H3": (-600, 300),
    "H4": (650, -450),
    "H5": (-500, -500),
    "H6": (100, 700),
}
# Six of the thirty ordered pairs are not requested, which leaves 24.
NOT_REQUESTED = frozenset(
    {("H3", "H4"), ("H4", "H3"), ("H3", "H5"), ("H5", "H3"), ("H5", "H6"), ("H6", "H5")}
)
NO_BIKE_PAIR = ("H5", "H1")
STOPS_PER_HUB = 5
BIKE_STATIONS_PER_HUB = 2
# The public code of the fake bus and tram routes: the worker's fake feed has a shape for the bus
# route only, so the fake city draws both a timetable shape and a straight line.
TRANSIT_CODES = {"BUS": "1", "TRAM": "T2"}
# The retries the fake trip planner client makes before it reports a technical failure.
FAKE_RETRIES = 3
# The fake values a failure's reason is written with.
FAKE_TRIP_PLANNER_URL = "http://trip-planner.fake/otp"
FAKE_SOLVER_STATUS = "INFEASIBLE"


class FakeSettingsSource(Protocol):
    def read(self) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class FakeStation:
    station_id: str
    kind: str
    name: str
    lat: float
    lon: float
    hub_id: str


def _offset(lat: float, lon: float, east: float, north: float) -> tuple[float, float]:
    return (
        lat + north / METRES_PER_DEGREE_LATITUDE,
        lon + east / (METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(lat))),
    )


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


@cache
def hub_positions() -> dict[str, tuple[float, float]]:
    centre = (GENEVA_PRESET.centre_lat, GENEVA_PRESET.centre_lon)
    return {name: _offset(*centre, *metres) for name, metres in HUB_METRES.items()}


@cache
def stations() -> tuple[FakeStation, ...]:
    found: list[FakeStation] = []
    for hub_id, (lat, lon) in hub_positions().items():
        for index in range(STOPS_PER_HUB):
            angle = math.radians(index * 72)
            near = _offset(lat, lon, 60 * math.cos(angle), 60 * math.sin(angle))
            found.append(
                FakeStation(
                    f"pts_FAKE{hub_id}{index}",
                    "pt",
                    f"Fake stop {hub_id}-{index + 1}",
                    *near,
                    hub_id,
                )
            )
        for index in range(BIKE_STATIONS_PER_HUB):
            angle = math.radians(36 + index * 180)
            near = _offset(lat, lon, 30 * math.cos(angle), 30 * math.sin(angle))
            found.append(
                FakeStation(
                    f"bss_fake_{hub_id}_{index}",
                    "bs",
                    f"Fake bikes {hub_id}-{index + 1}",
                    *near,
                    hub_id,
                )
            )
    return tuple(found)


@cache
def hub_pairs() -> tuple[tuple[str, str], ...]:
    return tuple(
        (origin, destination)
        for origin in HUB_METRES
        for destination in HUB_METRES
        if origin != destination and (origin, destination) not in NOT_REQUESTED
    )


def _stations_file() -> dict[str, Any]:
    return {
        "center": {"lat": GENEVA_PRESET.centre_lat, "lon": GENEVA_PRESET.centre_lon},
        "radius_m": GENEVA_PRESET.radius_m,
        "stations": [
            {
                "station_id": item.station_id,
                "type": item.kind,
                "name": item.name,
                "lat": item.lat,
                "lon": item.lon,
            }
            for item in stations()
        ],
    }


def _point(lat: float, lon: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [lon, lat]}


def _collection(features: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def _hubs_files() -> dict[str, dict[str, Any]]:
    hubs, linked, polygons = [], [], []
    for hub_id, (lat, lon) in hub_positions().items():
        members = [item for item in stations() if item.hub_id == hub_id]
        hubs.append(
            {
                "type": "Feature",
                "geometry": _point(lat, lon),
                "properties": {
                    "hub_id": hub_id,
                    "label": "PT+bike station",
                    "bike_stations": [m.station_id for m in members if m.kind == "bs"],
                    "pt_stations": [m.station_id for m in members if m.kind == "pt"],
                    "lines": ["1", "2"],
                },
            }
        )
        south_west, north_east = _offset(lat, lon, -50, -50), _offset(lat, lon, 50, 50)
        ring = [
            [south_west[1], south_west[0]],
            [north_east[1], south_west[0]],
            [north_east[1], north_east[0]],
            [south_west[1], north_east[0]],
            [south_west[1], south_west[0]],
        ]
        polygons.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"cluster": hub_id},
            }
        )
    for item in stations():
        linked.append(
            {
                "type": "Feature",
                "geometry": _point(item.lat, item.lon),
                "properties": {
                    "identifier": item.station_id,
                    "station_type": "bike" if item.kind == "bs" else "pt",
                    "hub_id": item.hub_id,
                },
            }
        )
    return {
        "hubs.geojson": _collection(hubs),
        "stations_hubs.geojson": _collection(linked),
        "hub_polygons.geojson": _collection(polygons),
    }


def _leg(mode: str, origin: str, destination: str, metres: float, **extra: Any) -> dict[str, Any]:
    return {
        "mode": mode,
        "duration_s": round(metres / (4.5 if mode == "BICYCLE" else 6.0), 1),
        "distance_m": round(metres, 1),
        "line_publicCode": {"publicCode": TRANSIT_CODES[mode]} if mode in TRANSIT_CODES else {},
        "from_place": origin,
        "to_place": destination,
        "rented_bike": mode == "BICYCLE",
        **extra,
    }


def _arc(arc_id: str, legs: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    for index, leg in enumerate(legs):
        leg["leg_idx"] = index
    travel = sum(leg["duration_s"] for leg in legs if leg["mode"] != "FOOT")
    transfer = sum(leg["duration_s"] for leg in legs if leg["mode"] == "FOOT")
    return {
        "arc_id": arc_id,
        "total_travel_time_s": travel,
        "total_transfer_time_s": transfer,
        "total_distance_m": sum(leg["distance_m"] for leg in legs),
        "legs": legs,
        **extra,
    }


def _routes() -> tuple[dict[str, Any], dict[str, Any]]:
    positions = hub_positions()
    results, geometries = [], []
    for number, (origin, destination) in enumerate(hub_pairs(), start=1):
        metres = haversine_m(positions[origin], positions[destination]) * 1.2
        pt_mode = "TRAM" if number % 3 == 0 else "BUS"
        bike = (
            []
            if (origin, destination) == NO_BIKE_PAIR
            else [
                _arc(
                    f"{number}b",
                    [
                        _leg("BICYCLE", origin, "stop", metres * 0.2),
                        _leg(pt_mode, "stop", destination, metres * 0.8),
                    ],
                    access_bike=True,
                    egress_bike=False,
                )
            ]
        )
        public = [
            _arc(
                f"{number}p",
                [
                    _leg("FOOT", origin, "stop", metres * 0.1),
                    _leg(pt_mode, "stop", destination, metres),
                ],
            )
        ]
        car = [_arc(f"car_{number}", [_leg("CAR", origin, destination, metres)])]
        results.append(
            {
                "from_id": origin,
                "to_id": destination,
                "arc_pt_bike": bike,
                "arc_pt_only": public,
                "arc_car": car,
            }
        )
        for arc in (*bike, *public, *car):
            start, end = positions[origin], positions[destination]
            geometries.append(
                {
                    "arc_id": arc["arc_id"],
                    "legs_geometry": [
                        {"leg_idx": leg["leg_idx"], "geometry": [list(start), list(end)]}
                        for leg in arc["legs"]
                    ],
                }
            )
    return {"od_results": results}, {"geometries": geometries}


def _without_failed(
    routes: dict[str, Any], geometry: dict[str, Any], failures: Sequence[RouteFailure]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A failed `pt_bike` query drops the pair, a failed `car` query empties its car option."""
    dropped = {
        (item.origin_hub, item.destination_hub) for item in failures if item.query == "pt_bike"
    }
    no_car = {(item.origin_hub, item.destination_hub) for item in failures if item.query == "car"}
    kept: list[dict[str, Any]] = []
    removed_arcs: set[str] = set()
    for result in routes["od_results"]:
        pair = (result["from_id"], result["to_id"])
        arcs = (*result["arc_pt_bike"], *result["arc_pt_only"], *result["arc_car"])
        if pair in dropped:
            removed_arcs.update(arc["arc_id"] for arc in arcs)
            continue
        if pair in no_car:
            removed_arcs.update(arc["arc_id"] for arc in result["arc_car"])
            result = {**result, "arc_car": []}
        kept.append(result)
    geometries = [item for item in geometry["geometries"] if item["arc_id"] not in removed_arcs]
    return {"od_results": kept}, {"geometries": geometries}


def _with_car_costs(arc: Mapping[str, Any], parameters: Any) -> dict[str, Any]:
    """The two fields the package writes on a car arc of an instance (`generator.py:156-161`),
    here from a fixed formula that draws nothing from the seeded generator: the parking time is
    the middle of the park-time range, the cost 0.2 CHF a kilometre plus 1 CHF."""
    return {
        **arc,
        "parking_time_min": (parameters.min_park_time_min + parameters.max_park_time_min) / 2,
        "total_travel_cost": arc["total_distance_m"] / 1000 * 0.2 + 1.0,
    }


def _instance(
    request: PreparationRequest, routes: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters = request.parameters
    rng = random.Random(int(parameters.seed))
    capacity = int(parameters.fixed_capacity)
    bike_ids = [item.station_id for item in stations() if item.kind == "bs"]
    inventory = {
        station: round(
            rng.uniform(parameters.min_inventory_pct, parameters.max_inventory_pct) * capacity
        )
        for station in bike_ids
    }
    # Two stations without a bike and two without a free dock: they run out under a simulation.
    for station in bike_ids[:2]:
        inventory[station] = 0
    for station in bike_ids[2:4]:
        inventory[station] = capacity
    positions = hub_positions()
    pairs, bike_arcs, public_arcs, car_arcs = [], [], [], []
    # The package keeps the arcs of an instance per pair, keyed `{from}_{to}`.
    bike_by_pair: dict[str, Any] = {}
    public_by_pair: dict[str, Any] = {}
    car_by_pair: dict[str, Any] = {}
    for result in routes["od_results"]:
        demand = rng.randint(int(parameters.min_demand), int(parameters.max_demand))
        pairs.append(
            {
                "origin": result["from_id"],
                "destination": result["to_id"],
                "demand": demand,
                "euclid_dist": round(
                    haversine_m(positions[result["from_id"]], positions[result["to_id"]])
                ),
            }
        )
        key = f"{result['from_id']}_{result['to_id']}"
        cars = [_with_car_costs(arc, parameters) for arc in result["arc_car"]]
        bike_by_pair[key] = result["arc_pt_bike"]
        public_by_pair[key] = result["arc_pt_only"]
        car_by_pair[key] = cars
        bike_arcs += result["arc_pt_bike"]
        public_arcs += result["arc_pt_only"]
        car_arcs += cars
    instance: dict[str, Any] = {
        "random_seed": int(parameters.seed),
        "info": {
            "num_OD_pairs": len(pairs),
            "num_bike_stations": len(bike_ids),
            "total_demand": sum(item["demand"] for item in pairs),
        },
        "bike_stations": {
            "station_list": bike_ids,
            "station_capacity": dict.fromkeys(bike_ids, capacity),
            "station_inventory": inventory,
        },
        "OD_pairs": pairs,
        "arcs_pt_bike": bike_by_pair,
        "arcs_pt_only": public_by_pair,
        "car_paths": car_by_pair,
        "delta_ia": {
            arc["arc_id"]: {bike_ids[i % len(bike_ids)]: -1} for i, arc in enumerate(bike_arcs)
        },
    }
    counts = {
        "hub_pairs": len(pairs),
        "travellers": instance["info"]["total_demand"],
        "bike_stations": len(bike_ids),
        "options": {"pt_bike": len(bike_arcs), "pt_only": len(public_arcs), "car": len(car_arcs)},
    }
    return instance, counts


def _write(folder: Path, name: str, content: Mapping[str, Any]) -> None:
    (folder / name).write_text(json.dumps(content, sort_keys=True) + "\n", encoding="utf-8")


class FakeCityPreparation:
    """Passes the same contract suite as the real adapter (story 2-7 adds that one)."""

    def __init__(self, settings: FakeSettingsSource, waiter: Waiter) -> None:
        self._settings = settings
        self._waiter = waiter

    def prepare(
        self,
        request: PreparationRequest,
        progress: Progress,
        stop: StopSignal,
        route_failed: RouteFailed = ignore_route_failure,
    ) -> StepOutcome:
        step = request.step
        if stop.is_set():
            return StepOutcome.stopped_on_signal()
        if self._config().get("hold_at") == step.value and not hold_until_released(
            self._settings, self._waiter, request.run_id, stop
        ):
            return StepOutcome.stopped_on_signal()
        failure = self._config().get("fail_at")
        if isinstance(failure, dict) and failure.get("step") == step.value:
            code = str(failure["code"])
            return StepOutcome.failed(code, failure_reason(code, **self._values(request)))
        if step is StepName.AREA:
            _write(request.working_dir, "stations.json", _stations_file())
            stops = len([item for item in stations() if item.kind == "pt"])
            return StepOutcome.done({"stops": stops, "bike_stations": len(stations()) - stops})
        if step is StepName.HUBS:
            for name, content in _hubs_files().items():
                _write(request.working_dir, name, content)
            return StepOutcome.done({"hubs": len(HUB_METRES)})
        if step is StepName.ROUTES:
            if not self._pace(progress, stop):
                return StepOutcome.stopped_on_signal()
            failures = self._route_failures()
            for failure in failures:
                route_failed(failure)
            routes, geometry = _without_failed(*_routes(), failures)
            _write(request.working_dir, "od_routes.json", routes)
            _write(request.working_dir, "od_geometry.json", geometry)
            return StepOutcome.done(
                {
                    "hub_pairs_requested": len(hub_pairs()),
                    "hub_pairs_with_routes": len(routes["od_results"]),
                    "hub_pairs_removed": 0,
                    "retries": FAKE_RETRIES,
                }
            )
        # The routes the travellers step reads are the routes step's own file, which a failed
        # query may have thinned.
        stored = request.working_dir / "od_routes.json"
        routes = (
            json.loads(stored.read_text(encoding="utf-8")) if stored.is_file() else _routes()[0]
        )
        instance, counts = _instance(request, routes)
        _write(request.working_dir, "Instance_1.json", instance)
        # What the package's parser counts: BICYCLE legs of a pt_bike arc, 0 for the others.
        bike_legs = {
            arc["arc_id"]: sum(1 for leg in arc["legs"] if leg["mode"] == "BICYCLE")
            for arcs in instance["arcs_pt_bike"].values()
            for arc in arcs
        }
        for key in ("arcs_pt_only", "car_paths"):
            for arcs in instance[key].values():
                for arc in arcs:
                    bike_legs[arc["arc_id"]] = 0
        _write(request.working_dir, "option_bike_legs.json", bike_legs)
        return StepOutcome.done(counts)

    def _config(self) -> Mapping[str, Any]:
        config = self._settings.read().get("pricing_model")
        return config if isinstance(config, dict) else {}

    def _route_failures(self) -> list[RouteFailure]:
        """The listed failures whose pair the fake city requests; a pair and query once."""
        listed = self._config().get("route_failures")
        found: dict[tuple[str, str, str], RouteFailure] = {}
        for item in listed if isinstance(listed, list) else []:
            pair = (item["origin_hub"], item["destination_hub"])
            if pair not in hub_pairs():
                continue
            attempts = 1 + FAKE_RETRIES if item["kind"] == "technical" else 1
            found.setdefault(
                (*pair, item["query"]),
                RouteFailure(*pair, item["query"], item["kind"], item["message"], attempts),
            )
        return list(found.values())

    def _pace(self, progress: Progress, stop: StopSignal) -> bool:
        pace_ms = int(self._config().get("routes_pace_ms") or 0)
        total = len(hub_pairs())
        if pace_ms <= 0:
            return True
        never = threading.Event()
        for done in range(1, total + 1):
            if stop.is_set():
                return False
            self._waiter.wait(pace_ms / 1000, never)
            progress(done, total)
        return True

    @staticmethod
    def _values(request: PreparationRequest) -> dict[str, object]:
        return {
            "url": FAKE_TRIP_PLANNER_URL,
            "d": request.period.routing_date.isoformat(),
            "name": FAKE_SOLVER_STATUS,
            "check": "the travellers of a pair do not add up",
            "n": 9,
            "exception_type": "RuntimeError",
            "message": "fake failure",
        }
