# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from ..config import PipelineConfig
from ..stations.gtfs import load_gtfs_stop_lines
from ..utils.io import read_json
from .agglomerative import AgglomClustering


def _safe_for_geojson(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    for col in ["bike_stations", "pt_stations", "lines"]:
        if col in out.columns:
            out[col] = out[col].apply(lambda value: value if isinstance(value, list) else [])
    return out


def build_hubs(stations_json_path: Path, config: PipelineConfig) -> tuple[Path, Path, Path]:
    stations_payload = read_json(Path(stations_json_path))
    stations = pd.DataFrame(stations_payload["stations"])

    pt_df = stations[stations["type"] == "pt"].copy()
    bs_df = stations[stations["type"] == "bs"].copy()

    stop_lines = load_gtfs_stop_lines(Path(config.gtfs_path))
    pt_df["stop_id"] = pt_df["station_id"].str.replace("pts_", "", regex=False)
    pt_df = pt_df.merge(stop_lines, on="stop_id", how="left")
    pt_df["lines"] = pt_df["lines"].apply(lambda x: x.tolist() if isinstance(x, np.ndarray) else ([] if pd.isna(x) else [x]))

    bike_gdf = gpd.GeoDataFrame(
        bs_df.assign(identifier=bs_df["station_id"], Line=None),
        geometry=[Point(xy) for xy in zip(bs_df.lon, bs_df.lat)],
        crs="EPSG:4326",
    )
    pt_gdf = gpd.GeoDataFrame(
        pt_df.assign(identifier=pt_df["station_id"], Stop=pt_df["station_id"], Line=pt_df["lines"]),
        geometry=[Point(xy) for xy in zip(pt_df.lon, pt_df.lat)],
        crs="EPSG:4326",
    )

    clustering = AgglomClustering(
        bike_gdf=bike_gdf,
        pt_gdf=pt_gdf,
        threshold=config.clustering_threshold_m,
        buffer=config.clustering_buffer_m,
    )
    hubs_gdf, stations_hubs_gdf, hub_polygons_gdf = clustering.run()

    output_dir = Path(config.output_dir)
    hubs_path = output_dir / "hubs.geojson"
    stations_hubs_path = output_dir / "stations_hubs.geojson"
    hub_polygons_path = output_dir / "hub_polygons.geojson"

    _safe_for_geojson(hubs_gdf).to_file(hubs_path, driver="GeoJSON", index=False)
    stations_hubs_gdf.to_file(stations_hubs_path, driver="GeoJSON", index=False)
    hub_polygons_gdf.to_file(hub_polygons_path, driver="GeoJSON", index=False)

    return hubs_path, stations_hubs_path, hub_polygons_path
