import json
import math
import os

def parse_json_instance(json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        inst = json.load(f)

    OD_raw = inst['OD_pairs']
    W = [(od['origin'], od['destination']) for od in OD_raw]
    demands = {(od['origin'], od['destination']): od['demand'] for od in OD_raw}
    euclid_m ={(od['origin'], od['destination']): od['euclid_dist'] for od in OD_raw}
    euclid_km = {od: m / 1000.0 for od, m in euclid_m.items()}

    arcs_pt_bike = inst['arcs_pt_bike']
    arcs_pt_only = inst['arcs_pt_only']
    car_paths    = inst['car_paths']
    delta_ia     = inst['delta_ia']

    # --- distance-elasticity factors (kept as-is) ---
    ref_dist = 39
    lam_td = -0.115
    lam_cd =  0.221
    xi_TD = {od: (dkm / ref_dist) ** lam_td for od, dkm in euclid_km.items()}
    xi_CD = {od: (dkm / ref_dist) ** lam_cd for od, dkm in euclid_km.items()}

    # --- station data (drop unused stations) ---
    raw_station_list     = inst['bike_stations']['station_list']
    station_capacity  = {str(k): v for k, v in inst['bike_stations']['station_capacity'].items()}
    station_inventory = {str(k): v for k, v in inst['bike_stations']['station_inventory'].items()}

    stations_in_delta = {sid for deltas in delta_ia.values() for sid in deltas.keys()}
    stations_list = sorted(stations_in_delta)

    dropped_stations = set(map(str, raw_station_list)) - stations_in_delta
    if dropped_stations:
        print(f"⚠️ Dropped {len(dropped_stations)} stations not used in delta_ia: {sorted(dropped_stations)}")

    station_capacity  = {k: v for k, v in station_capacity.items()  if k in stations_in_delta}
    station_inventory = {k: v for k, v in station_inventory.items() if k in stations_in_delta}

    # --- containers ---
    bike_time_min           = {}
    pt_time_min             = {}
    transfer_time_min       = {}
    total_distance_km       = {}
    distance_km             = {}
    parking_time_min        = {}
    total_cost_car          = {}
    travel_time_min         = {}
    travel_parking_time_min = {}

    # NEW: number of bike legs for each A1 alternative
    k_bike_legs             = {}   # dict keyed by (o,d,aid) with values in {0,1,2}

    def split_key(key):
        o, d = key.split('_')
        return int(o), int(d)

    # --- PT+Bike arcs (A1) ---
    for key, arcs in arcs_pt_bike.items():
        o, d = split_key(key)
        for arc in arcs:
            aid = arc['arc_id']

            # count BICYCLE legs (preferred source)
            bike_legs = sum(1 for leg in arc.get('legs', []) if leg.get('mode') == 'BICYCLE')

            # fallback: infer from delta_ia if legs not annotated
            if bike_legs == 0:
                nonzero = sum(1 for v in delta_ia.get(aid, {}).values() if abs(v) > 0)
                # each bike leg touches two stations (dep+arr)
                inferred = nonzero // 2
                # clip to {0,1,2}
                bike_legs = min(2, max(0, inferred))

            k_bike_legs[(o, d, aid)] = int(bike_legs)

            # times/distances
            bike_time = sum(leg.get('duration_min', 0.0)
                            for leg in arc.get('legs', []) if leg.get('mode') == 'BICYCLE')
            bike_time_min[(o, d, aid)] = math.ceil(bike_time)

            pt_time_sum = sum(
                leg.get('duration_min', 0.0)
                for leg in arc.get('legs', [])
                if leg.get('mode') in ('BUS', 'TRAM')
            )
            pt_time_min[(o, d, aid)] = math.ceil(pt_time_sum)
            transfer_time_min[(o, d, aid)] = math.ceil(arc.get('total_transfer_time_min', 0.0))
            total_distance_km[(o, d, aid)] = arc.get('total_distance_km', 0.0)

            # optional: one bike-leg distance if present
            for leg in arc.get('legs', []):
                if leg.get('mode') == 'BICYCLE':
                    distance_km[(o, d, aid)] = leg.get('distance_km', 0.0)
                    break

    # --- PT-only arcs (A2) ---
    for key, arcs in arcs_pt_only.items():
        o, d = split_key(key)
        for arc in arcs:
            aid = arc['arc_id']
            pt_time_min[(o, d, aid)]       = math.ceil(arc.get('total_travel_time_min', 0.0))
            transfer_time_min[(o, d, aid)] = math.ceil(arc.get('total_transfer_time_min', 0.0))
            total_distance_km[(o, d, aid)] = arc.get('total_distance_km', 0.0)
            # ensure k=0 for PT-only (never used, but safe)
            k_bike_legs[(o, d, aid)] = 0

    # --- Car paths ---
    for key, arcs in car_paths.items():
        o, d = split_key(key)
        for arc in arcs:
            aid = arc['arc_id']
            travel_time_min[(o, d, aid)]   = math.ceil(arc.get('total_travel_time_min', 0.0))
            transfer_time_min[(o, d, aid)] = math.ceil(arc.get('total_transfer_time_min', 0.0))
            parking_time_min[(o, d, aid)]  = math.ceil(arc.get('parking_time_min', 0.0))
            travel_parking_time_min[(o, d, aid)] = math.ceil(arc.get('total_travel_and_parking_time_min', 0.0))
            total_distance_km[(o, d, aid)] = arc.get('total_distance_km', 0.0)
            total_cost_car[(o, d, aid)]    = arc.get('total_travel_cost', 0.0)
            # ensure k=0 for car arcs
            k_bike_legs[(o, d, aid)] = 0

    return {
        'OD_pairs':            W,
        'demands':             demands,
        'arcs_pt_bike':        arcs_pt_bike,
        'arcs_pt_only':        arcs_pt_only,
        'car_paths':           car_paths,
        'stations_list':       stations_list,
        'station_capacity':    station_capacity,
        'station_inventory':   station_inventory,
        'delta_ia':            delta_ia,
        'bike_time_min':       bike_time_min,
        'pt_time_min':         pt_time_min,
        'travel_time_min':     travel_time_min,
        'transfer_time_min':   transfer_time_min,
        'total_distance_km':   total_distance_km,
        'distance_km':         distance_km,
        'parking_time_min':    parking_time_min,
        'total_cost_car':      total_cost_car,
        'total_time_car_min':  travel_parking_time_min,
        'xi_TD':               xi_TD,      # {(o,d): ξ_TD}
        'xi_CD':               xi_CD,      # {(o,d): ξ_CD}
        'k_bike_legs':         k_bike_legs # NEW
    }
