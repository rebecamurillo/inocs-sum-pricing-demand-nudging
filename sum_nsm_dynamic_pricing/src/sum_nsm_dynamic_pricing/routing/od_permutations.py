# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from itertools import permutations
from pathlib import Path

from ..utils.geo import haversine_m
from ..utils.io import read_json


def extract_hubs(hubs_geojson_path: Path) -> list[dict]:
    hubs_geojson = read_json(Path(hubs_geojson_path))
    hubs = []
    for feature in hubs_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        lon, lat = geometry["coordinates"]
        properties = feature.get("properties", {})
        hubs.append({
            "hub_id": properties["hub_id"],
            "lat": lat,
            "lon": lon,
            "label": properties.get("label"),
            "bike_stations": properties.get("bike_stations", []),
            "pt_stations": properties.get("pt_stations", []),
            "lines": properties.get("lines", []),
        })
    return hubs


def generate_od_pairs(hubs: list[dict], min_distance_m: float) -> list[tuple[dict, dict]]:
    return [
        (origin, destination)
        for origin, destination in permutations(hubs, 2)
        if haversine_m((origin["lat"], origin["lon"]), (destination["lat"], destination["lon"])) >= min_distance_m
    ]
