import random
import numpy as np
import os
import json
import geopandas as gpd
from math import sqrt
from shapely import wkb
from Codes.filter_alts import filter_alternatives
from Codes.create_bike_pt_alts import create_pt_and_ptbike_alternatives
from Codes.compute_delta import compute_delta_A1_v2_in_chunks
from Codes.precompute_direct_alternatives import euclidean_distance, precompute_direct_pt_alternatives, precompute_direct_bike_alternatives


# --- Revised Instance Generator Using Real Network Data ---
def generate_instance_real(folder_path, seed_number, hub_df, od_counts,
                           beta_cost_range, beta_time_range, beta_transfer_range, beta_buffer_range,
                           capacity_range, inventory_range, 
                           fixed_pt_price_value=4, bike_cost_operator=0.5, ridership_weight=2,
                           max_disp_alts=10, min_demand=20, max_demand=50, max_travel_time=80,
                           min_od_distance=500, bike_max_distance=3000, transfer_buffer_range=(1,10),
                           use_fixed_beta_values=False, 
                           fixed_beta_cost = 0.9, fixed_beta_time = 0.6, fixed_beta_transfer = 0.4, fixed_beta_buffer = 0.2                           
                           ):
    """
    Generate an instance from a real network.
    
    Inputs:
      - folder_path: Output folder for JSON/TXT files.
      - seed_number: Random seed.
      - hub_df: GeoDataFrame of nodes with columns: 'hub_id', 'bike_stations', 'pt_stations',
                'lines', 'label', 'geometry' (EPSG:3857). Ensure geometry is properly loaded.
      - num_od_pairs: Number of O-D pairs to sample.
      - fixed_pt_price_value: Fixed PT price.
      - bike_cost_operator: Fixed bike cost per minute.
      - ridership_weight: Ridership weight.
      - max_disp_alts: Maximum number of alternatives displayed.
      - min_demand, max_demand: Demand range for O-D pairs.
      - max_travel_time: Maximum allowed total travel time (in minutes) for alternatives.
      - min_od_distance: Minimum Euclidean distance between nodes to form an O-D pair.
      - bike_max_distance: Maximum allowed bike travel distance (in meters).
      - transfer_buffer_range: Range for waiting time (in minutes) per transfer.
    
    Process:
      1. Derive nodes_list from hub_df.
      2. Form O-D pairs from hub_df nodes (using Euclidean distance > min_od_distance)
         and sample num_od_pairs.
      3. Assign random demand and sensitivity parameters (alpha, beta, theta) for each O-D pair.
      4. Generate alternatives (A1, A2, B) using create_pt_and_ptbike_alternatives.
      5. Filter alternatives (A1 and A2) to remove those with total_travel_time > max_travel_time.
      6. Compute delta values for PT+bike alternatives (A1) in chunks.
      7. Build an instance_data dictionary matching the original JSON structure.
      8. Write instance_data to JSON and TXT files.
    
    Returns:
      Paths to the JSON and TXT instance files.
    """
    random.seed(seed_number)
    np.random.seed(seed_number)
    
    # ===============================================
    # 0. Helper Functions for Random Terms
    # ===============================================

    def random_alpha():
        return fixed_beta_cost if use_fixed_beta_values else random.uniform(*beta_cost_range)
    def random_beta():
        return fixed_beta_time if use_fixed_beta_values else random.uniform(*beta_time_range)
    def random_theta():
        return fixed_beta_transfer if use_fixed_beta_values else random.uniform(*beta_transfer_range)
    def random_buffer():
        return fixed_beta_buffer if use_fixed_beta_values else random.randint(*beta_buffer_range)
    
    def create_demand_from_od_pairs(od_pairs, od_counts_df, hub_df, min_demand, max_demand):
        """
        Create a demand dictionary from a list of OD pairs and aggregated od_counts data.
        
        Parameters:
        od_pairs: List of OD pairs, where each pair is a tuple (o, d) with o and d being hub records.
        od_counts_df: DataFrame with columns ['origin_hub', 'destination_hub', 'trip_count'] 
                        representing aggregated trip counts.
        hub_df: GeoDataFrame of hubs containing at least 'hub_id' and 'label'.
        min_demand, max_demand: Bounds for the random addition if at least one hub is PT+bike.
        
        Returns:
        A dictionary mapping (origin_hub, destination_hub) to a demand value.
        
        Rule:
        - If both origin and destination hub labels are exactly "bike station" (case-insensitive),
            then demand = base_trip_count + random.randint(1, 10).
        - Otherwise (e.g., if one or both are labeled "pt+bike" or "pt station"),
            then demand = base_trip_count + random.randint(min_demand, max_demand).
        - If an OD pair is not found in od_counts_df, base_trip_count defaults to 0.
        """
        # Build a mapping from (origin_hub, destination_hub) to trip_count using od_counts_df.
        od_counts = {}
        for idx, row in od_counts_df.iterrows():
            od_counts[(row['origin_hub'], row['destination_hub'])] = row['trip_count']
        
        # Build a mapping from hub_id to label.
        hub_labels = hub_df.set_index('hub_id')['label'].to_dict()
        
        demand_dict = {}
        
        for (o, d) in od_pairs:
            key = (o['hub_id'], d['hub_id'])
            base_count = od_counts.get(key, 0)
            origin_label = hub_labels.get(o['hub_id'], "").lower()
            
            if origin_label == "bike station":
                dem = base_count + random.randint(1, 10)
            elif origin_label == "pt+bike":
                dem = base_count + random.randint(min_demand, max_demand)
            else:
                dem = random.randint(min_demand, max_demand)
            demand_dict[key] = dem
        return demand_dict

    # ===============================================
    # 1. Determine Nodes
    # ===============================================

    # Ensure geometry is in proper format: if stored as WKB bytes, convert to shapely geometries.
    #hub_df['geometry'] = hub_df['geometry'].apply(lambda geom: wkb.loads(geom) if isinstance(geom, bytes) else geom)
    
    # 1.1 Derive nodes_list.
    nodes_list = hub_df['hub_id'].tolist()
    hub_records = hub_df.to_dict('records')

    

    # ===============================================
    # 2. Generate O-D Pairs and Alternatives Using the Real Network
    # ===============================================
    
    # dict keyed by (o,d), each value is list of arcs for PT+Bike (A1), PT-only (A2), and Car (A3) alternatives.
    # This function generates all possible alternatives for all O-D pairs. Generated alternatives are direct, 1 trarnsfer, and 2 transfer. 
    # The function currently do not distinguish based on PT mode (e.g., bus, tram, metro, etc.). This will be added later on. 

    A1, A2, B, od_pairs = create_pt_and_ptbike_alternatives(hub_df, 
                                                  min_od_distance=min_od_distance, 
                                                  bike_max_distance=bike_max_distance,
                                                  scaling_pt=0.06, scaling_bike=0.04, scaling_car=0.1,
                                                  transfer_buffer_range=transfer_buffer_range)
    
    # ===============================================
    # 3. Filter Generated Alternatives Based on Max Travel Time
    # ===============================================

    #If an alternative below the threshold is not available, the O-D pair is removed from the list.
    #keys_to_keep is the set of O-D pairs that have at least one alternative below the threshold.

    A1_filtered, A2_filtered, B_filtered, keys_to_keep = filter_alternatives(A1, A2, B, max_travel_time=max_travel_time)
    
    od_counts_filtered = od_counts[
    od_counts.apply(lambda row: (row['origin_hub'], row['destination_hub']) in keys_to_keep, axis=1)
]
    # ===============================================
    # 4. Create Demand, Station Capacities, Station Inventories and O-D Based Choice Parameters
    # ===============================================
    
    # After keys_to_keep is obtained, update the O-D Pairs:
    
    od_pairs = [(o, d) for (o, d) in od_pairs if (o['hub_id'], d['hub_id']) in keys_to_keep]   
    print(f"Number of O-D pairs: {len(od_pairs)}")
    print(od_pairs)
    
    od_demand = create_demand_from_od_pairs(od_pairs, od_counts_filtered, hub_df, min_demand, max_demand)
    alpha_vals = {}
    beta_vals = {}
    theta_vals = {}
    
    station_capacity = {}
    station_inventory = {}

    for (o, d) in od_pairs:
        key_od = (o['hub_id'], d['hub_id'])
        alpha_vals[key_od] = round(random_alpha(), 3)
        beta_vals[key_od] = round(random_beta(), 3)
        theta_vals[key_od] = round(random_theta(), 3)
    
    stations_list = [node['hub_id'] for node in hub_records if "bike" in node['label'].lower()]
    for station in stations_list:
        station_capacity[station] = random.randint(*capacity_range)
        station_inventory[station] = random.randint(*inventory_range)
    
    # ===============================================
    # 5. Compute Node Based Indicator Function delta_ia
    # ===============================================
    # delta_ia is an indicator function that assigns +1, -1, or 0 to each node and alternative that are in subset A1.
    # Key: (i, arc_id) => +1, -1, or 0
    # If i_in is a station, delta_ia[(i_in, arc_id)] = -1
    # If i_out is a station, delta_ia[(i_out, arc_id)] = +1

    delta_A1 = compute_delta_A1_v2_in_chunks(A1_filtered, stations_list, chunk_size=100)
    delta_ia_dict = {}
    for (station, arc_id), value in delta_A1.items():
        if arc_id not in delta_ia_dict:
            delta_ia_dict[arc_id] = {}
        delta_ia_dict[arc_id][station] = value

    # ===============================================
    # 6. Prepare Intance Data For JSON and TXT Files
    # ===============================================

    instance_data = {
        "random_seed": seed_number,
        "max_disp_alts": max_disp_alts,
        "ridership_weight": ridership_weight,
        "nodes": nodes_list,
        "edges": [],  # Real network edges can be added if available.
        "fixed_pt_price_value": fixed_pt_price_value,
        "bike_cost_operator": bike_cost_operator,
        "bike_stations": {
            "station_list": stations_list,
            "station_capacity": station_capacity,  # Add if available.
            "station_inventory": station_inventory  # Add if available.
        },
        "OD_pairs": [
            {
                "origin": o['hub_id'],
                "destination": d['hub_id'],
                "demand": od_demand[(o['hub_id'], d['hub_id'])],
                "alpha": alpha_vals[(o['hub_id'], d['hub_id'])],
                "beta": beta_vals[(o['hub_id'], d['hub_id'])],
                "theta": theta_vals[(o['hub_id'], d['hub_id'])]
            }
            for (o, d) in od_pairs
        ],
        "arcs_pt_bike": {
            f"{o['hub_id']}_{d['hub_id']}": A1_filtered[(o['hub_id'], d['hub_id'])]
            for (o, d) in od_pairs if (o['hub_id'], d['hub_id']) in A1_filtered
        },
        "arcs_pt_only": {
            f"{o['hub_id']}_{d['hub_id']}": A2_filtered[(o['hub_id'], d['hub_id'])]
            for (o, d) in od_pairs if (o['hub_id'], d['hub_id']) in A2_filtered
        },
        "car_paths": {
            f"{o['hub_id']}_{d['hub_id']}": B_filtered[(o['hub_id'], d['hub_id'])]
            for (o, d) in od_pairs if (o['hub_id'], d['hub_id']) in B_filtered
        },
        "delta_ia": delta_ia_dict
    }
    
    # 8. Write instance_data to a JSON file.
    instance_file_json = os.path.join(folder_path, f"real_instance_{seed_number}_{len(nodes_list)}_{len(od_pairs)}.json")
    with open(instance_file_json, "w") as f:
        json.dump(instance_data, f, indent=2)
    print(f"Instance data successfully written to: {instance_file_json}")
    
    # 9. Write instance_data to a TXT file.
    txt_folder = folder_path.replace("json", "txt")
    instance_file_txt = os.path.join(txt_folder, f"real_instance_{seed_number}_{len(nodes_list)}_{len(od_pairs)}.txt")
    with open(instance_file_txt, "w") as f:
        f.write(f"Random Seed Value: {seed_number}\n\n")
        f.write(f"Weight of Multimodal Ridership: {ridership_weight}\n\n")
        f.write(f"Max Number of Alternatives Displayed: {max_disp_alts}\n\n")
        f.write("=== NODES ===\n")
        f.write(f"All Nodes: {nodes_list}\n\n")
        f.write(f"Fixed PT Price: {fixed_pt_price_value}\n\n")
        f.write(f"Fixed Bike Cost per Minute: {bike_cost_operator}\n\n")
        f.write("=== BIKE STATIONS ===\n")
        for st in stations_list:
            f.write(f"Station Node = {st}\n")
        f.write("\n")
        f.write("=== OD PAIRS ===\n")
        for (o, d) in od_pairs:
            f.write(f"(origin={o['hub_id']}, destination={d['hub_id']}), Demand = {od_demand[(o['hub_id'], d['hub_id'])]}\n")
        f.write("\n")
        f.write("=== ARCS FOR PT+BIKE (A1) ===\n")
        for (o, d) in A1_filtered:
            f.write(f"OD: ({o}_{d})\n")
            for arc in A1_filtered[(o, d)]:
                f.write(f"   {arc}\n")
        f.write("\n")
        f.write("=== ARCS FOR PT-ONLY (A2) ===\n")
        for (o, d) in A2_filtered:
            f.write(f"OD: ({o}_{d})\n")
            for arc in A2_filtered[(o, d)]:
                f.write(f"   {arc}\n")
        f.write("\n")
        f.write("=== CAR PATHS (B) ===\n")
        for (o, d) in B_filtered:
            f.write(f"OD: ({o}_{d})\n")
            for path in B_filtered[(o, d)]:
                f.write(f"   {path}\n")
        f.write("\n")
        f.write("=== SENSITIVITIES (alpha, beta, theta) ===\n")
        for (o, d) in od_pairs:
            f.write(f"OD: ({o['hub_id']}_{d['hub_id']}) -> alpha={alpha_vals[(o['hub_id'], d['hub_id'])]}, beta={beta_vals[(o['hub_id'], d['hub_id'])]}, theta={theta_vals[(o['hub_id'], d['hub_id'])]}\n")
        f.write("\n")
        f.write("=== DELTA (for PT+BIKE) ===\n")
        for (arc_id, station_dict) in delta_ia_dict.items():
            for station, value in station_dict.items():
                f.write(f"arc_id={arc_id}, station={station}, delta={value}\n")
        f.write("\n")
    
    print(f"Instance data successfully written to: {instance_file_txt}")
    
    return instance_file_json, instance_file_txt

# --- End of Instance Generator Code ---
