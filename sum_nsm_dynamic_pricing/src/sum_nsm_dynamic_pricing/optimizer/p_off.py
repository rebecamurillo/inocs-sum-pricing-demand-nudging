# Codes/p_off_utils.py
import json
from pathlib import Path
import os
def compute_p_off(parsed_data, *, P_bar=1, P_up=4, pt_price=2, parking_fee=2.8, dep_cost=0.0, tol=0.5,
                  ASC_PT=-0.756, ASC_BIKE=0.0, ASC_CAR=-0.669,
                  BETA_Cost_BIKE=0.689, BETA_Time_BIKE=0.108, BETA_TR_BIKE=0.199,
                  BETA_Cost_PT=0.779,  BETA_Time_PT=0.101,  BETA_TR_PT=0.208,
                  BETA_Cost_Car=0.474, BETA_Cost_park=0.532, BETA_Time_Car=0.116):
    """
    Returns:
      p_off: {(o,d,a): float}  — tight per-arc upper bound on p (>= P_bar+tol)
      disable: set((o,d,a))    — arcs whose utility can't be deteriorated by price (k=0 etc.)
      global_p_off: float      — max of p_off (handy fallback)
      skipped_ods: set((o,d))  — ODs with no competitor (car/PT-only)
    """
    W            = parsed_data['OD_pairs']
    arcs_a1      = parsed_data['arcs_pt_bike']
    arcs_a2      = parsed_data['arcs_pt_only']
    car_paths    = parsed_data['car_paths']
    pt_time      = parsed_data['pt_time_min']
    bike_time    = parsed_data['bike_time_min']
    transfers    = parsed_data['transfer_time_min']
    travel_time  = parsed_data['travel_time_min']
    total_cost_c = parsed_data['total_cost_car']
    k_bike_legs  = parsed_data['k_bike_legs']

    def V_car(o,d,a):
        F  = total_cost_c[(o,d,a)]
        Tt = travel_time[(o,d,a)]
        return (ASC_CAR + BETA_Cost_Car*(F - dep_cost) + BETA_Cost_park*parking_fee + BETA_Time_Car*Tt)

    def V_pt(o,d,a):
        return (ASC_PT + BETA_Cost_PT*pt_price + BETA_Time_PT*pt_time[(o,d,a)] + BETA_TR_PT*transfers[(o,d,a)])

    def C_a1(o,d,a):
        # utility part of A1 independent of p
        return (ASC_PT + ASC_BIKE
                + BETA_Cost_PT*pt_price
                + BETA_Time_PT*pt_time[(o,d,a)]
                + BETA_Time_BIKE*bike_time.get((o,d,a), 0.0)
                + BETA_TR_BIKE*transfers[(o,d,a)])

    p_off = {}
    disable = set()
    skipped_ods = set()
    global_max = P_up

    for (o,d) in W:
        key = f"{o}_{d}"
        # best (lowest) competitor disutility
        best_comp = float('inf')
        #best_comp = 0
        found = False
        for arc in car_paths.get(key, []):
            best_comp = min(best_comp, V_car(o,d,arc['arc_id'])); found = True
        for arc in arcs_a2.get(key, []):
            best_comp = min(best_comp, V_pt(o,d,arc['arc_id'])); found = True
        if not found:
            skipped_ods.add((o,d))
            continue

        for arc in arcs_a1.get(key, []):
            a  = arc['arc_id']
            k  = int(k_bike_legs.get((o,d,a), 1))
            α  = BETA_Cost_BIKE * k
            if α <= 0:
                disable.add((o,d,a))  # price won’t deteriorate utility
                continue
            C = C_a1(o,d,a)
            p_needed = (best_comp - C) / α
            off = max(P_bar, p_needed) + tol
            p_off[(o,d,a)] = off
            global_max = max(P_up, off)

    return {'p_off': p_off, 'disable': disable, 'global_p_off': global_max, 'skipped_ods': skipped_ods}

def save_p_off_json(p_off_data, instance_path: str, suffix="_p_off.json"):
    os.makedirs(instance_path, exist_ok=True)
    out = Path(instance_path).with_name(Path(instance_path).stem + suffix)
    # Convert tuple keys to strings for JSON
    po = {"{}-{}-{}".format(o,d,a): v for (o,d,a), v in p_off_data['p_off'].items()}
    data = {
        "p_off": po,
        "disable": ["{}-{}-{}".format(o,d,a) for (o,d,a) in p_off_data['disable']],
        "global_p_off": p_off_data['global_p_off'],
        "skipped_ods": ["{}-{}".format(o,d) for (o,d) in p_off_data['skipped_ods']],
    }
    out.write_text(json.dumps(data, indent=2))
    return str(out)

def load_p_off_json(p_off_path: str):
    p = Path(p_off_path)
    obj = json.loads(p.read_text())
    def parse_tup3(s):
        o,d,a = s.split("-")
        return (int(o), int(d), a)
    def parse_tup2(s):
        o,d = s.split("-")
        return (int(o), int(d))
    p_off = {parse_tup3(k): v for k, v in obj["p_off"].items()}
    disable = set(parse_tup3(s) for s in obj["disable"])
    skipped = set(parse_tup2(s) for s in obj["skipped_ods"])
    return {"p_off": p_off, "disable": disable, "global_p_off": obj["global_p_off"], "skipped_ods": skipped}
