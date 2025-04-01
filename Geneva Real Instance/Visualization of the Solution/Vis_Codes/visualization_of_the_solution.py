import folium
import json
import math
from shapely.geometry import Point
import geopandas as gpd

def visualize_bilevel_solution(cluster_df, solution_json_path, preprocessing_data_path, origin_id, destination_id, search=True):
    """
    Visualize the solution on a folium map.
    
    Parameters:
      cluster_df: GeoDataFrame of hubs with at least columns 'hub_id' and 'geometry'.
                  Geometry should be in EPSG:4326. If not, it is converted.
      solution_json_path: Path to the solution JSON file.
      preprocessing_data_path: Path to the network JSON file (contains detailed arc info).
      origin_id: Hub ID for search origin.
      destination_id: Hub ID for search destination.
      search: If True, add a separate search layer.
    
    Returns:
      A folium Map object with hubs and all alternatives drawn with a small offset.
      - For transfers==0: a line from origin to destination.
      - For transfers==1: a line from origin → transfer_node → destination.
      - For transfers==2: a line from origin → first transfer node → second transfer node → destination.
      The popup shows arc details and the line color is green if nu==1 and Flow≥1, orange if nu==1, else grey.
    
    Visualization:
        - Hubs are marked with red markers.
        - Alternatives are drawn with a small offset from the base line between origin and destination.
        - Search alternatives are drawn with a larger offset.
        - If an alternative is offered, it is drawn in orange, if it is selected is is highlighted in green.
        - If an alternative is not offered, it is drawn in grey.
        - Blue node is the search origin, pink node is the search destination.
    """
    # Convert cluster_df to EPSG:4326 if necessary.
    if cluster_df.crs != "EPSG:4326":
        cluster_df = cluster_df.to_crs("EPSG:4326")
    
    # Build mapping from hub_id to (lat, lon)
    hub_coords = {}
    for idx, row in cluster_df.iterrows():
        hub_coords[row['hub_id']] = (row.geometry.y, row.geometry.x)
    
    # Compute map center.
    avg_lat = sum(lat for lat, lon in hub_coords.values()) / len(hub_coords)
    avg_lon = sum(lon for lat, lon in hub_coords.values()) / len(hub_coords)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)
    
    # Create FeatureGroups.
    hubs_fg = folium.FeatureGroup(name="Hubs", show=False)
    arcs_fg = folium.FeatureGroup(name="Alternatives", show=False)
    search_fg = folium.FeatureGroup(name=f"OD Search: {origin_id}->{destination_id}")
    instance_hubs_fg = folium.FeatureGroup(name="Instance Hubs")
    
    # Plot hub markers.
    for idx, row in cluster_df.iterrows():
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
        ).add_to(hubs_fg)
    
    # Load network data.
    with open(preprocessing_data_path, "r") as f:
        net_data = json.load(f)
    # Build mapping from arc_id to detailed arc info.
    arc_mapping = {}
    for key, arc_list in net_data.get("arcs_pt_bike", {}).items():
        for arc in arc_list:
            arc_mapping[arc["arc_id"]] = arc
    for key, arc_list in net_data.get("arcs_pt_only", {}).items():
        for arc in arc_list:
            arc_mapping[arc["arc_id"]] = arc

    instance_hub_ids = net_data.get("nodes", [])
    for hub in cluster_df.itertuples():
        if hub.hub_id in instance_hub_ids:
            lat, lon = hub.geometry.y, hub.geometry.x
            popup_html = (
                f"<b>Hub {hub.hub_id}</b><br>"
                f"Label: {hub.label}<br>"
                f"Bike Stations: {hub.bike_stations}<br>"
                f"PT Stops: {hub.pt_stations}<br>"
                f"Lines: {hub.lines}"
            )
            folium.Marker(
                location=(lat, lon),
                icon=folium.Icon(color='blue', icon='info-sign'),
                popup=folium.Popup(popup_html, max_width=300)
            ).add_to(instance_hubs_fg)

    # Load solution data and filter out car alternatives.
    with open(solution_json_path, "r") as f:
        sol_data = json.load(f)
    solution_instances = [inst for inst in sol_data.get("instances", []) 
                          if "b" not in inst.get("Arc ID", "").lower()]
    
    # Group solution instances by OD key.
    od_groups = {}
    for inst in solution_instances:
        od_str = inst.get("OD", "")
        if "->" not in od_str:
            continue
        od_groups.setdefault(od_str, []).append(inst)
    
    # Set offset factor (adjust as needed).
    offset_factor = 0.00005

    # For each OD group, draw the alternatives with an offset.
    for od_str, group in od_groups.items():
        # Parse origin and destination from od_str.
        origin_str, dest_str = od_str.split("->")
        try:
            o_id = int(origin_str)
            d_id = int(dest_str)
        except ValueError:
            o_id, d_id = origin_str, dest_str
        if o_id not in hub_coords or d_id not in hub_coords:
            continue
        
        base_origin = hub_coords[o_id]
        base_dest = hub_coords[d_id]
        
        # Compute base vector from origin to destination.
        dx = base_dest[1] - base_origin[1]
        dy = base_dest[0] - base_origin[0]
        norm = math.sqrt(dx**2 + dy**2)
        perp = (-dy/norm, dx/norm) if norm != 0 else (0, 0)
        
        n_alts = len(group)
        for idx, inst in enumerate(group):
            # Compute offset: center the alternatives.
            offset_multiplier = idx - (n_alts - 1) / 2.0
            overall_offset = (perp[0] * offset_factor * offset_multiplier,
                              perp[1] * offset_factor * offset_multiplier)
            
            # Lookup detailed arc info from network data.
            arc_id = inst.get("Arc ID")
            arc_info = arc_mapping.get(arc_id, {})
            transfers = arc_info.get("transfers", 0)
            
            # Build base polyline coordinates.
            coords = [base_origin]
            transfer_info = ""
            if transfers == 0:
                # Direct arc: nothing in between.
                pass
            elif transfers == 1:
                t_node = arc_info.get("transfer_node")
                transfer_info = f"Transfer Node: {t_node}"
                if t_node is not None and t_node in hub_coords:
                    coords.append(hub_coords[t_node])
            elif transfers == 2:
                t_nodes = arc_info.get("transfer_nodes")
                transfer_info = f"Transfer Node: {t_nodes}"
                if t_nodes and isinstance(t_nodes, list) and len(t_nodes) >= 2:
                    if t_nodes[0] in hub_coords:
                        coords.append(hub_coords[t_nodes[0]])
                    if t_nodes[1] in hub_coords:
                        coords.append(hub_coords[t_nodes[1]])
            coords.append(base_dest)
            
            # Apply offset to each coordinate.
            polyline_coords = [(lat + overall_offset[0], lon + overall_offset[1]) for lat, lon in coords]
            
            # Determine color.
            nu_val = inst.get("nu", 0)
            flow_val = inst.get("Flow (q)", 0)
            if  flow_val >= 1:
                line_color = "green"
            elif nu_val == 1 and flow_val < 1:
                line_color = "orange"
            else:
                line_color = "grey"
            
            popup_text = (
                f"Arc {arc_id}<br>"
                f"Type: {inst.get('Type', 'N/A')}<br>"
                f"Number of Transfers: {inst.get('Transfers', 'N/A')}<br>"
                f"{transfer_info}<br>"
                f"Mile Type: {inst.get('Mile Type', 'N/A')}<br>"
                f"Bike Price: {inst.get('Bike Price', 'N/A')}<br>"
                f"Flow: {inst.get('Flow (q)', 0)}"
            )
            
            folium.PolyLine(
                locations=polyline_coords,
                color=line_color,
                weight=2,
                popup=folium.Popup(popup_text, parse_html=True)
            ).add_to(arcs_fg)
    
    # Search layer: add a separate layer for the searched OD pair with offset applied.
    if search:
        # Add special markers for search origin and destination.
        if origin_id in hub_coords:
            folium.Marker(
                location=hub_coords[origin_id],
                icon=folium.Icon(color='darkblue', icon='flag'),
                popup=f"Search Origin: {origin_id}"
            ).add_to(search_fg)
        if destination_id in hub_coords:
            folium.Marker(
                location=hub_coords[destination_id],
                icon=folium.Icon(color='pink', icon='flag'),
                popup=f"Search Destination: {destination_id}"
            ).add_to(search_fg)
        
        search_key = f"{origin_id}->{destination_id}"
        if search_key in od_groups:
            group = od_groups[search_key]
            # Compute base vector for the searched OD pair.
            base_origin = hub_coords[origin_id]
            base_dest = hub_coords[destination_id]
            dx = base_dest[1] - base_origin[1]
            dy = base_dest[0] - base_origin[0]
            norm = math.sqrt(dx**2 + dy**2)
            perp = (-dy/norm, dx/norm) if norm != 0 else (0, 0)
            n_alts = len(group)
            for idx, inst in enumerate(group):
                offset_multiplier = idx - (n_alts - 1) / 2.0
                overall_offset = (perp[0] * offset_factor * offset_multiplier,
                                  perp[1] * offset_factor * offset_multiplier)
                arc_id = inst.get("Arc ID")
                arc_info = arc_mapping.get(arc_id, {})
                transfers = arc_info.get("transfers", 0)
                coords = [base_origin]
                transfer_info = ""
                if transfers == 0:
                    pass
                elif transfers == 1:
                    t_node = arc_info.get("transfer_node")
                    transfer_info = f"Transfer Node: {t_node}"
                    if t_node is not None and t_node in hub_coords:
                        coords.append(hub_coords[t_node])
                elif transfers == 2:
                    t_nodes = arc_info.get("transfer_nodes")
                    transfer_info = f"Transfer Node: {t_node}"
                    if t_nodes and isinstance(t_nodes, list) and len(t_nodes) >= 2:
                        if t_nodes[0] in hub_coords:
                            coords.append(hub_coords[t_nodes[0]])
                        if t_nodes[1] in hub_coords:
                            coords.append(hub_coords[t_nodes[1]])
                coords.append(base_dest)
                search_coords = [(lat + overall_offset[0], lon + overall_offset[1]) for lat, lon in coords]
                
                nu_val = inst.get("nu", 0)
                flow_val = inst.get("Flow (q)", 0)
                if  flow_val >= 1:
                    line_color = "green"
                elif nu_val == 1 and flow_val < 1:
                    line_color = "orange"
                else:
                    line_color = "grey"
                popup_text = (
                    f"Arc {arc_id}<br>"
                    f"Type: {inst.get('Type', 'N/A')}<br>"
                    f"Number of Transfers: {inst.get('Transfers', 'N/A')}<br>"
                    f"{transfer_info}<br>"
                    f"Mile Type: {inst.get('Mile Type', 'N/A')}<br>"
                    f"Bike Price: {inst.get('Bike Price', 'N/A')}<br>"
                    f"Flow: {flow_val}"
                )
                folium.PolyLine(
                    locations=search_coords,
                    color=line_color,
                    weight=3,
                    popup=folium.Popup(popup_text)
                ).add_to(search_fg)
    
    # Add layers and layer control.
    m.add_child(hubs_fg)
    m.add_child(arcs_fg)
    m.add_child(search_fg)
    m.add_child(instance_hubs_fg)
    folium.LayerControl().add_to(m)
    
    return m

# Example usage:
# m = visualize_solution(cluster_df, "solution.json", "network.json", origin_id=4, destination_id=5, search=True)
# m.save("final_solution_map.html")
# m  # To display the map.
