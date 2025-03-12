import random
import networkx as nx
import numpy as np
import os
import json
import matplotlib.pyplot as plt
import networkx as nx


def generate_instance(folder_path,seed_number,num_nodes,num_stations,num_od_pairs,max_demand,min_demand,fixed_pt_price_value,bike_cost_operator,ridership_weight,max_disp_alts,travel_time_range,bike_time_range,cost_range_car,beta_cost_range,beta_time_range,beta_transfer_range
                        ,fuel_cost_range,multimodal_arc_range,pt_arc_range,capacity_range,inventory_range, use_fixed_beta_values=False, fixed_beta_cost=0.9, fixed_beta_time=0.6, fixed_beta_transfer=0.4):
    
    # Set a random seed (optional)

    random.seed(seed_number)
    np.random.seed(seed_number)
   
    # ===============================================
    # 2. Generate the Random Network (Nodes + Edges)
    # ===============================================
    # We'll use a random geometric graph or a simple ER (Erdos-Renyi) graph 
    # as an example. For demonstration, let's do Erdos-Renyi.
    p_edge = 0.8  # probability of having an edge between two nodes

    G = nx.erdos_renyi_graph(n=num_nodes, p=p_edge, seed=seed_number, directed=False)
    # We want a connected graph or at least mostly connected. 
    # For a real instance, you might ensure connectivity or generate until it's connected.

    # Convert to a directed version if you want to treat arcs as directed
    # G = G.to_directed()

    # Collect node list
    nodes_list = list(G.nodes)

    print("Generated random graph with edges:")
    print(G.edges)

    # ===============================================
    # 3. Define Which Nodes Have Bike Stations
    # ===============================================
    # Randomly pick a subset of nodes to be bike stations (I subset)
    stations_list = random.sample(nodes_list, k=num_stations)

    # Assign random capacity & inventory to each station
    station_capacity = {}
    station_inventory = {}
    for station in stations_list:
        station_capacity[station] = random.randint(*capacity_range)
        station_inventory[station] = random.randint(*inventory_range)

    # ===============================================
    # 4. Create Random O-D Pairs
    # ===============================================
    # We'll pick random distinct pairs (o, d) with o != d
    od_pairs = []
    while len(od_pairs) < num_od_pairs:
        o = random.choice(nodes_list)
        d = random.choice(nodes_list)
        if o != d and (o, d) not in od_pairs:
            od_pairs.append((o, d))

    # For each O-D pair, we'll assign a demand
    od_demand = {}
    for (o, d) in od_pairs:
        od_demand[(o, d)] = random.randint(min_demand, max_demand)

    # ===============================================
    # 5. Helper Functions
    # ===============================================

    def random_travel_time():
        return random.randint(*travel_time_range)
    def random_bike_time():
        return random.randint(*bike_time_range)

    def random_car_cost():
        return random.uniform(*cost_range_car)

    def random_alpha():
        return fixed_beta_cost if use_fixed_beta_values else random.uniform(*beta_cost_range)

    def random_beta():
        return fixed_beta_time if use_fixed_beta_values else random.uniform(*beta_time_range)

    def random_theta():
        return fixed_beta_transfer if use_fixed_beta_values else random.uniform(*beta_transfer_range)


    def random_fuel_cost():
        return round(random.uniform(*fuel_cost_range), 2)
    
    def number_multimodal_arcs():
        return random.randint(*multimodal_arc_range)

    def number_pt_arcs():
        return random.randint(*pt_arc_range)
    
    # ===============================================
    # 6. Generate Travel Arcs/Paths for Each O-D Pair
    # ===============================================
    # For demonstration, we define:
    #   A1: multimodal (PT + bike) arcs = subset of edges or direct routes
    #   A2: PT-only arcs = some subset
    #   B: car paths (we can store a single or multiple "shortest" car paths)
    #
    # In reality, you'd do a routing or shortest path procedure.
    # For now, let's randomly pick 1-2 "PT-only" arcs and 1-2 "multimodal" arcs per OD.
    # Then define a car path similarly (maybe just the direct shortest path for simplicity).

    A1 = {}  # dict keyed by (o,d), each value is list of arcs for PT+Bike
    A2 = {}  # dict keyed by (o,d), each value is list of arcs for PT-only
    B  = {}  # dict keyed by (o,d), each value is list of arcs (car) or path

    # We'll keep a global dictionary for delta_{i,a}.
    # Key: (i, arc_id) => +1, -1, or 0
    delta_ia = {}  # We'll ONLY populate this for arcs in A1
    arc_counter = 0

    for (o, d) in od_pairs:

        # ====================
        # Car Paths: exactly 1 route
        # ====================
        B[(o, d)] = []
        # We only want 1 route per OD => shortest path assumption
        # We'll just store a single arc record:
        arc_id = f"b_{arc_counter}"
        arc_counter += 1
        route_data = {
            "arc_id": arc_id,
            "travel_time": random_travel_time(),
            "fuel_cost": random_fuel_cost()
        }
        B[(o, d)].append(route_data)
        # Car arcs don't need delta_ia => skip

        # ====================
        # PT-only Arcs: multiple routes possible
        # ====================
        A2[(o, d)] = []
        num_pt_arcs = number_pt_arcs()  # keep multiple routes for PT
        for _ in range(num_pt_arcs):
            arc_id = f"a2_{arc_counter}"
            arc_counter += 1
            arc_data = {
                "arc_id": arc_id,
                "pt_time": random_travel_time(),
                "bike_time": 0, #no bike usage
                "fixed_pt_price": fixed_pt_price_value,
                "transfers": random.randint(0, 2)
            }
            A2[(o, d)].append(arc_data)

        # ====================
        # PT+Bike (A1) arcs: 
        #   - Must have >=1 transfer
        #   - Bike portion = first-mile (if o in I) OR last-mile (if d in I).
        #   - If neither o nor d in stations_list, we skip.
        # ====================
        A1[(o, d)] = []
        
        # Condition: only build A1 arcs if at least one (o or d) is in stations_list
        if (o in stations_list) or (d in stations_list):
            
            # Decide how many A1 arcs we want; let's allow 1 or 2
            num_multimodal_arcs = number_multimodal_arcs()
            for _ in range(num_multimodal_arcs):
                arc_id = f"a1_{arc_counter}"
                arc_counter += 1

                # Force at least 1 transfer (transfers >= 1)
                transfers_val = random.randint(1, 2)

                # We need to decide if it's a first-mile or last-mile arc:
                # 1) If both o and d are in stations_list, randomly pick first-mile or last-mile
                #    For simplicity, we do a 50-50 choice if both in I
                # 2) If only o in I, do first-mile
                # 3) If only d in I, do last-mile

                if (o in stations_list) and (d in stations_list):
                    # Randomly pick 0 => first mile, 1 => last mile
                    mile_type = random.choice(["first", "last"])
                elif (o in stations_list):
                    mile_type = "first"
                else:
                    mile_type = "last"

                # We'll define:
                #  - "first mile": bike from origin (o) to some intermediate node 'm',
                #    then PT from 'm' to d.
                #  - "last mile": PT from o to 'm', then bike from 'm' to destination (d).

                # We'll pick 'm' as either:
                #  - if first mile, 'm' could be any node != o (including possibly d)
                #  - if last mile, 'm' could be any node != d (including possibly o)

                # We'll require that 'm' is in the set of all nodes. 
                # If we want to ensure that 'm' is not also a station, that's optional. 
                # For simplicity, let's just pick from all nodes except the one it's not allowed to be.
                
                if mile_type == "first":
                    # Bike from o -> m
                    valid_choices = [x for x in stations_list if x != o if x!=d]
                    m = random.choice(valid_choices)

                    # The "arc" concept in your model lumps the entire route o->d as one arc,
                    # but with a bike portion from o->m and a PT portion from m->d.
                    # We'll store the "bike_orig_station = o" and "bike_dest_station = m".
                    i_in = o
                    i_out = m

                else:  # mile_type == "last"
                    # Bike from m -> d
                    valid_choices = [x for x in stations_list if x != o if x!=d]
                    m = random.choice(valid_choices)

                    i_in = m
                    i_out = d

                # Build the arc data
                arc_data = {
                    "arc_id": arc_id,
                    "pt_time": random_travel_time(),    # total time of the PT portion
                    "bike_time": random_bike_time(),    #total time of the bike portion
                    "fixed_pt_price": fixed_pt_price_value,
                    "bike_cost": bike_cost_operator,
                    "transfers": transfers_val,
                    "bike_orig_station": i_in,
                    "bike_dest_station": i_out,
                    "mile_type": mile_type  # just to keep track for debugging
                }
                A1[(o, d)].append(arc_data)

                #  Build delta_{i,arc_id} for these arcs (since they're PT+Bike)
                #  If i_in is a station, delta_ia[(i_in, arc_id)] = -1
                #  If i_out is a station, delta_ia[(i_out, arc_id)] = +1
                #  But note, we only want to do it if i_in, i_out are in your stations_list
                for station in stations_list:
                    if station == i_in:
                        delta_ia[(station, arc_id)] = -1
                    elif station == i_out:
                        delta_ia[(station, arc_id)] = +1
                    else:
                        # optional to store 0
                        delta_ia[(station, arc_id)] = 0

    # ===============================================
    # 7. Generate Travel Sensitivities per O-D
    # ===============================================
    alpha_vals = {}
    beta_vals = {}
    theta_vals = {}
    for (o,d) in od_pairs:
        alpha_vals[(o,d)] = round(random_alpha(), 3)
        beta_vals[(o,d)] = round(random_beta(), 3)
        theta_vals[(o,d)] = round(random_theta(), 3)

    # ===============================================
    # 8. Write the Data to a JSON File
    # ===============================================


    instance_file = os.path.join(folder_path,  f"random_instance_{seed_number}_{num_nodes}_{num_stations}_{num_od_pairs}.json")


    delta_ia_dict = {}
    for (station, arc_id) in delta_ia:
        if arc_id not in delta_ia_dict:
            delta_ia_dict[arc_id] = {}
        delta_ia_dict[arc_id][station] = delta_ia[(station, arc_id)]


    instance_data = {
        "random_seed":seed_number,
        "max_disp_alts" : max_disp_alts,
        "ridership_weight": ridership_weight,
        "nodes": nodes_list,
        "edges": list(G.edges()),
        
        # Store operator cost info
        "fixed_pt_price_value": fixed_pt_price_value,
        "bike_cost_operator": bike_cost_operator,

        "bike_stations": {
            "station_list": stations_list,
            "station_capacity": station_capacity,
            "station_inventory": station_inventory
        },

        "OD_pairs": [
            {
                "origin": o,
                "destination": d,
                "demand": od_demand[(o, d)],
                "alpha": alpha_vals[(o, d)],
                "beta": beta_vals[(o, d)],
                "theta": theta_vals[(o,d)]
            }
            for (o, d) in od_pairs
        ],

        "arcs_pt_bike": {
            f"{o}_{d}": A1[(o, d)] for (o, d) in od_pairs
        },
        "arcs_pt_only": {
            f"{o}_{d}": A2[(o, d)] for (o, d) in od_pairs
        },
        "car_paths": {
            f"{o}_{d}": B[(o, d)] for (o, d) in od_pairs
        },


        # Delta only for arcs in A1
        "delta_ia": delta_ia_dict
    }

    with open(instance_file, "w") as f:
        json.dump(instance_data, f, indent=2)
        
    print(f"Instance data successfully written to: {instance_file}")

    # ===============================================
    # 9. Write the Data to a .txt File
    # ===============================================

    txt_file_path = folder_path.replace("json", "txt")

    instance_file_txt = os.path.join(txt_file_path,  f"random_instance_{seed_number}_{num_nodes}_{num_stations}_{num_od_pairs}.txt")

    with open(instance_file_txt, 'w') as f:
        f.write(f"Random Seed Value: {seed_number}\n\n")
        f.write(f"Weight of Multimodal Ridership: {ridership_weight}\n\n")
        f.write(f"Max Number of Alternatives Displayed: {max_disp_alts}\n\n")
        f.write("=== NODES ===\n")
        f.write(f"All Nodes: {nodes_list}\n\n")
        f.write(f"Fixed PT Price: {fixed_pt_price_value}\n\n")
        f.write(f"Fixed Bike Cost per Minute: {bike_cost_operator}\n\n")
        
        f.write("=== BIKE STATIONS (I) ===\n")
        for st in stations_list:
            f.write(f"Station Node = {st}, Capacity = {station_capacity[st]}, Inventory = {station_inventory[st]}\n")
        f.write("\n")
        
        f.write("=== OD PAIRS (W) ===\n")
        for (o,d) in od_pairs:
            f.write(f"(o={o}, d={d}), Demand = {od_demand[(o,d)]}\n")
        f.write("\n")
        
        f.write("=== ARCS FOR PT+BIKE (A1) ===\n")
        for (o,d) in A1:
            f.write(f"OD: ({o},{d})\n")
            for arc in A1[(o,d)]:
                f.write(f"   {arc}\n")
        f.write("\n")
        
        f.write("=== ARCS FOR PT-ONLY (A2) ===\n")
        for (o,d) in A2:
            f.write(f"OD: ({o},{d})\n")
            for arc in A2[(o,d)]:
                f.write(f"   {arc}\n")
        f.write("\n")
        
        f.write("=== CAR PATHS (B) ===\n")
        for (o,d) in B:
            f.write(f"OD: ({o},{d})\n")
            for path in B[(o,d)]:
                f.write(f"   {path}\n")
        f.write("\n")
        
        f.write("=== SENSITIVITIES (alpha, beta) ===\n")
        for (o,d) in od_pairs:
            f.write(f"OD: ({o},{d}) -> alpha={alpha_vals[(o,d)]}, beta={beta_vals[(o,d)]}, theta={theta_vals[(o,d)]}\n")
        f.write("\n")
        
        # ---------------------------------------------------------------------
        # Additional: Print out delta_{i,a} for PT+Bike arcs ONLY
        # ---------------------------------------------------------------------
        f.write("=== DELTA_{i,a} (Only for PT+Bike Arcs) ===\n")
        # If delta_ia is keyed by (station, arc_id), we can just iterate directly:
        for (station, arc_id) in delta_ia:
            value = delta_ia[(station, arc_id)]
            # Print in a simple line format
            f.write(f"arc_id={arc_id}, station={station}, delta={value}\n")
        f.write("\n")

    print(f"Instance data successfully written to {instance_file_txt}")

    return instance_file, instance_file_txt
