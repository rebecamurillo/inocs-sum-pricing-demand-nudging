# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from pathlib import Path

import pandas as pd

from ..utils.geo import haversine_m


def load_gtfs_pt_stations(gtfs_zip_path: Path, center_lat: float, center_lon: float, radius_m: float) -> list[dict]:
    import zipfile

    with zipfile.ZipFile(gtfs_zip_path) as archive:
        with archive.open("stops.txt") as stops_file:
            gtfs_stops = pd.read_csv(stops_file, usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])

    stations = []
    for _, row in gtfs_stops.iterrows():
        dist = haversine_m((center_lat, center_lon), (float(row["stop_lat"]), float(row["stop_lon"])))
        if dist <= radius_m:
            stations.append(
                {
                    "station_id": f"pts_{row['stop_id']}",
                    "type": "pt",
                    "name": row["stop_name"],
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"]),
                }
            )
    return stations


def load_gtfs_stop_lines(gtfs_zip_path: Path) -> pd.DataFrame:
    import zipfile

    with zipfile.ZipFile(gtfs_zip_path) as archive:
        with archive.open("stop_times.txt") as stop_times_file:
            stop_times = pd.read_csv(stop_times_file, usecols=["stop_id", "trip_id"])
        with archive.open("trips.txt") as trips_file:
            trips = pd.read_csv(trips_file, usecols=["route_id", "trip_id"])
        with archive.open("routes.txt") as routes_file:
            routes = pd.read_csv(routes_file, usecols=["route_id", "route_short_name"])

    stop_lines = (
        stop_times.merge(trips, on="trip_id")
        .merge(routes, on="route_id")
        .groupby("stop_id")["route_short_name"]
        .unique()
        .reset_index()
        .rename(columns={"route_short_name": "lines"})
    )
    return stop_lines
