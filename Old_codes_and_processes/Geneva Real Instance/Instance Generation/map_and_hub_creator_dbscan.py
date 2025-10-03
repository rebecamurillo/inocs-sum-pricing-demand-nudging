import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from sklearn.cluster import DBSCAN
from shapely.ops import unary_union
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance   import pdist
import numpy as np
from sklearn.cluster import AgglomerativeClustering
def flow_to_weight(flow, alpha=1.0):
    """
    Convert a non‑negative flow value into a DBSCAN weight.
    Larger flow  →  smaller weight  (≤ 1).

    w_i = 1 / (1 + flow_i)^alpha
    """
    return 1.0 / (1.0 + flow)**alpha

def clusters_to_polygons(combined, eps_buffer=150):
    """
    Return a GeoDataFrame with one polygon per DBSCAN cluster.
    `combined` is the metric‑CRS GeoDataFrame that already has a `cluster` column.
    """
    polys = []
    for label, grp in combined.groupby("cluster"):
        # union of r‑metre buffers, then take its convex hull to reduce complexity
        geom = unary_union(grp.geometry.buffer(eps_buffer))
        polys.append({"cluster": label, "geometry": geom})
    return gpd.GeoDataFrame(polys, crs=combined.crs)

import random
import matplotlib.colors as mcolors

def cluster_palette(labels):
    """
    Map each cluster label to a distinct HEX colour.
    Noise (‑1) → grey.
    Works for an arbitrary number of clusters.
    """
    uniq   = sorted(set(labels))
    n      = len(uniq)

    # Use a continuous colormap and sample n evenly‑spaced colours.
    cmap   = cm.get_cmap("gist_ncar", n)       # perceptually distinct gamut
    colors = [mcolors.to_hex(cmap(i)) for i in range(n)]

    palette = dict(zip(uniq, colors))
    palette[-1] = "#808080"                    # noise
    return palette


def create_hub_map_and_dataframe_dbscan(bike_gdf, pt_gdf, threshold=120, buffer=100):
    """
    Create hub clusters from bike and PT stations using DBSCAN, aggregate PT line information,
    and generate a folium map.
    
    The function performs the following:
      - Reprojects the input GeoDataFrames to a metric CRS for clustering.
      - For bike stations, uses column "name" as identifier.
      - For PT stops, uses column "Stop" as identifier and keeps the "Line" information.
      - Clusters all points using DBSCAN with the given threshold (in meters).
      - For each cluster (hub), aggregates:
            * bike_stations: list of bike station names.
            * pt_stations: list of PT stop names.
            * lines: list of unique PT lines serving that hub.
      - Labels each hub as:
            "bike station" if only bike stations,
            "pt station" if only PT stops,
            "pt+bike station" if both types are present.
      - Reprojects the hub nodes (and original points) back to EPSG:4326 for folium mapping.
      - Creates a folium map displaying:
            - Bike stations (blue markers)
            - PT stops (green markers)
            - Hub nodes (red markers with popups showing hub ID, label, stations, and lines)
            - A 50 m reference circle at the map's center.
    
    Parameters:
      bike_gdf (GeoDataFrame): GeoDataFrame of bike stations with columns "name" and "geometry".
      pt_gdf (GeoDataFrame): GeoDataFrame of PT stops with columns "Stop", "Line", and "geometry".
      threshold (float): Distance threshold in meters for DBSCAN clustering.
      
    Returns:
      tuple: (folium Map object, hub DataFrame)a
    """




    # -------------------------------
    # 1. Prepare and Reproject Data
    # -------------------------------
    # Ensure input GeoDataFrames have CRS; if not, set to EPSG:4326.
    if bike_gdf.crs is None:
        bike_gdf = bike_gdf.set_crs("EPSG:4326")
    if pt_gdf.crs is None:
        pt_gdf = pt_gdf.set_crs("EPSG:4326")
        
    # Reproject to a metric CRS (EPSG:3857) for distance calculations.
    bike_gdf_metric = bike_gdf.to_crs("EPSG:3857")
    pt_gdf_metric = pt_gdf.to_crs("EPSG:3857")
    
    # For bike stations: add a column "station_type" and rename identifier.
    bike_df = bike_gdf_metric.copy()
    bike_df["station_type"] = "bike"
    bike_df = bike_df.rename(columns={"name": "identifier"})
    # Add a "Line" column for compatibility (bike stations don't have lines).
    bike_df["Line"] = None
    
    # For PT stops: add a column "station_type" and rename identifier.
    pt_df = pt_gdf_metric.copy()
    pt_df["station_type"] = "pt"
    pt_df = pt_df.rename(columns={"Stop": "identifier"})
    # Assume the PT GeoDataFrame has a "Line" column.
    
    # Combine both datasets. Ensure both have the same set of columns.
  
    # -------------------------------------------
    # 2. Cluster with DBSCAN
    # -------------------------------------------

    
    # ── 2.1  concatenate bike + PT rows  ─────────────────────────────
    combined = pd.concat(
        [bike_df[['identifier', 'station_type', 'geometry', 'Line', 'outflow']],
        pt_df  [['identifier', 'station_type', 'geometry', 'Line', 'outflow']]],
        ignore_index=True
    )

# ── 2.2  (n, 2) coordinate array in metres  ─────────────────────
    coords = combined.geometry.apply(lambda geom: (geom.x, geom.y)).tolist()

