import gurobipy as gp
from gurobipy import GRB
import os, json, time
from Codes.CPPMTO_instance_parser_2 import parse_bilevel_instance1


def solve_lower_level(json_file_path, save_folder,
                      bike_price=0.5,        #  P̄  – €/min of bike time
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

    β1              = data["alpha_vals"]
    β2              = data["beta_vals"]
    β3              = data["theta_vals"]

    # station information (needed for the new constraint)
    stations_list   = data["stations_list"]
    station_capacity= data["station_capacity"]      # {str(i): C_i}
    station_inventory = data["station_inventory"]   # {str(i): s_i}
    delta_ia          = data["delta_ia"]            # {arc_id: {str(i): Δ_{i,a}}}

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
    for (o, d) in W:
        b1, b2, b3 = β1[(o, d)], β2[(o, d)], β3[(o, d)]
        key = f"{o}_{d}"

        # PT (+bike) and PT-only arcs   — set 𝒜
        for arc in arcs_pt_bike.get(key, []) + arcs_pt_only.get(key, []):
            aid  = arc["arc_id"]
            τ    = bike_time[(o, d, aid)]
            T_pt = pt_time[(o, d, aid)]
            Tr   = transfers[(o, d, aid)]

            V_a  = b1 * (pt_price + τ * bike_price) \
                 + b2 * (T_pt + τ) \
                 + b3 * Tr
            obj.add(q[(o, d, aid)], V_a)

        # car arcs — set ℬ
        for arc in car_paths.get(key, []):
            bid = arc["arc_id"]
            V_b = b1 * fuel_cost[(o, d, bid)] + b2 * travel_time[(o, d, bid)]
            obj.add(q[(o, d, bid)], V_b)

    m.setObjective(obj, GRB.MINIMIZE)

    # ------------- demand-satisfaction constraints ---------------------
    for (o, d) in W:
        key = f"{o}_{d}"
        flow_PT = gp.quicksum(q[(o, d, arc["arc_id"])]
                              for arc in arcs_pt_bike.get(key, []) + arcs_pt_only.get(key, []))
        flow_car = gp.quicksum(q[(o, d, arc["arc_id"])]
                               for arc in car_paths.get(key, []))
        m.addConstr(flow_PT + flow_car == demands[(o, d)],
                    name=f"demand_{o}_{d}")

    # ------------- station capacity constraints ------------------------
    #   Σ_{(o,d),a∈A1} Δ_{i,a} · q_a  ≤ C_i − s_i
    #   Σ_{(o,d),a∈A1} Δ_{i,a} · q_a  ≥ −s_i     (≡ s_i + lhs ≥ 0)
    #
    for i in stations_list:
        i_str = str(i)
        C_i   = station_capacity[i_str]
        s_i   = station_inventory[i_str]

        lhs = gp.LinExpr()
        for (o, d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):           # bike arcs only
                aid = arc["arc_id"]
                Δ = delta_ia.get(aid, {}).get(i_str, 0.0)
                if Δ:                                          # skip zeros
                    lhs.add(q[(o, d, aid)], Δ)

        m.addConstr(lhs <= C_i - s_i,          name=f"Cap_{i_str}_upper")
        m.addConstr(lhs + s_i >= 0,            name=f"Cap_{i_str}_lower")

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
            price = pt_price + τ * bike_price
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
            revenue += price * q_val
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
