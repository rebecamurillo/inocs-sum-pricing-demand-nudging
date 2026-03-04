# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import count
from pathlib import Path

from ..config import PipelineConfig
from ..utils.io import read_json, write_json
from .od_permutations import extract_hubs, generate_od_pairs
from .otp_client import OTPClient

logger = logging.getLogger(__name__)


def _build_arc_entry(arc_id: str, legs: list[dict], include_bike_flags: bool) -> dict:
    total_travel = 0.0
    total_transfer = 0.0
    total_dist = 0.0
    bike_indices = []
    pt_indices = []
    leg_entries = []

    for index, leg in enumerate(legs):
        mode = leg["mode"].upper()
        duration = leg.get("duration", 0.0)
        distance = leg.get("distance", 0.0)
        if mode == "FOOT":
            total_transfer += duration
        else:
            total_travel += duration
        total_dist += distance
        if "BICYCLE" in mode:
            bike_indices.append(index)
        if mode in ("BUS", "TRAM"):
            pt_indices.append(index)

        leg_entries.append(
            {
                "leg_idx": index,
                "mode": mode,
                "duration_s": duration,
                "distance_m": distance,
                "line_publicCode": leg.get("line", {}),
                "to_place": leg.get("toPlace", {}).get("name", ""),
                "to_lat": leg.get("toPlace", {}).get("lat"),
                "to_lon": leg.get("toPlace", {}).get("lon"),
                "from_place": leg.get("fromPlace", {}).get("name", ""),
                "from_lat": leg.get("fromPlace", {}).get("lat"),
                "from_lon": leg.get("fromPlace", {}).get("lon"),
                "rented_bike": leg.get("rentedBike", False),
            }
        )

    arc = {
        "arc_id": arc_id,
        "total_travel_time_s": total_travel,
        "total_transfer_time_s": total_transfer,
        "total_distance_m": total_dist,
        "legs": leg_entries,
    }

    if include_bike_flags:
        if bike_indices and pt_indices:
            access_bike = min(bike_indices) < min(pt_indices)
            egress_bike = max(bike_indices) > max(pt_indices)
        else:
            access_bike = bool(bike_indices)
            egress_bike = bool(bike_indices)
        arc["access_bike"] = access_bike
        arc["egress_bike"] = egress_bike

    return arc


def _classify_patterns(patterns: list[dict], arc_counter) -> tuple[list[dict], list[dict], list[dict]]:
    arc_pt_bike = []
    arc_pt_only = []
    arc_bike_only = []

    for pattern in patterns:
        arc_id = str(next(arc_counter))
        legs = pattern.get("legs", [])
        modes = {leg.get("mode", "").upper() for leg in legs}
        bike = "BICYCLE" in modes
        pt = bool(modes.intersection({"BUS", "TRAM", "RAIL", "SUBWAY", "FERRY", "TRANSIT"}))

        if bike and pt:
            arc_pt_bike.append(_build_arc_entry(arc_id, legs, include_bike_flags=True))
        elif pt:
            arc_pt_only.append(_build_arc_entry(arc_id, legs, include_bike_flags=False))
        else:
            arc_bike_only.append(_build_arc_entry(arc_id, legs, include_bike_flags=False))

    return arc_pt_bike, arc_pt_only, arc_bike_only


def _extract_car_arcs(patterns: list[dict], arc_counter) -> list[dict]:
    car_arcs = []
    for pattern in patterns:
        legs = pattern.get("legs", [])
        modes = {leg.get("mode", "").upper() for leg in legs}
        if "CAR" in modes:
            arc_id = str(next(arc_counter))
            car_arcs.append(_build_arc_entry(arc_id, legs, include_bike_flags=False))
    return car_arcs


