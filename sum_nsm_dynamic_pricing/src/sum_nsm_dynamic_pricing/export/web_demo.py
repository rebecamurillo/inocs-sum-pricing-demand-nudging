from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils.io import ensure_folder, read_json, write_json


def _parse_od_label(od_label: Any) -> tuple[int, int] | None:
    if not isinstance(od_label, str) or "->" not in od_label:
        return None

    left, right = od_label.split("->", 1)
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None


def _load_optimization_lookup(output_dir: Path) -> tuple[dict[tuple[int, int, str], dict[str, Any]], dict[tuple[int, int], Any]]:
    optimization_path = output_dir / "optimization_instance_results.json"
    if not optimization_path.exists():
        return {}, {}

    payload = read_json(optimization_path)
    rows = payload.get("instances", [])
    if not isinstance(rows, list):
        return {}, {}

    arc_lookup: dict[tuple[int, int, str], dict[str, Any]] = {}
    gamma_lookup: dict[tuple[int, int], Any] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        od_pair = _parse_od_label(row.get("OD") or row.get("Instance OD"))
        if od_pair is None:
            continue

        if "Arc ID" not in row:
            if "gamma" in row:
                gamma_lookup[od_pair] = row["gamma"]
            continue

        arc_id = str(row["Arc ID"])
        details = {
            key: value
            for key, value in row.items()
            if key not in {"OD", "Instance OD", "Arc ID"}
        }
        arc_lookup[(od_pair[0], od_pair[1], arc_id)] = details

    return arc_lookup, gamma_lookup


def _load_demand_lookup(output_dir: Path) -> dict[tuple[int, int], Any]:
    instance_candidates = [
        path
        for path in output_dir.glob("Instance_*.json")
        if not path.name.endswith("_solution.json")
    ]
    if not instance_candidates:
        return {}

    latest_instance_path = max(instance_candidates, key=lambda path: path.stat().st_mtime)
    instance_payload = read_json(latest_instance_path)
    od_pairs = instance_payload.get("OD_pairs", [])
    if not isinstance(od_pairs, list):
        return {}

    demand_lookup: dict[tuple[int, int], Any] = {}
    for od in od_pairs:
        if not isinstance(od, dict):
            continue
        origin = od.get("origin")
        destination = od.get("destination")
        if isinstance(origin, int) and isinstance(destination, int):
            demand_lookup[(origin, destination)] = od.get("demand")

    return demand_lookup


