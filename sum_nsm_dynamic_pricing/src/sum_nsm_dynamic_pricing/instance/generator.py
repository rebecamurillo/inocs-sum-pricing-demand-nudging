# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from __future__ import annotations

import json
import random
from pathlib import Path

from ..config import InstanceParams
from ..utils.constants import (
    CAR_DEPRECIATION_COST_CHF,
    CAR_EFFICIENCY_L_PER_100KM,
    CAR_FUEL_PRICE_CHF_PER_L,
)
from ..utils.geo import haversine
from ..utils.io import read_json, write_json
from .bike_resolver import BikeStationResolver
from .delta import compute_delta_ia


def _load_hub_properties(hubs_geojson: dict) -> tuple[dict, dict, dict]:
    hub_coords = {}
    hub_to_bss = {}
    hub_is_pt_bike = {}
    pt_to_hub = {}

    for feature in hubs_geojson.get("features", []):
        props = feature["properties"]
        hub_id = props["hub_id"]
        lon, lat = feature["geometry"]["coordinates"]
        hub_coords[hub_id] = (lat, lon)
        hub_to_bss[hub_id] = props.get("bike_stations", [])
        hub_is_pt_bike[hub_id] = props.get("label", "").lower() == "pt+bike station"
        for pt_station in props.get("pt_stations", []):
            pt_to_hub[pt_station.strip()] = hub_id

    return hub_coords, hub_to_bss, hub_is_pt_bike, pt_to_hub


def _convert_arc_times(arc: dict) -> None:
    arc["total_distance_km"] = arc.get("total_distance_m", 0.0) / 1000.0
    arc["total_travel_time_min"] = arc.get("total_travel_time_s", 0.0) / 60.0
    arc["total_transfer_time_min"] = arc.get("total_transfer_time_s", 0.0) / 60.0
    for leg in arc.get("legs", []):
        leg["duration_min"] = leg.get("duration_s", 0.0) / 60.0
        leg["distance_km"] = leg.get("distance_m", 0.0) / 1000.0


