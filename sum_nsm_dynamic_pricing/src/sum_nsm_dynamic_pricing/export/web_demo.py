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
    od_routes_dir = ensure_folder(web_demo_dir / "od_routes")

    write_json(web_demo_dir / "stations_hub.geojson", _build_stations_hub_geojson(output_dir))
    write_json(web_demo_dir / "hubs.geojson", read_json(hubs_path))

    od_routes_payload = read_json(routes_path)
    od_results = od_routes_payload.get("od_results", [])

    optimization_lookup, gamma_lookup = _load_optimization_lookup(output_dir)
    demand_lookup = _load_demand_lookup(output_dir)

    od_manifest = []

    for od_entry in od_results:
        if not isinstance(od_entry, dict):
            continue

        origin = od_entry.get("from_id")
        destination = od_entry.get("to_id")
        if not isinstance(origin, int) or not isinstance(destination, int):
            continue

        od_key = f"{origin}_{destination}"
        routes = []

        for route_type, route_field in [
            ("PT+Bike", "arc_pt_bike"),
            ("PT-Only", "arc_pt_only"),
            ("Car", "arc_car"),
        ]:
            for arc in od_entry.get(route_field, []):
                if not isinstance(arc, dict):
                    continue
                arc_id = str(arc.get("arc_id"))
                route_payload = dict(arc)
                route_payload["type"] = route_type
                route_payload["optimization"] = optimization_lookup.get((origin, destination, arc_id))
                routes.append(route_payload)

        od_payload: dict[str, Any] = {
            "origin_hub_id": origin,
            "destination_hub_id": destination,
            "od_key": od_key,
            "routes": routes,
        }

        if (origin, destination) in demand_lookup:
            od_payload["demand"] = demand_lookup[(origin, destination)]

        if (origin, destination) in gamma_lookup:
            od_payload["gamma"] = gamma_lookup[(origin, destination)]

        write_json(od_routes_dir / f"{od_key}.json", od_payload)
        od_manifest.append({"origin": origin, "destination": destination, "file": f"{od_key}.json"})

    write_json(
        od_routes_dir / "index.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "od_pairs": od_manifest,
        },
    )

    return web_demo_dir