def _build_stations_hub_geojson(output_dir: Path) -> dict[str, Any]:
    stations_payload = read_json(output_dir / "stations.json")
    stations_hub_payload = read_json(output_dir / "stations_hubs.geojson")

    station_name_lookup = {
        station.get("station_id"): station.get("name", "")
        for station in stations_payload.get("stations", [])
        if isinstance(station, dict) and station.get("station_id")
    }

    features = []
    for feature in stations_hub_payload.get("features", []):
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties", {})
        station_id = properties.get("identifier")
        if not station_id:
            continue

        features.append(
            {
                "type": "Feature",
                "properties": {
                    "station_id": station_id,
                    "station_type": properties.get("station_type"),
                    "name": station_name_lookup.get(station_id, ""),
                    "hub_id": properties.get("hub_id"),
                },
                "geometry": feature.get("geometry"),
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _load_geometry_lookup(output_dir: Path) -> dict[str, list]:
    """Return arc_id -> legs_geometry list from od_geometry.json, or {} if absent."""
    geometry_path = output_dir / "od_geometry.json"
    if not geometry_path.exists():
        return {}
    return read_json(geometry_path).get("arcs_geometry", {})


def export_web_demo(output_dir: Path) -> Path:
    output_dir = Path(output_dir)

    stations_path = output_dir / "stations.json"
    hubs_path = output_dir / "hubs.geojson"
    stations_hub_path = output_dir / "stations_hubs.geojson"
    routes_path = output_dir / "od_routes.json"

    for required_path in [stations_path, hubs_path, stations_hub_path, routes_path]:
        if not required_path.exists():
            raise FileNotFoundError(f"Missing required input file: {required_path}")

    web_demo_dir = ensure_folder(output_dir / "web_demo")
    cluster_arcs_dir = ensure_folder(web_demo_dir / "cluster_arcs")

    write_json(web_demo_dir / "stations_hub.geojson", _build_stations_hub_geojson(output_dir))
    write_json(web_demo_dir / "hubs.geojson", read_json(hubs_path))

    od_routes_payload = read_json(routes_path)
    od_results = od_routes_payload.get("od_results", [])

    optimization_lookup, gamma_lookup = _load_optimization_lookup(output_dir)
    demand_lookup = _load_demand_lookup(output_dir)
    geometry_lookup = _load_geometry_lookup(output_dir)

    od_manifest = []

    for od_entry in od_results:
        if not isinstance(od_entry, dict):
            continue

        origin = od_entry.get("from_id")
        destination = od_entry.get("to_id")
        if not isinstance(origin, int) or not isinstance(destination, int):
            continue

        routes_summary = []
        arc_detail_files: list[tuple[str, dict]] = []

        for route_type, route_field in [
            ("PT+Bike", "arc_pt_bike"),
            ("PT-Only", "arc_pt_only"),
            ("Car", "arc_car"),
        ]:
            for arc in od_entry.get(route_field, []):
                if not isinstance(arc, dict):
                    continue
                arc_id = str(arc.get("arc_id"))

                # --- Summary entry (no geometry) ---
                summary_arc: dict[str, Any] = {
                    "arc_id": arc_id,
                    "type": route_type,
                    "total_travel_time_s": arc.get("total_travel_time_s"),
                    "total_transfer_time_s": arc.get("total_transfer_time_s"),
                    "total_distance_m": arc.get("total_distance_m"),
                    "legs": arc.get("legs", []),
                    "optimization": optimization_lookup.get((origin, destination, arc_id)),
                }
                if "access_bike" in arc:
                    summary_arc["access_bike"] = arc["access_bike"]
                if "egress_bike" in arc:
                    summary_arc["egress_bike"] = arc["egress_bike"]
                routes_summary.append(summary_arc)

                # --- Detail entry (with geometry per leg) ---
                leg_geo_by_idx: dict[int, Any] = {
                    entry["leg_idx"]: entry.get("geometry")
                    for entry in geometry_lookup.get(arc_id, [])
                }
                detail_legs = [
                    {
                        "leg_idx": leg.get("leg_idx"),
                        "mode": leg.get("mode"),
                        "duration_s": leg.get("duration_s"),
                        "distance_m": leg.get("distance_m"),
                        "from_place": leg.get("from_place"),
                        "to_place": leg.get("to_place"),
                        "line_publicCode": leg.get("line_publicCode"),
                        "rented_bike": leg.get("rented_bike"),
                        "geometry": leg_geo_by_idx.get(leg.get("leg_idx")),
                    }
                    for leg in arc.get("legs", [])
                ]
                detail_payload: dict[str, Any] = {
                    "arc_id": arc_id,
                    "type": route_type,
                    "origin_hub_id": origin,
                    "destination_hub_id": destination,
                    "total_travel_time_s": arc.get("total_travel_time_s"),
                    "total_transfer_time_s": arc.get("total_transfer_time_s"),
                    "total_distance_m": arc.get("total_distance_m"),
                    "legs": detail_legs,
                }
                arc_detail_files.append((arc_id, detail_payload))

        # Sort: routes with optimization Flow (q) > 0 first, then by total travel time ascending.
        def _route_sort_key(r: dict) -> tuple[int, float]:
            opt = r.get("optimization") or {}
            has_flow = int((opt.get("Flow (q)") or 0) <= 0)
            return (has_flow, r.get("total_travel_time_s") or 0.0)

        routes_summary.sort(key=_route_sort_key)

        # Write routes.json (summary list, no geometry)
        routes_payload: dict[str, Any] = {
            "origin_hub_id": origin,
            "destination_hub_id": destination,
            "routes": routes_summary,
        }
        if (origin, destination) in demand_lookup:
            routes_payload["demand"] = demand_lookup[(origin, destination)]
        if (origin, destination) in gamma_lookup:
            routes_payload["gamma"] = gamma_lookup[(origin, destination)]

        od_dir = cluster_arcs_dir / str(origin) / str(destination)
        write_json(od_dir / "routes.json", routes_payload)

        # Write one {arc_id}.json per arc (detail with geometry)
        for arc_id, detail_payload in arc_detail_files:
            write_json(od_dir / "arcs" / f"{arc_id}.json", detail_payload)

        od_manifest.append({
            "origin": origin,
            "destination": destination,
            "path": f"{origin}/{destination}",
        })

    write_json(
        cluster_arcs_dir / "index.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "od_pairs": od_manifest,
        },
    )

    return web_demo_dir
