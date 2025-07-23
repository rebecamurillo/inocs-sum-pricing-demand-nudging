import gurobipy as gp
from gurobipy import GRB
import os, json, time
from Codes.CPPMTO_instance_parser_2 import parse_bilevel_instance1


def solve_lower_level(json_file_path, save_folder,
                      bike_price=2,        #  P̄  – €/min of bike time
                      pt_price=4,            #  d̄  – flat PT fare
                      verbose=False):
    """
    Stand-alone solver for the (passenger) lower-level problem.
    Adds station–capacity constraints and reports total revenue.
    """

    # ------------------------- data ------------------------------------
    data = parse_bilevel_instance1(json_file_path)

    W               = data["OD_pairs"]
    arcs_pt_bike    = data["arcs_pt_bike"]
    arcs_pt_only    = data["arcs_pt_only"]
    car_paths       = data["car_paths"]
    demands         = data["demands"]

    bike_time       = data["bike_time"]
    pt_time         = data["pt_time"]
    transfers       = data["transfers"]
    fuel_cost       = data["fuel_cost"]
    travel_time     = data["travel_time"]
    d_val           = pt_price
    beta_1 = {}
    beta_2 = {}
    beta_3 = {}
    beta_4 = {}
    beta_5 = {}
    asc_pt = {}
    asc_bike = {}
    for (o,d) in W:
        beta_1[(o,d)] = 0.093   #main cost
        beta_2[(o,d)] = 0.034   #main time
        beta_3[(o,d)] = 0.425   #egress cost
        beta_4[(o,d)] = 0.039   #egress time
        beta_5[(o,d)] = 0       #transfer time
        for arc in arcs_pt_bike.get(f"{o}_{d}", []):
            arc_id = arc["arc_id"]
            asc_bike[(o,d, arc_id)] = 0.856
            asc_pt[(o,d, arc_id)] = 0

        for arc in arcs_pt_only.get(f"{o}_{d}", []):
            arc_id = arc["arc_id"]
            asc_pt[(o,d, arc_id)] = -0.683
            asc_bike[(o,d, arc_id)] = 0


    # station information (needed for the new constraint)
    stations_list       = data["stations_list"]
    station_capacity    = data["station_capacity"]      # {str(i): C_i}
    station_inventory   = data["station_inventory"]   # {str(i): s_i}
    delta_ia            = data["delta_ia"]            # {arc_id: {str(i): Δ_{i,a}}}

    # --------------------- model ---------------------------------------
    m = gp.Model('LowerLevel')

    # q-variables
    q = {}  # key: (o,d,arc_id)
    for (o, d) in W:
        key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(key, []) + arcs_pt_only.get(key, []):
            aid = arc["arc_id"]
            q[(o, d, aid)] = m.addVar(name=f"qA_{o}_{d}_{aid}")
        for arc in car_paths.get(key, []):
            bid = arc["arc_id"]
            q[(o, d, bid)] = m.addVar(name=f"qB_{o}_{d}_{bid}")

    m.update()

    # ------------------- objective  (min Σ q·V) ------------------------
    obj = gp.LinExpr()
    for (o,d) in W:
        b1 = beta_1[(o,d)]
        b2 = beta_2[(o,d)]
        b3 = beta_3[(o,d)]
        b4 = beta_4[(o,d)]
        b5 = beta_5[(o,d)]

        od_key = f"{o}_{d}"
        A_arcs = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])
        for arc in A_arcs:
            arc_id = arc["arc_id"]
            asc_pt_val = asc_pt[(o,d, arc_id)]
            asc_bike_val = asc_bike[(o,d, arc_id)]

            # Retrieve parameters from your dictionaries
            #d_val   = fixed_pt_price[(o,d,arc_id)]  # d_a
            tau_val = bike_time[(o,d,arc_id)]       # τ_a
            Tt_val  = pt_time[(o,d,arc_id)]         # Tt_a
            Tr_val  = transfers[(o,d,arc_id)]       # Tr_a

            # p_a is p[(o,d,arc_id)], gamma is gamma_[(o,d)]

            # Directly build the right-hand side as a Python expression
            V_a = (  asc_bike_val
                        + asc_pt_val
                        + b1 * d_val
                        + b3 * tau_val * bike_price
                        + b2 * Tt_val
                        + b4 * tau_val
                        + b5 * Tr_val)
            obj.add(q[(o, d, arc_id)], V_a)

        # car arcs — set ℬ
        B_arcs = car_paths.get(od_key, [])
        for arc in B_arcs:
            arc_id = arc["arc_id"]

            F_val  = fuel_cost[(o,d, arc_id)]     # F_b
            Tt_val = travel_time[(o,d, arc_id)]   # Tt_b

            V_b = b1 * F_val + b2 * Tt_val

            obj.add(q[(o, d, arc_id)], V_b)

    m.setObjective(obj, GRB.MINIMIZE)

    # ------------- demand-satisfaction constraints ---------------------
    # 5) sum_{a in A^(o,d)} q_a^(o,d) + sum_{b in B^(o,d)} q_b^(o,d) = Q_{(o,d)}
    for (o,d) in W:
        od_key = f"{o}_{d}"
        arcs_all = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])

        lhs_expr = gp.quicksum(q[(o,d, arc["arc_id"])] for arc in arcs_all) \
                    + gp.quicksum(q[(o,d, arc["arc_id"])] for arc in car_paths.get(od_key, []))
        m.addConstr(lhs_expr == demands[(o,d)], name=f"demand_{o}_{d}")

    # ------------- station capacity constraints ------------------------
    # 4) Station capacity: sum of q_a * delta_ia <= C_i - s_i
    for i in stations_list:
        i_str = str(i)  # station_capacity keys are strings
        capacity_i = station_capacity[i_str]
        inventory_i= station_inventory[i_str]
        lhs_expr = gp.LinExpr()
        # sum over (o,d) in W, arcs in A1 (since A2 or B typically doesn't use bikes, but if they do, adapt)
        for (o,d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):
                arc_id = arc["arc_id"]
                delta_val = delta_ia.get(arc_id, {}).get(i_str, 0.0)
                lhs_expr.add(q[(o,d,arc_id)], delta_val)
        m.addConstr(
            lhs_expr <= capacity_i - inventory_i,
            name=f"StationCap_{i}")
        m.addConstr(lhs_expr + inventory_i >= 0,
                        name=f"StationCap_nonneg_{i}")

    # -------------------------------------------------------------------
    m.optimize()

