# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from itertools import count
from pathlib import Path

from ..config import PipelineConfig
from ..utils.io import read_json, write_json
from .od_permutations import extract_hubs, generate_od_pairs
from .otp_client import OTPClient

logger = logging.getLogger(__name__)


def _decode_polyline(encoded: str) -> list[list[float]]:
    """Decode a Google Encoded Polyline string to [[lat, lon], ...] pairs."""
    coords: list[list[float]] = []
    index = 0
    length = len(encoded)
    lat = lon = 0
    while index < length:
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = -(result >> 1) if result & 1 else result >> 1
            if not is_lon:
                lat += delta
            else:
                lon += delta
        coords.append([lat / 1e5, lon / 1e5])
    return coords


def _build_arc_entry(arc_id: str, legs: list[dict], include_bike_flags: bool) -> tuple[dict, dict]:
    total_travel = 0.0
    total_transfer = 0.0
    total_dist = 0.0
    bike_indices = []
    pt_indices = []
    leg_entries = []
    legs_geometry = []

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

        encoded = leg.get("legGeometry")
        legs_geometry.append({
            "leg_idx": index,
            "geometry": _decode_polyline(encoded) if encoded else None,
        })

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

    geometry_record = {"arc_id": arc_id, "legs_geometry": legs_geometry}
    return arc, geometry_record


def _classify_patterns(patterns: list[dict], arc_counter) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    arc_pt_bike = []
    arc_pt_only = []
    arc_bike_only = []
    geometry_records = []

    for pattern in patterns:
        arc_id = str(next(arc_counter))
        legs = pattern.get("legs", [])
        modes = {leg.get("mode", "").upper() for leg in legs}
        bike = "BICYCLE" in modes
        pt = bool(modes.intersection(
            {"BUS", "TRAM", "RAIL", "SUBWAY", "FERRY", "TRANSIT"}))

        if bike and pt:
            arc, geo = _build_arc_entry(arc_id, legs, include_bike_flags=True)
            arc_pt_bike.append(arc)
        elif pt:
            arc, geo = _build_arc_entry(arc_id, legs, include_bike_flags=False)
            arc_pt_only.append(arc)
        else:
            arc, geo = _build_arc_entry(arc_id, legs, include_bike_flags=False)
            arc_bike_only.append(arc)
        geometry_records.append(geo)

    return arc_pt_bike, arc_pt_only, arc_bike_only, geometry_records


def _extract_car_arcs(patterns: list[dict], arc_counter) -> tuple[list[dict], list[dict]]:
    car_arcs = []
    geometry_records = []
    for pattern in patterns:
        legs = pattern.get("legs", [])
        modes = {leg.get("mode", "").upper() for leg in legs}
        if "CAR" in modes:
            arc_id = str(next(arc_counter))
            arc, geo = _build_arc_entry(f"car_{arc_id}", legs, include_bike_flags=False)
            car_arcs.append(arc)
            geometry_records.append(geo)
    return car_arcs, geometry_records