# ── 2.3  complete‑link agglomerative clustering  ─────────────────
#     • linkage='complete'  →  distance between clusters = max pairwise distance
#     • distance_threshold  →  stop merging when that distance > 300 m
#     • n_clusters=None     →  let the threshold decide the number of clusters
    clustering = DBSCAN(eps=threshold, min_samples=1).fit(coords)
    combined["cluster"] = clustering.labels_
    palette = cluster_palette(combined["cluster"])

    stops_df = (
        combined[["identifier", "station_type", "geometry", "cluster"]]
        .rename(columns={"cluster": "hub_id"})
        .copy())
    

    # buffered union per cluster  (metric CRS)
    cluster_polys = (
        combined
        .groupby("cluster", as_index=False)["geometry"]
        .apply(lambda g: g.buffer(buffer).unary_union)
        .reset_index()
    )

    cluster_polys = gpd.GeoDataFrame(cluster_polys, geometry="geometry", crs=combined.crs)
    cluster_polys_4326 = cluster_polys.to_crs("EPSG:4326")
    polys = (
        stops_df.groupby("hub_id", as_index=False)["geometry"]
                .apply(lambda g: g.buffer(buffer).unary_union)
                .reset_index()
    )
    polys = gpd.GeoDataFrame(polys, geometry="geometry", crs="EPSG:3857")
    polys_4326 = polys.to_crs("EPSG:4326")
    stops_4326 = stops_df.to_crs("EPSG:4326")
    # -------------------------------------------
    # 3. Aggregate Cluster Data into Hubs
    # -------------------------------------------
    hub_data = []
    for cluster_label, group in combined.groupby("cluster"):
        centroid = group.unary_union.centroid
        # Get lists of identifiers.
        bike_list = group[group["station_type"] == "bike"]["identifier"].tolist()
        pt_list = group[group["station_type"] == "pt"]["identifier"].tolist()
        # For PT stops, also collect the unique lines (ignoring NaN).
        pt_lines = list(group[group["station_type"] == "pt"]["Line"].dropna().unique())
        
        # Determine label based on cluster contents.
        if bike_list and not pt_list:
            label = "bike station"
        elif pt_list and not bike_list:
            label = "pt station"
        elif bike_list and pt_list:
            label = "pt+bike station"
        else:
            label = "unknown"
        
        hub_data.append({
            "hub_id": cluster_label,
            "bike_stations": bike_list,
            "pt_stations": pt_list,
            "lines": pt_lines,
            "label": label,
            "geometry": centroid
        })
    
    hub_df = pd.DataFrame(hub_data)
    # Convert hub_df to a GeoDataFrame.
    hubs_gdf = gpd.GeoDataFrame(hub_df, geometry="geometry", crs="EPSG:3857")
    
    # -------------------------------------------
    # 4. Create the Folium Map
    # -------------------------------------------
    # Reproject data back to EPSG:4326 for folium.
    hubs_gdf_4326 = hubs_gdf.to_crs("EPSG:4326")
    bike_gdf_4326 = bike_gdf.to_crs("EPSG:4326")
    pt_gdf_4326 = pt_gdf.to_crs("EPSG:4326")
    
    # Compute map center as the average of all bike and PT points.
    all_points = pd.concat([bike_gdf_4326[['geometry']], pt_gdf_4326[['geometry']]])
    avg_lat = all_points.geometry.y.mean()
    avg_lon = all_points.geometry.x.mean()
    
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)
    
    # Plot bike stations (blue).
    for _, row in bike_gdf_4326.iterrows():
        lat, lon = row.geometry.y, row.geometry.x
        folium.CircleMarker(
            location=(lat, lon),
            radius=4,
            color="blue",
            fill=True,
            fill_color="blue",
            popup=folium.Popup(str(row["name"]), parse_html=True)
        ).add_to(m)
    
    # Plot PT stops (green).
    for _, row in pt_gdf_4326.iterrows():
        lat, lon = row.geometry.y, row.geometry.x
        folium.CircleMarker(
            location=(lat, lon),
            radius=4,
            color="green",
            fill=True,
            fill_color="green",
            popup=folium.Popup(str(row["Stop"]), parse_html=True)
        ).add_to(m)
    
    # Plot hub nodes (red) with popups including lines.
    for _, row in hubs_gdf_4326.iterrows():
        lat, lon = row.geometry.y, row.geometry.x
        popup_html = (
            f"<b>Hub {row['hub_id']}</b><br>"
            f"Label: {row['label']}<br>"
            f"Bike Stations: {row['bike_stations']}<br>"
            f"PT Stops: {row['pt_stations']}<br>"
            f"Lines: {row['lines']}"
        )
        folium.Marker(
            location=(lat, lon),
            icon=folium.Icon(color='red'),
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(m)
    # ---------------- CLUSTER PATCHES ----------------
    for _, row in cluster_polys_4326.iterrows():
        clust  = row["cluster"]
        colour = palette[clust]

        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _,
                col=colour: {"fillColor": col, "fillOpacity": 0.15,
                            "color": col, "weight": 1},
            tooltip=f"Cluster {clust}"
        ).add_to(m)

    # Add a 50 m reference circle at the map center.
    folium.Circle(
        location=(avg_lat, avg_lon),
        radius=threshold/2,
        color='red',
        fill=False,
        popup='Reference'
    ).add_to(m)
    
    return m, hub_df, stops_4326, polys_4326,