def generate_instance(
    od_routes_path: Path,
    stations_path: Path,
    hubs_geojson_path: Path,
    output_dir: Path,
    params: InstanceParams,
    seed: int | None = None,
) -> Path:
    if seed is not None:
        random.seed(seed)

    fuel_chf_per_km = CAR_FUEL_PRICE_CHF_PER_L * CAR_EFFICIENCY_L_PER_100KM / 100.0

    merged = read_json(Path(od_routes_path))
    stations_payload = read_json(Path(stations_path))
    hubs_geojson = read_json(Path(hubs_geojson_path))

    bike_stations = [station for station in stations_payload.get("stations", []) if station.get("type") == "bs"]
    pt_stations = [station for station in stations_payload.get("stations", []) if station.get("type") == "pt"]

    name_to_id = {station["name"].strip().lower(): station["station_id"] for station in bike_stations}
    id_to_name = {station_id: name for name, station_id in name_to_id.items()}
    station_coords = {station["station_id"]: (station["lat"], station["lon"]) for station in bike_stations}

    pt_name_to_id = {station["name"].strip(): station["station_id"] for station in pt_stations}
    pt_coords_by_id = {station["station_id"]: (station["lat"], station["lon"]) for station in pt_stations}

    hub_coords, hub_to_bss, hub_is_pt_bike, pt_to_hub = _load_hub_properties(hubs_geojson)

    resolver = BikeStationResolver(
        name_to_id=name_to_id,
        id_to_name=id_to_name,
        station_coords=station_coords,
        hub_coords=hub_coords,
        hub_to_bss=hub_to_bss,
        pt_name_to_id=pt_name_to_id,
        pt_coords_by_id=pt_coords_by_id,
        pt_to_hub=pt_to_hub,
    )

    station_ids = list(name_to_id.values())
    station_capacity = {station_id: params.fixed_capacity for station_id in station_ids}
    station_inventory = {}
    for station_id, capacity in station_capacity.items():
        low = min(int(capacity * params.min_inventory_pct), capacity)
        high = min(int(capacity * params.max_inventory_pct), capacity)
        station_inventory[station_id] = random.randint(low, high)

    bike_station_info = {
        "station_list": station_ids,
        "station_capacity": station_capacity,
        "station_inventory": station_inventory,
    }

    od_pairs = []
    arcs_pt_bike = {}
    arcs_pt_only = {}
    car_paths = {}
    origins = set()
    destinations = set()
    total_demand = 0

    for od in merged.get("od_results", []):
        origin = od.get("from_id")
        destination = od.get("to_id")
        key = f"{origin}_{destination}"

        demand = random.randint(params.min_demand, params.max_demand)
        od_pairs.append({"origin": origin, "destination": destination, "demand": demand})
        origins.add(origin)
        destinations.add(destination)
        total_demand += demand

        pt_bike_out = []
        for arc in od.get("arc_pt_bike", []):
            legs = arc.get("legs", [])
            first_is_bike = bool(legs and legs[0].get("mode") == "BICYCLE")
            last_is_bike = bool(legs and legs[-1].get("mode") == "BICYCLE")
            if (first_is_bike and not hub_is_pt_bike.get(origin, False)) or (last_is_bike and not hub_is_pt_bike.get(destination, False)):
                continue

            keep_arc = True
            for index, leg in enumerate(legs):
                if leg.get("mode") != "BICYCLE":
                    continue
                if not resolver.is_bs(leg.get("from_place", "")):
                    candidate = resolver.infer_from_station(legs, index, origin)
                    if candidate:
                        leg["from_place"] = resolver.canon(candidate)
                if not resolver.is_bs(leg.get("to_place", "")):
                    if not resolver.fix_to_station(leg, destination):
                        keep_arc = False
                        break
                leg["to_place"] = resolver.canon(leg.get("to_place"))

            if not keep_arc:
                continue

            _convert_arc_times(arc)
            pt_bike_out.append(arc)

        arcs_pt_bike[key] = pt_bike_out

        pt_only = od.get("arc_pt_only", [])
        for arc in pt_only:
            _convert_arc_times(arc)
        arcs_pt_only[key] = pt_only

        cars = od.get("arc_car", [])
        for arc in cars:
            _convert_arc_times(arc)
            parking_time = random.uniform(params.min_park_time, params.max_park_time)
            arc["parking_time_min"] = parking_time
            arc["total_travel_and_parking_time_min"] = parking_time + arc["total_travel_time_min"]
            arc["total_travel_cost"] = arc["total_distance_km"] * fuel_chf_per_km + CAR_DEPRECIATION_COST_CHF
        car_paths[key] = cars

    for od in od_pairs:
        origin_coord = hub_coords.get(od["origin"])
        destination_coord = hub_coords.get(od["destination"])
        if origin_coord and destination_coord:
            od["euclid_dist"] = round(haversine(origin_coord, destination_coord) * 1000)

    info = {
        "num_OD_pairs": len(od_pairs),
        "num_bike_stations": len(station_ids),
        "num_unique_origins": len(origins),
        "num_unique_destinations": len(destinations),
        "total_demand": total_demand,
    }

    delta_ia = compute_delta_ia(arcs_pt_bike, name_to_id)

    instance = {
        "generated_at": merged.get("generated_at"),
        "random_seed": seed,
        "info": info,
        "bike_stations": bike_station_info,
        "OD_pairs": od_pairs,
        "arcs_pt_bike": arcs_pt_bike,
        "arcs_pt_only": arcs_pt_only,
        "car_paths": car_paths,
        "delta_ia": delta_ia,
    }

    output_path = Path(output_dir) / f"Instance_{info['num_OD_pairs']}.json"
    write_json(output_path, instance)
    return output_path