def _query_one_pair(
    client: OTPClient,
    origin: dict,
    destination: dict,
    date_time: str,
    otp_params: dict,
    car_otp_params: dict,
    arc_counter,
    cache: dict,
    cache_lock: threading.Lock,
    request_delay_s: float,
    geometry_store: dict,
    geometry_lock: threading.Lock,
) -> dict | None:
    """Query PT+Bike and Car routes for a single OD pair in one shot.

    Combining both query types into one worker eliminates the second full
    ThreadPool pass and keeps OTP load steady.
    """
    key = f"{origin['hub_id']}|{destination['hub_id']}"

    with cache_lock:
        if key in cache:
            logger.debug("Cache hit for pair %s", key)
            return cache[key]

    if request_delay_s > 0:
        time.sleep(request_delay_s)

    logger.debug("OTP query [%s]: date_time=%s", key, date_time)

    # --- PT + Bike ---
    try:
        patterns = client.query_trip(
            origin, destination, date_time, otp_params)
    except Exception as exc:
        logger.warning("OTP PT query failed for pair %s: %s", key, exc)
        return None

    if not patterns:
        logger.debug("No PT patterns returned for pair %s", key)
        return None

    pt_bike, pt_only, bike_only, pt_geometry = _classify_patterns(patterns, arc_counter)

    if not pt_bike and not pt_only and not bike_only:
        logger.warning(
            "All %d pattern(s) for pair %s were unclassified (no PT/bike modes)",
            len(patterns),
            key,
        )
        return None

    result: dict = {
        "from_id": origin["hub_id"],
        "to_id": destination["hub_id"],
        "arc_pt_bike": pt_bike,
        "arc_pt_only": pt_only,
        "arc_car": [],
    }

    all_geometry = list(pt_geometry)

    # --- Car (queried immediately after PT, same thread) ---
    if request_delay_s > 0:
        time.sleep(request_delay_s)
    try:
        car_patterns = client.query_car_trip(
            origin, destination, date_time, car_otp_params)
        car_arcs, car_geometry = _extract_car_arcs(car_patterns, arc_counter)
        result["arc_car"] = car_arcs
        all_geometry.extend(car_geometry)
        logger.debug("OTP CAR [%s]: car=%d", key, len(car_arcs))
    except Exception as exc:
        logger.warning("OTP CAR query failed for pair %s: %s", key, exc)

    with geometry_lock:
        for rec in all_geometry:
            geometry_store[rec["arc_id"]] = rec["legs_geometry"]

    with cache_lock:
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
    geometry_path = output_dir / "od_geometry.json"

    cache: dict = read_json(cache_path) if cache_path.exists() else {}
    cache_lock = threading.Lock()
    arc_counter = count()

    # Load any previously computed geometry so resumed runs keep existing entries.
    geometry_store: dict = {}
    if geometry_path.exists():
        existing_geo = read_json(geometry_path)
        geometry_store = existing_geo.get("arcs_geometry", {})
    geometry_lock = threading.Lock()

    from ..utils.constants import DEFAULT_CAR_OTP_PARAMS, DEFAULT_OTP_PARAMS

    fixed_timestamp = config.otp_timestamp

    # Skip pairs that are already fully resolved in the cache.
    pending_pairs = [
        (o, d) for o, d in od_pairs
        if f"{o['hub_id']}|{d['hub_id']}" not in cache
    ]
    already_cached = len(od_pairs) - len(pending_pairs)
    total = len(od_pairs)

    logger.info(
        "Route building: %d total OD pairs | %d already cached | %d to query "
        "(workers=%d, delay=%.2fs)",
        total,
        already_cached,
        len(pending_pairs),
        config.otp_workers,
        config.otp_request_delay_s,
    )

    # Counters shared across threads (GIL-safe for += on int via list trick).
    completed = [0]
    log_interval = max(1, len(pending_pairs) // 20)  # log every ~5%
    cache_save_interval = 50  # persist cache every 50 completions

    def _on_complete(result: dict | None) -> None:
        completed[0] += 1
        n = completed[0]
        if result:
            pass  # already written to cache inside _query_one_pair
        if n % log_interval == 0 or n == len(pending_pairs):
            pct = 100.0 * (already_cached + n) / total if total else 0
            logger.info(
                "Route progress: %d/%d pending done (%.0f%% overall)", n, len(pending_pairs), pct)
        if n % cache_save_interval == 0:
            with cache_lock:
                snapshot = dict(cache)
            write_json(cache_path, snapshot)
            logger.debug(
                "Cache saved incrementally (%d entries)", len(snapshot))

    results: list[dict] = list(cache.values())

    with ThreadPoolExecutor(max_workers=config.otp_workers) as executor:
        futures = [
            executor.submit(
                _query_one_pair,
                client,
                origin,
                destination,
                fixed_timestamp,
                DEFAULT_OTP_PARAMS,
                DEFAULT_CAR_OTP_PARAMS,
                arc_counter,
                cache,
                cache_lock,
                config.otp_request_delay_s,
                geometry_store,
                geometry_lock,
            )
            for origin, destination in pending_pairs
        ]
        for future in as_completed(futures):
            response = future.result()
            if response:
                results.append(response)
            _on_complete(response)

    # Final cache + routes flush.
    with cache_lock:
        write_json(cache_path, cache)

    logger.info(
        "Route building complete: %d/%d OD pairs have results. Output: %s",
        len(results),
        total,
        routes_path,
    )
    if len(results) == 0:
        logger.warning(
            "No OD routes were generated. Check OTP connectivity and query parameters.")
    write_json(routes_path, {
               "generated_at": fixed_timestamp, "od_results": results})
    write_json(geometry_path, {
               "generated_at": fixed_timestamp, "arcs_geometry": geometry_store})
    return routes_path