def _query_one_pair(client: OTPClient, origin: dict, destination: dict, date_time: str, otp_params: dict, arc_counter, cache: dict) -> dict | None:
    key = f"{origin['hub_id']}|{destination['hub_id']}"
    if key in cache:
        logger.debug("Cache hit for pair %s", key)
        return cache[key]

    logger.debug(
        "OTP query context [%s -> %s]: date_time=%s params=%s",
        key.split("|")[0],
        key.split("|")[1],
        date_time,
        json.dumps(otp_params),
    )

    try:
        patterns = client.query_trip(origin, destination, date_time, otp_params)
    except Exception as exc:
        logger.warning("OTP query failed for pair %s: %s", key, exc)
        return None

    logger.debug(
        "OTP response [%s -> %s] patterns (%d): %s",
        key.split("|")[0],
        key.split("|")[1],
        len(patterns),
        json.dumps(patterns),
    )

    if not patterns:
        logger.debug("No patterns returned for pair %s", key)
        return None

    pt_bike, pt_only, bike_only = _classify_patterns(patterns, arc_counter)
    logger.debug(
        "OTP classification [%s -> %s]: pt_bike=%d, pt_only=%d, bike_only=%d",
        key.split("|")[0],
        key.split("|")[1],
        len(pt_bike),
        len(pt_only),
        len(bike_only),
    )
    if not pt_bike and not pt_only and not bike_only:
        logger.warning("All %d pattern(s) for pair %s were unclassified (no PT/bike/car modes found)", len(patterns), key)
    result = {
        "from_id": origin["hub_id"],
        "to_id": destination["hub_id"],
        "arc_pt_bike": pt_bike,
        "arc_pt_only": pt_only,
        "arc_car": [],
    }
    cache[key] = result
    return result


def build_od_routes(config: PipelineConfig, hubs_geojson_path: Path) -> Path:
    client = OTPClient(config.otp_url)
    client.ensure_available()

    hubs = extract_hubs(Path(hubs_geojson_path))
    od_pairs = generate_od_pairs(hubs, config.min_od_distance_m)

    output_dir = Path(config.output_dir)
    cache_path = output_dir / "od_cache.json"
    routes_path = output_dir / "od_routes.json"

    cache = read_json(cache_path) if cache_path.exists() else {}
    results = []
    arc_counter = count()

    from ..utils.constants import DEFAULT_CAR_OTP_PARAMS, DEFAULT_OTP_PARAMS

    fixed_timestamp = datetime.utcnow().isoformat() + "Z"

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(
                _query_one_pair,
                client,
                origin,
                destination,
                fixed_timestamp,
                DEFAULT_OTP_PARAMS,
                arc_counter,
                cache,
            )
            for origin, destination in od_pairs
        ]
        for future in as_completed(futures):
            response = future.result()
            if response:
                results.append(response)

    hubs_by_id = {str(hub["hub_id"]): hub for hub in hubs}
    results_by_key = {f"{od['from_id']}|{od['to_id']}": od for od in results}

    def query_car_for_pair(origin: dict, destination: dict) -> tuple[str, list[dict]]:
        key = f"{origin['hub_id']}|{destination['hub_id']}"
        try:
            patterns = client.query_car_trip(origin, destination, fixed_timestamp, DEFAULT_CAR_OTP_PARAMS)
        except Exception as exc:
            logger.warning("OTP CAR query failed for pair %s: %s", key, exc)
            return key, []

        car_arcs = _extract_car_arcs(patterns, arc_counter)
        logger.debug(
            "OTP CAR classification [%s -> %s]: car=%d",
            origin["hub_id"],
            destination["hub_id"],
            len(car_arcs),
        )
        return key, car_arcs

    car_pairs = []
    for key in results_by_key:
        origin_id, destination_id = key.split("|")
        origin = hubs_by_id.get(origin_id)
        destination = hubs_by_id.get(destination_id)
        if origin and destination:
            car_pairs.append((origin, destination))

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(query_car_for_pair, origin, destination) for origin, destination in car_pairs]
        for future in as_completed(futures):
            key, car_arcs = future.result()
            if key in results_by_key:
                results_by_key[key]["arc_car"] = car_arcs
            if key in cache:
                cache[key]["arc_car"] = car_arcs

    logger.info(
        "Route building complete: %d/%d OD pairs returned results. Output: %s",
        len(results),
        len(od_pairs),
        routes_path,
    )
    if len(results) == 0:
        logger.warning("No OD routes were generated. Check OTP connectivity and query parameters.")
    write_json(cache_path, cache)
    write_json(routes_path, {"generated_at": fixed_timestamp, "od_results": results})
    return routes_path
