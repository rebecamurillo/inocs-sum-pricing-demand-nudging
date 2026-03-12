from __future__ import annotations

import logging
from pathlib import Path

from .utils.io import read_json, write_json

logger = logging.getLogger(__name__)


def validate_od_routes(routes_path: Path) -> bool:
    payload = read_json(Path(routes_path))
    od_results = payload.get("od_results", [])

    has_errors = False
    seen_arc_ids: dict[str, tuple[str, str]] = {}

    for od in od_results:
        origin = od.get("from_id")
        destination = od.get("to_id")
        od_key = f"{origin}|{destination}"

        pt_bike_arcs = od.get("arc_pt_bike", [])
        pt_only_arcs = od.get("arc_pt_only", [])
        car_arcs = od.get("arc_car", [])

        if len(pt_bike_arcs) + len(pt_only_arcs) == 0:
            has_errors = True
            logger.error(
                "OD %s has no PT/Bike options (arc_pt_bike + arc_pt_only are empty)", od_key)

        if len(car_arcs) == 0:
            has_errors = True
            logger.error("OD %s has no car options (arc_car is empty)", od_key)

        for arc_field in ("arc_pt_bike", "arc_pt_only", "arc_car"):
            for arc in od.get(arc_field, []):
                arc_id = arc.get("arc_id")
                if not arc_id:
                    has_errors = True
                    logger.error(
                        "OD %s contains an arc without arc_id in %s", od_key, arc_field)
                    continue

                if arc_id in seen_arc_ids:
                    has_errors = True
                    prev_od_key, prev_field = seen_arc_ids[arc_id]
                    logger.error(
                        "Duplicate arc_id '%s' found in %s (%s) and %s (%s)",
                        arc_id,
                        prev_od_key,
                        prev_field,
                        od_key,
                        arc_field,
                    )
                else:
                    seen_arc_ids[arc_id] = (od_key, arc_field)

    if has_errors:
        logger.error("Route quality validation failed for %s", routes_path)
    else:
        logger.info("Route quality validation passed for %s (%d OD pairs)",
                    routes_path, len(od_results))
    return not has_errors


def clean_incomplete_od_pairs(routes_path: Path) -> bool:
    logger.info("Starting OD cleanup for %s", routes_path)
    payload = read_json(Path(routes_path))
    od_results = payload.get("od_results", [])

    total_od_pairs = len(od_results)
    if total_od_pairs == 0:
        logger.info("OD cleanup skipped: no OD pairs found in %s", routes_path)
        return False

    cleaned_od_results = []
    removed_count = 0

    for od in od_results:
        has_pt_or_bike = bool(od.get("arc_pt_bike", [])
                              or od.get("arc_pt_only", []))
        has_car = bool(od.get("arc_car", []))
        if has_pt_or_bike and has_car:
            cleaned_od_results.append(od)
        else:
            removed_count += 1

    if removed_count == 0:
        logger.info(
            "OD cleanup found no incomplete OD pairs in %s", routes_path)
        return False

    payload["od_results"] = cleaned_od_results
    write_json(Path(routes_path), payload)

    invalid_pct = (removed_count / total_od_pairs) * 100.0
    logger.info(
        "OD cleanup removed %d/%d OD pairs (%.2f%% invalid) from %s",
        removed_count,
        total_od_pairs,
        invalid_pct,
        routes_path,
    )
    return True


def validate_instance(instance_path: Path) -> bool:
    payload = read_json(Path(instance_path))
    arcs_pt_bike = payload.get("arcs_pt_bike", {})
    delta_ia = payload.get("delta_ia", {})

    has_errors = False

    for od_key, arcs in arcs_pt_bike.items():
        for arc in arcs:
            arc_id = arc.get("arc_id")
            if not arc_id:
                has_errors = True
                logger.error(
                    "OD %s contains a PT+Bike arc without arc_id", od_key)
                continue

            if arc_id not in delta_ia:
                has_errors = True
                logger.error(
                    "OD %s PT+Bike arc '%s' has no delta entry in delta_ia", od_key, arc_id)

    for arc_id, station_deltas in delta_ia.items():
        total = 0.0
        for value in station_deltas.values():
            if isinstance(value, (int, float)):
                total += value

        if abs(total) > 1e-9:
            has_errors = True
            logger.error(
                "delta_ia for arc '%s' is unbalanced (sum=%s, expected 0)", arc_id, total)

    if has_errors:
        logger.error(
            "Instance quality validation failed for %s", instance_path)
    else:
        logger.info("Instance quality validation passed for %s", instance_path)
    return not has_errors
