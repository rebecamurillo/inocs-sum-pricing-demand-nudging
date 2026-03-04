# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from pathlib import Path

from ..utils.geo import haversine_m
from ..utils.io import read_json


def load_gbfs_bike_stations(gbfs_station_information_path: Path, center_lat: float, center_lon: float, radius_m: float) -> list[dict]:
    station_info = read_json(gbfs_station_information_path)
    raw_bike = station_info.get("data", {}).get("stations", [])
    stations = []
    for station in raw_bike:
        lat = float(station.get("lat"))
        lon = float(station.get("lon"))
        dist = haversine_m((center_lat, center_lon), (lat, lon))
        if dist <= radius_m:
            stations.append(
                {
                    "station_id": f"bs_{station['station_id']}",
                    "type": "bs",
                    "name": station.get("name"),
                    "lat": lat,
                    "lon": lon,
                }
            )
    return stations
