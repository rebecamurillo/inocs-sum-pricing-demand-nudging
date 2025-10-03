from Codes.precompute_direct_alternatives import euclidean_distance, precompute_direct_pt_alternatives, precompute_direct_bike_alternatives
import random


def create_pt_and_ptbike_alternatives(hub_df, 
                                      min_od_distance=500, 
                                      bike_max_distance=3000,
                                      scaling_pt=0.06, 
                                      scaling_bike=0.04,
                                      scaling_car=0.1,
                                      transfer_buffer_range=(1, 10)):
    """
    Using the real hub_df, this function:
      - Forms O-D pairs among nodes with Euclidean distance > min_od_distance.
      - Generates PT-only alternatives (A2): direct, 1-transfer, and 2-transfer.
      - Generates PT+bike alternatives (A1):
           * 1-transfer alternatives: first-mile (bike from origin to m, then PT from m to destination)
             and last-mile variants.
           * 2-transfer alternatives: combining a direct bike arc with 1-transfer PT alternatives.
      - Computes car alternatives (B) by scaling Euclidean distance.
    """
    A1 = {}
    A2 = {}
    B = {}
    arc_counter = 0
    all_nodes = hub_df.to_dict('records')
    # For PT alternatives, use nodes with PT connectivity.
    pt_nodes = [n for n in all_nodes if "pt" in n['label'].lower()]
    pt_alts = precompute_direct_pt_alternatives(pt_nodes, scaling_pt=scaling_pt)
    # Precompute bike alternatives using all nodes.
    bike_alts = precompute_direct_bike_alternatives(all_nodes, scaling_bike=scaling_bike)
    
    # Form OD pairs (all nodes with distance > min_od_distance)
    od_pairs = []
    for o in all_nodes:
        for d in all_nodes:
            if o['hub_id'] == d['hub_id']:
                continue
            if euclidean_distance(o['geometry'], d['geometry']) > min_od_distance:
                od_pairs.append((o, d))
    print(f"Number of O-D pairs: {len(od_pairs)}")
    print(od_pairs)
    
    for (o, d) in od_pairs:
        key = (o['hub_id'], d['hub_id'])
        A2[key] = []
        A1[key] = []
        B[key] = []
        # --- Car Alternative ---
        dist_od = euclidean_distance(o['geometry'], d['geometry'])
        car_time = int(dist_od * scaling_car)
        arc_id = f"b_{arc_counter}"
        arc_counter += 1
        B[key].append({
            "arc_id": arc_id,
            "travel_time": car_time,
            "fuel_cost": random.uniform(1, 5)
        })
        
        # --- PT-only Alternatives ---
        key_od = (o['hub_id'], d['hub_id'])
        if key_od in pt_alts:
            for arc in pt_alts[key_od]:
                new_arc = arc.copy()
                new_arc["arc_id"] = f"a2_{arc_counter}"
                arc_counter += 1
                new_arc["waiting_time"] = 0
                new_arc["total_travel_time"] = new_arc["pt_time"]
                new_arc["transfers"] = 0
                A2[key].append(new_arc)
        for m in pt_nodes:
            if m['hub_id'] in (o['hub_id'], d['hub_id']):
                continue
            key_om = (o['hub_id'], m['hub_id'])
            key_md = (m['hub_id'], d['hub_id'])
            if key_om in pt_alts and key_md in pt_alts:
                for arc1 in pt_alts[key_om]:
                    for arc2 in pt_alts[key_md]:
                        waiting_time = random.randint(*transfer_buffer_range)
                        total_pt_time = arc1["pt_time"] + arc2["pt_time"]
                        new_arc = {
                            "arc_id": f"a2_{arc_counter}",
                            "pt_time": total_pt_time,
                            "waiting_time": waiting_time,
                            "total_travel_time": total_pt_time + waiting_time,
                            "transfers": 1,
                            "lines": [arc1["line"], arc2["line"]],
                            "transfer_node": m['hub_id']
                        }
                        arc_counter += 1
                        A2[key].append(new_arc)
        for m in pt_nodes:
            if m['hub_id'] in (o['hub_id'], d['hub_id']):
                continue
            for n in pt_nodes:
                if n['hub_id'] in (o['hub_id'], d['hub_id'], m['hub_id']):
                    key_om = (o['hub_id'], m['hub_id'])
                    key_mn = (m['hub_id'], n['hub_id'])
                    key_nd = (n['hub_id'], d['hub_id'])
                    if key_om in pt_alts and key_mn in pt_alts and key_nd in pt_alts:
                        for arc1 in pt_alts[key_om]:
                            for arc2 in pt_alts[key_mn]:
                                for arc3 in pt_alts[key_nd]:
                                    waiting_time1 = random.randint(*transfer_buffer_range)
                                    waiting_time2 = random.randint(*transfer_buffer_range)
                                    total_pt_time = arc1["pt_time"] + arc2["pt_time"] + arc3["pt_time"]
                                    total_wait = waiting_time1 + waiting_time2
                                    new_arc = {
                                        "arc_id": f"a2_{arc_counter}",
                                        "pt_time": total_pt_time,
                                        "waiting_time": total_wait,
                                        "total_travel_time": total_pt_time + total_wait,
                                        "transfers": 2,
                                        "lines": [arc1["line"], arc2["line"], arc3["line"]],
                                        "transfer_nodes": [m['hub_id'], n['hub_id']]
                                    }
                                    arc_counter += 1
                                    A2[key].append(new_arc)
        
        # --- PT+bike Alternatives ---
        # 1-transfer: First-mile variant if o has bike connectivity.
        if "bike" in o['label'].lower():
            for m in all_nodes:
                if m['hub_id'] in (o['hub_id'], d['hub_id']):
                    continue
                if "bike" not in m['label'].lower():
                    continue
                key_om_bike = (o['hub_id'], m['hub_id'])
                key_md_pt = (m['hub_id'], d['hub_id'])
                if key_om_bike in bike_alts and key_md_pt in pt_alts:
                    for bike_arc in bike_alts[key_om_bike]:
                        if euclidean_distance(o['geometry'], m['geometry']) > bike_max_distance:
                            continue
                        for pt_arc in pt_alts[key_md_pt]:
                            waiting_time = random.randint(*transfer_buffer_range)
                            new_arc = {
                                "arc_id": f"a1_{arc_counter}",
                                "pt_time": pt_arc["pt_time"],
                                "bike_time": bike_arc["bike_time"],
                                "waiting_time": waiting_time,
                                "total_travel_time": pt_arc["pt_time"] + bike_arc["bike_time"] + waiting_time,
                                "transfers": 1,
                                "mile_type": "first",
                                "transfer_node": m['hub_id']
                            }
                            arc_counter += 1
                            A1[key].append(new_arc)
        # 1-transfer: Last-mile variant if d has bike connectivity.
        if "bike" in d['label'].lower():
            for m in all_nodes:
                if m['hub_id'] in (o['hub_id'], d['hub_id']):
                    continue
                if "bike" not in m['label'].lower():
                    continue
                key_om_pt = (o['hub_id'], m['hub_id'])
                key_md_bike = (m['hub_id'], d['hub_id'])
                if key_om_pt in pt_alts and key_md_bike in bike_alts:
                    for pt_arc in pt_alts[key_om_pt]:
                        for bike_arc in bike_alts[key_md_bike]:
                            if euclidean_distance(m['geometry'], d['geometry']) > bike_max_distance:
                                continue
                            waiting_time = random.randint(*transfer_buffer_range)
                            new_arc = {
                                "arc_id": f"a1_{arc_counter}",
                                "pt_time": pt_arc["pt_time"],
                                "bike_time": bike_arc["bike_time"],
                                "waiting_time": waiting_time,
                                "total_travel_time": pt_arc["pt_time"] + bike_arc["bike_time"] + waiting_time,
                                "transfers": 1,
                                "mile_type": "last",
                                "transfer_node": m['hub_id']
                            }
                            arc_counter += 1
                            A1[key].append(new_arc)
        # 2-transfer: First-mile variant if o has bike.
        if "bike" in o['label'].lower():
            for m in all_nodes:
                if m['hub_id'] in (o['hub_id'], d['hub_id']):
                    continue
                if "bike" not in m['label'].lower():
                    continue
                key_om_bike = (o['hub_id'], m['hub_id'])
                if key_om_bike not in bike_alts:
                    continue
                for bike_arc in bike_alts[key_om_bike]:
                    if euclidean_distance(o['geometry'], m['geometry']) > bike_max_distance:
                        continue
                    one_transfer_alts = []
                    for n in pt_nodes:
                        if n['hub_id'] in (m['hub_id'], d['hub_id']):
                            continue
                        key_mn = (m['hub_id'], n['hub_id'])
                        key_nd = (n['hub_id'], d['hub_id'])
                        if key_mn in pt_alts and key_nd in pt_alts:
                            for arc1 in pt_alts[key_mn]:
                                for arc2 in pt_alts[key_nd]:
                                    waiting_time = random.randint(*transfer_buffer_range)
                                    one_transfer_alts.append({
                                        "pt_time": arc1["pt_time"] + arc2["pt_time"],
                                        "waiting_time": waiting_time,
                                        "lines": [arc1["line"], arc2["line"]],
                                        "transfer_node": n['hub_id']
                                    })
                    for alt in one_transfer_alts:
                        new_arc = {
                            "arc_id": f"a1_{arc_counter}",
                            "pt_time": alt["pt_time"],
                            "bike_time": bike_arc["bike_time"],
                            "waiting_time": alt["waiting_time"],
                            "total_travel_time": alt["pt_time"] + bike_arc["bike_time"] + alt["waiting_time"],
                            "transfers": 2,
                            "mile_type": "first",
                            "transfer_nodes": [m['hub_id'], alt["transfer_node"]]
                        }
                        arc_counter += 1
                        A1[key].append(new_arc)
        # 2-transfer: Last-mile variant if d has bike.
        if "bike" in d['label'].lower():
            for m in all_nodes:
                if m['hub_id'] in (o['hub_id'], d['hub_id']):
                    continue
                if "bike" not in m['label'].lower():
                    continue
                key_md_bike = (m['hub_id'], d['hub_id'])
                if key_md_bike not in bike_alts:
                    continue
                for bike_arc in bike_alts[key_md_bike]:
                    if euclidean_distance(m['geometry'], d['geometry']) > bike_max_distance:
                        continue
                    one_transfer_alts = []
                    for n in pt_nodes:
                        if n['hub_id'] in (o['hub_id'], m['hub_id']):
                            continue
                        key_on = (o['hub_id'], n['hub_id'])
                        key_nm = (n['hub_id'], m['hub_id'])
                        if key_on in pt_alts and key_nm in pt_alts:
                            for arc1 in pt_alts[key_on]:
                                for arc2 in pt_alts[key_nm]:
                                    waiting_time = random.randint(*transfer_buffer_range)
                                    one_transfer_alts.append({
                                        "pt_time": arc1["pt_time"] + arc2["pt_time"],
                                        "waiting_time": waiting_time,
                                        "lines": [arc1["line"], arc2["line"]],
                                        "transfer_node": n['hub_id']
                                    })
                    for alt in one_transfer_alts:
                        new_arc = {
                            "arc_id": f"a1_{arc_counter}",
                            "pt_time": alt["pt_time"],
                            "bike_time": bike_arc["bike_time"],
                            "waiting_time": alt["waiting_time"],
                            "total_travel_time": alt["pt_time"] + bike_arc["bike_time"] + alt["waiting_time"],
                            "transfers": 2,
                            "mile_type": "last",
                            "transfer_nodes": [alt["transfer_node"], m['hub_id']]
                        }
                        arc_counter += 1
                        A1[key].append(new_arc)
    
    return A1, A2, B, od_pairs