# ----------------- post-processing ---------------------------------
    ε = 1e-6

    pt_only_flows  = []     # PT without bike leg
    pt_bike_flows  = []     # PT with bike first/last mile
    car_flows      = []     # pure car
    revenue = 0.0

    for (o, d) in W:
        key = f"{o}_{d}"

        # ---- PT + Bike arcs ------------------------------------------
        for arc in arcs_pt_bike.get(key, []):
            aid   = arc["arc_id"]
            q_val = q[(o, d, aid)].X
            if q_val <= ε:
                continue
            τ     = bike_time[(o, d, aid)]
            price = τ * bike_price
            revenue += price * q_val
            pt_bike_flows.append(
                {"o": o, "d": d, "arc_id": aid,
                 "q": q_val, "price": price,
                 "type": "PT+Bike"}
            )

        # ---- PT-only arcs --------------------------------------------
        for arc in arcs_pt_only.get(key, []):
            aid   = arc["arc_id"]
            q_val = q[(o, d, aid)].X
            if q_val <= ε:
                continue
            price = pt_price                         # no bike fare part
            pt_only_flows.append(
                {"o": o, "d": d, "arc_id": aid,
                 "q": q_val, "price": price,
                 "type": "PT"}
            )

        # ---- Car arcs -------------------------------------------------
        for arc in car_paths.get(key, []):
            bid   = arc["arc_id"]
            q_val = q[(o, d, bid)].X
            if q_val <= ε:
                continue
            car_flows.append(
                {"o": o, "d": d, "arc_id": bid,
                 "q": q_val, "price": 0.0,
                 "type": "Car"}
            )

    # --------- optional overall PT total ------------------------------
    total_pt_flow  = sum(f["q"] for f in pt_only_flows + pt_bike_flows)
    total_car_flow = sum(f["q"] for f in car_flows)

    # ---------------------- save ---------------------------------------
    result = {
        "objective": m.ObjVal,
        "SolutionTime": m.Runtime,
        "revenue": revenue,
        "flow_totals": {
            "PT+Bike" : sum(f["q"] for f in pt_bike_flows),
            "PT"      : sum(f["q"] for f in pt_only_flows),
            "Car"     : total_car_flow,
            "PT_all"  : total_pt_flow          # handy aggregate
        }
    }

    os.makedirs(save_folder, exist_ok=True)
    out_name = os.path.basename(json_file_path).replace(".json",
                                                        "_LL_solution.json")
    out_path = os.path.join(save_folder, out_name)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    if verbose:
        print(f"✓ lower-level solution saved to {out_path}")

    return result
