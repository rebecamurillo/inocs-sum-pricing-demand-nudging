# Source: pricing_demand_nudging/clustering/strategy.py
from abc import ABC, abstractmethod

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union


class ClusteringStrategy(ABC):
    def __init__(self, bike_gdf: gpd.GeoDataFrame, pt_gdf: gpd.GeoDataFrame, threshold: float, buffer: float):
        self.bike_gdf = bike_gdf.to_crs("EPSG:3857")
        self.pt_gdf = pt_gdf.to_crs("EPSG:3857")
        self.threshold = threshold
        self.buffer = buffer
        self.data = self._combine()

    def _combine(self) -> pd.DataFrame:
        bike_df = self.bike_gdf.copy()
        bike_df["station_type"] = "bike"
        bike_df["Line"] = None

        pt_df = self.pt_gdf.copy()
        pt_df["station_type"] = "pt"

        return pd.concat(
            [
                bike_df[["identifier", "station_type", "geometry", "Line"]],
                pt_df[["identifier", "station_type", "geometry", "Line"]],
            ],
            ignore_index=True,
        )

    @abstractmethod
    def _cluster(self, coords: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def run(self) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
        coords = np.vstack(self.data.geometry.apply(lambda geom: (geom.x, geom.y)).to_numpy())
        self.data["cluster"] = self._cluster(coords)
        return self._aggregate()

    def _aggregate(self) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
        stops_df = self.data[["identifier", "station_type", "geometry", "cluster"]].rename(columns={"cluster": "hub_id"})
        stops_4326 = gpd.GeoDataFrame(stops_df, geometry="geometry", crs="EPSG:3857").to_crs("EPSG:4326")

        cluster_polys = (
            self.data.groupby("cluster")["geometry"]
            .apply(lambda geom: unary_union(geom.buffer(self.buffer)))
            .reset_index()
        )
        polys_4326 = gpd.GeoDataFrame(cluster_polys, geometry="geometry", crs="EPSG:3857").to_crs("EPSG:4326")

        hubs = []
        for cluster_id, group in self.data.groupby("cluster"):
            bike_list = group.loc[group["station_type"] == "bike", "identifier"].tolist()
            pt_list = group.loc[group["station_type"] == "pt", "identifier"].tolist()
            pt_lines = group.loc[group["station_type"] == "pt", "Line"].explode().dropna().unique().tolist()

            if bike_list and not pt_list:
                label = "bike station"
            elif pt_list and not bike_list:
                label = "pt station"
            elif bike_list and pt_list:
                label = "pt+bike station"
            else:
                label = "unknown"

            centroid = unary_union(group.geometry).centroid
            hubs.append(
                {
                    "hub_id": int(cluster_id),
                    "bike_stations": bike_list,
                    "pt_stations": pt_list,
                    "lines": pt_lines,
                    "label": label,
                    "geometry": centroid,
                }
            )

        hubs_4326 = gpd.GeoDataFrame(hubs, geometry="geometry", crs="EPSG:3857").to_crs("EPSG:4326")
        return hubs_4326, stops_4326, polys_4326
