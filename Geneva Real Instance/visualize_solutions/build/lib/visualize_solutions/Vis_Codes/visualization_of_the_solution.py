import folium
import json
import math
from shapely.geometry import Point
import geopandas as gpd

def visualize_bilevel_solution(cluster_df, network_data_path, solution_json_path, origin_id, destination_id, search=True):
    """
    Visualize the solution on a folium map.
    
    Parameters:
      cluster_df: GeoDataFrame of hubs with at least columns 'hub_id' and 'geometry'.
                  Geometry should be in EPSG:4326. If not, it is converted.
      solution_json_path: Path to the solution JSON file.
      network_data_path: Path to the network JSON file (contains detailed arc info).
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
    #========================================
    #1. Create the nodes
    #========================================
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
    
    # Load network data.
    with open(network_data_path, "r") as f:
        net_data = json.load(f)
    # Build mapping from arc_id to detailed arc info.
    arc_mapping = {}
    for key, arc_list in net_data.get("arcs_pt_bike", {}).items():
        for arc in arc_list:
            arc_mapping[arc["arc_id"]] = arc
    for key, arc_list in net_data.get("arcs_pt_only", {}).items():
        for arc in arc_list:
            arc_mapping[arc["arc_id"]] = arc

   # Extract bike station information from the network data.
    bike_stations_info = net_data.get("bike_stations", {})
    station_capacity = bike_stations_info.get("station_capacity", {})
    station_inventory = bike_stations_info.get("station_inventory", {})

    # Plot hub markers.
    for idx, row in cluster_df.iterrows():
        lat, lon = row.geometry.y, row.geometry.x
        popup_html = (
            f"<b>Hub {row['hub_id']}</b><br>"
            f"Label: {row['label']}<br>"
            f"Bike Stations: {row['bike_stations']}<br>"
            f"PT Stops: {row['pt_stations']}<br>"
            f"Lines: {row['lines']}<br>"
        )
        # If the hub label includes "bike", add capacity and inventory info.
        if "bike" in row['label'].lower():
            cap = station_capacity.get(str(row['hub_id']), "N/A")
            inv = station_inventory.get(str(row['hub_id']), "N/A")
            popup_html += f"Capacity: {cap}<br>Inventory: {inv}"
        
        folium.Marker(
            location=(lat, lon),
            icon=folium.Icon(color='red'),
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(hubs_fg)
    #========================================
    #1.1 Create the nodes for the instance solution
    #========================================
    instance_hub_ids = net_data.get("nodes", [])
    for hub in cluster_df.itertuples():
        if hub.hub_id in instance_hub_ids:
            lat, lon = hub.geometry.y, hub.geometry.x
            popup_html = (
                f"<b>Hub {hub.hub_id}</b><br>"
                f"Label: {hub.label}<br>"
                f"Bike Stations: {hub.bike_stations}<br>"
                f"PT Stops: {hub.pt_stations}<br>"
                f"Lines: {hub.lines}<br>"
            )
            # If the hub label includes "bike", add capacity and inventory info.
            if "bike" in hub.label.lower():
                cap = station_capacity.get(str(hub.hub_id), "N/A")
                inv = station_inventory.get(str(hub.hub_id), "N/A")
                popup_html += f"Capacity: {cap}<br>Inventory: {inv}"
            folium.Marker(
                location=(lat, lon),
                icon=folium.Icon(color='blue', icon='info-sign'),
                popup=folium.Popup(popup_html, max_width=300)
            ).add_to(instance_hubs_fg)

    #========================================
    #2. Create the the trips
    #========================================

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
            
            # ——— detect super vs normal ———
            # — detect super vs normal & build line_str, transfer_opts —
            is_super = "lines_options" in arc_info
            if is_super:
                line_opts     = arc_info["lines_options"]
                transfer_opts = arc_info.get(
                    "transfer_nodes_options",
                    [[]] * len(line_opts)
                )
                # bracketed popup strings
                line_str = ", ".join(f"[{', '.join(opt)}]" for opt in line_opts)
                if transfers > 0:
                    transfer_str = ", ".join(
                        f"[{', '.join(map(str, opts))}]" for opts in transfer_opts
                    )
                else:
                    transfer_str = ""
                # use only the first option’s nodes for geometry
                transfer_nodes_list = transfer_opts[0] if transfers > 0 else []
            else:
                # normal arc
                lines = arc_info.get("lines", [])
                line_str = ", ".join(lines)
                if transfers == 1:
                    transfer_nodes_list = [arc_info.get("transfer_node")]
                    transfer_str = str(transfer_nodes_list[0])
                elif transfers == 2:
                    transfer_nodes_list = arc_info.get("transfer_nodes", [])
                    transfer_str = ", ".join(map(str, transfer_nodes_list))
                else:
                    transfer_nodes_list = []
                    transfer_str = ""

            # — build the coords sequence —
            coords = [base_origin]
            for node in transfer_nodes_list:
                if node in hub_coords:
                    coords.append(hub_coords[node])
            coords.append(base_dest)

            # apply offset
            polyline_coords = [
                (lat + overall_offset[0], lon + overall_offset[1])
                for lat, lon in coords
            ]

            # determine color
            nu_val   = inst.get("nu", 0)
            flow_val = inst.get("Flow (q)", 0)
            if flow_val >= 1:
                line_color = "green"
            elif nu_val == 1:
                line_color = "orange"
            else:
                line_color = "grey"

            # build popup
            popup_text = (
                f"Arc {arc_id}<br>"
                f"Type: {inst.get('Type', 'N/A')}<br>"
                f"Number of Transfers: {transfers}<br>"
            )
            popup_text += f"Lines: {line_str}<br>"
            if transfer_str:
                popup_text += f"Transfer Node(s): {transfer_str}<br>"
            popup_text += (
                f"Mile Type: {inst.get('Mile Type', 'N/A')}<br>"
                f"Bike Price: {inst.get('Bike Price', 'N/A')}<br>"
                f"Flow: {flow_val}"
            )

            folium.PolyLine(
                locations=polyline_coords,
                color=line_color,
                weight=2,
                popup=folium.Popup(popup_text, max_width=400, parse_html=True)
            ).add_to(arcs_fg)
    
    #========================================
    #3. Create a search engine for the selected OD pair
    #========================================

    # Search layer: add a separate layer for the searched OD pair with offset applied.
    if search:
        if origin_id in hub_coords:
            # Retrieve the row from cluster_df corresponding to the origin.
            origin_row = cluster_df[cluster_df['hub_id'] == origin_id].iloc[0]
            popup_html_origin = (
                f"<b>Hub {origin_row['hub_id']}</b><br>"
                f"Label: {origin_row['label']}<br>"
                f"Bike Stations: {origin_row['bike_stations']}<br>"
                f"PT Stops: {origin_row['pt_stations']}<br>"
                f"Lines: {origin_row['lines']}<br>"
            )
            # If the hub label includes "bike", add capacity and inventory info.
            if "bike" in origin_row['label'].lower():
                cap = station_capacity.get(str(origin_row['hub_id']), "N/A")
                inv = station_inventory.get(str(origin_row['hub_id']), "N/A")
                popup_html_origin += f"Capacity: {cap}<br>Inventory: {inv}"
            folium.Marker(
                location=hub_coords[origin_id],
                icon=folium.Icon(color='darkblue', icon='flag'),
                popup=folium.Popup(popup_html_origin, max_width=300)
            ).add_to(search_fg)

        if destination_id in hub_coords:
            # Retrieve the row from cluster_df corresponding to the destination.
            destination_row = cluster_df[cluster_df['hub_id'] == destination_id].iloc[0]
            popup_html_destination = (
                f"<b>Hub {destination_row['hub_id']}</b><br>"
                f"Label: {destination_row['label']}<br>"
                f"Bike Stations: {destination_row['bike_stations']}<br>"
                f"PT Stops: {destination_row['pt_stations']}<br>"
                f"Lines: {destination_row['lines']}<br>"
            )
            # Add capacity/inventory info for bike hubs.
            if "bike" in destination_row['label'].lower():
                cap = station_capacity.get(str(destination_row['hub_id']), "N/A")
                inv = station_inventory.get(str(destination_row['hub_id']), "N/A")
                popup_html_destination += f"Capacity: {cap}<br>Inventory: {inv}"
            folium.Marker(
                location=hub_coords[destination_id],
                icon=folium.Icon(color='pink', icon='flag'),
                popup=folium.Popup(popup_html_destination, max_width=300)
            ).add_to(search_fg)

        
        
        '''
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
        '''
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

                # — detect super vs normal & build strings —
                is_super = "lines_options" in arc_info
                if is_super:
                    line_opts     = arc_info["lines_options"]
                    transfer_opts = arc_info.get(
                        "transfer_nodes_options",
                        [[]] * len(line_opts)
                    )
                    line_str = ", ".join(f"[{', '.join(opt)}]" for opt in line_opts)
                    transfer_str = (
                        ", ".join(f"[{', '.join(map(str, opts))}]"
                                  for opts in transfer_opts)
                        if transfers > 0 else ""
                    )
                    transfer_nodes_list = transfer_opts[0] if transfers > 0 else []
                else:
                    lines = arc_info.get("lines", [])
                    line_str = ", ".join(lines)
                    if transfers == 1:
                        transfer_nodes_list = [arc_info.get("transfer_node")]
                        transfer_str = str(transfer_nodes_list[0])
                    elif transfers == 2:
                        transfer_nodes_list = arc_info.get("transfer_nodes", [])
                        transfer_str = ", ".join(map(str, transfer_nodes_list))
                    else:
                        transfer_nodes_list = []
                        transfer_str = ""

                # — build coords with offset —
                coords = [base_origin]
                for node in transfer_nodes_list:
                    if node in hub_coords:
                        coords.append(hub_coords[node])
                coords.append(base_dest)

                search_coords = [
                    (lat + overall_offset[0], lon + overall_offset[1])
                    for lat, lon in coords
                ]

                # color logic unchanged…
                nu_val   = inst.get("nu", 0)
                flow_val = inst.get("Flow (q)", 0)
                if flow_val >= 1:
                    line_color = "green"
                elif nu_val == 1:
                    line_color = "orange"
                else:
                    line_color = "grey"

                # build popup
                popup_text = (
                    f"Arc {arc_id}<br>"
                    f"Type: {inst.get('Type', 'N/A')}<br>"
                    f"Number of Transfers: {transfers}<br>"
                )
                popup_text += f"Lines: {line_str}<br>"
                if transfer_str:
                    popup_text += f"Transfer Node(s): {transfer_str}<br>"
                popup_text += f"Mile Type: {inst.get('Mile Type', 'N/A')}<br>"
                popup_text += f"Bike Price: {inst.get('Bike Price', 'N/A')}<br>"
                popup_text += f"Flow: {flow_val}"

                folium.PolyLine(
                    locations=search_coords,
                    color=line_color,
                    weight=3,
                    popup=folium.Popup(popup_text, max_width=400)
                ).add_to(search_fg)
    
    # Add layers and layer control.
    m.add_child(hubs_fg)
    m.add_child(arcs_fg)
    m.add_child(instance_hubs_fg)
    m.add_child(search_fg)
    folium.LayerControl().add_to(m)
    
    return m

# Example usage:
# m = visualize_solution(cluster_df, "solution.json", "network.json", origin_id=4, destination_id=5, search=True)
# m.save("final_solution_map.html")
# m  # To display the map.
