import gurobipy as gp
from gurobipy import GRB
import os, json, time
from Codes.CPPMTO_instance_parser_v4 import parse_json_instance


def solve_lower_level_margarita(parsed_data: dict,json_file_path, save_folder,
                      bike_price=2,dep_cost=0,        #  P̄  – €/min of bike time
                      pt_price=2,parking_fee = 2.8,            #  d̄  – flat PT fare
                      verbose=False):
    """
    Stand-alone solver for the (passenger) lower-level problem.
    Adds station–capacity constraints and reports total revenue.
    """

    """
    Builds and solves the model in your LaTeX using the JSON-like data from `parsed_data`.
    Adapt the code as needed to match exactly how you interpret each parameter.
    """

       # 1. Parse Data
    W                = parsed_data["OD_pairs"]           # list of (o,d)
    demands          = parsed_data["demands"]            # dict[(o,d)] -> Demand Q_{(o,d)}
    
    dep_cost = dep_cost

    # Arc collections
    arcs_pt_bike     = parsed_data["arcs_pt_bike"]       # dict["o_d"] -> [arc dicts]
    arcs_pt_only     = parsed_data["arcs_pt_only"]
    car_paths        = parsed_data["car_paths"]

    # Station info: bike stations from GBFS, assigned inventory and capacity
    stations_list     = parsed_data["stations_list"]
    station_capacity  = parsed_data["station_capacity"]
    station_inventory = parsed_data["station_inventory"]

    # Flows → station deltas
    delta_ia         = parsed_data["delta_ia"]

    # Minute‐/km‐based times & costs
    bike_time        = parsed_data["bike_time_min"]      # τᵃ (bike)
    pt_time          = parsed_data["pt_time_min"]        # Tᵃ (pt)
    transfers        = parsed_data["transfer_time_min"]  # Trᵃ
    parking_time     = parsed_data["parking_time_min"]   # parking search alone
    total_cost_car   = parsed_data["total_cost_car"]     # Fᵇ + depreciation
    #travel_time      = parsed_data["total_time_car_min"] # car travel + parking
    travel_time      = parsed_data["travel_time_min"] # car travel
    distance_car    = parsed_data["total_distance_km"]

    arcs_all = {}

    for (o, d) in W:
        od_key = f"{o}_{d}"
        bike_arcs = arcs_pt_bike.get(od_key, [])
        pt_arcs   = arcs_pt_only.get(od_key, [])
        arcs_all[(o, d)] = bike_arcs + pt_arcs


# Coefficients retained from Rojas et al. (2022) – magnitudes only
    ASC_PT   = -0.756          # PT alternative-specific constant (relative to BSS)
    ASC_BIKE = 0.0            # BSS ASC is the reference
    ASC_CAR  = -0.669
    
    BETA_Cost_BIKE  = 0.689      # disutility per € bike price
    BETA_Time_BIKE  = 0.108      # disutility per min of bike riding
    BETA_TR_BIKE    = 0.199      # disutility per min of bike access/egress walk
    
    BETA_Cost_PT    = 0.779      # disutility per € PT ticket
    BETA_Time_PT    = 0.101      # disutility per min of in-vehicle PT
    BETA_TR_PT      = 0.208      # disutility per min of PT access/egress walk
    
    BETA_Cost_Car   = 0.474
    BETA_Cost_park  = 0.532
    BETA_Time_Car   = 0.116
    
    # New cost dictionaries so we can weight bike- and PT-cost separately
    beta_cost_pt   = {}
    beta_cost_bike = {}
    beta_cost_car = {}
    beta_cost_park = {}

    beta_biketime = {}
    beta_pttime = {}
    beta_car_time = {}
    
    beta_transfer_time_pt = {}
    beta_transfer_time_bike = {}
    asc_bike    = {}
    asc_pt      = {}
    asc_car     = {}

    for (o,d) in W:
        od_key = f"{o}_{d}"

        for arc in arcs_pt_bike.get(od_key, []):
            a_id = arc["arc_id"]

            asc_bike[(o, d, a_id)]            = ASC_BIKE
            asc_pt[(o, d, a_id)]              = ASC_PT

            beta_biketime[(o, d, a_id)]       = BETA_Time_BIKE         # τ_bike
            beta_pttime[(o, d, a_id)]         = BETA_Time_PT           # T_PT
            beta_transfer_time_pt[(o, d, a_id)]  = BETA_TR_PT          # walk / transfers
            beta_transfer_time_bike[(o, d, a_id)]  = BETA_TR_BIKE
            beta_cost_bike[(o, d, a_id)]      = BETA_Cost_BIKE         # p_a  (bike €)
            beta_cost_pt[(o, d, a_id)]        = BETA_Cost_PT           # d_val (PT €)

        
        for arc in arcs_pt_only.get(f"{o}_{d}", []):
            arc_id = arc["arc_id"]
            asc_pt[(o,d, arc_id)] = ASC_PT
            asc_bike[(o,d, arc_id)] = 0
            beta_pttime[(o,d, arc_id)] = BETA_Time_PT
            beta_transfer_time_pt[(o,d, arc_id)] = BETA_TR_PT
            beta_cost_pt[(o,d, arc_id)] = BETA_Cost_PT



        for arc in car_paths.get(f"{o}_{d}", []):

            arc_id = arc["arc_id"]
            asc_car[(o,d, arc_id)] = ASC_CAR
            beta_car_time[(o,d, arc_id)] = BETA_Time_Car
            beta_cost_car[(o,d, arc_id)] = BETA_Cost_Car
            beta_cost_park[(o,d, arc_id)] = BETA_Cost_park



    # --------------------- model ---------------------------------------
    m = gp.Model('LowerLevel')

    # q-variables
    q = {}  # key: (o,d,arc_id)
    d_val = {}
    slack_bike={}

    for (o, d) in W:
        key = f"{o}_{d}"

        for arc in arcs_pt_bike.get(key,[]):
            aid = arc["arc_id"]
            slack_bike[(o,d, arc_id)] = m.addVar(vtype=GRB.BINARY, name=f"slack_{o}_{d}_{arc_id}")


        for arc in arcs_pt_bike.get(key, []) + arcs_pt_only.get(key, []):
            aid = arc["arc_id"]
            q[(o, d, aid)] = m.addVar(name=f"qA_{o}_{d}_{aid}")
            d_val[(o,d,aid)] = pt_price

        for arc in car_paths.get(key, []):
            bid = arc["arc_id"]
            q[(o, d, bid)] = m.addVar(name=f"qB_{o}_{d}_{bid}")




    m.update()

    # ------------------- objective  (min Σ q·V) ------------------------
    obj = gp.LinExpr()
    for (o,d) in W:

        od_key = f"{o}_{d}"
        # ---------- PT+Bike arcs ------------------------------------------------
        for arc in arcs_pt_bike.get(od_key, []):
            a  = arc["arc_id"]
            V_a = (asc_bike[(o,d,a)]
                + asc_pt[(o,d,a)]
                + beta_cost_pt[(o,d,a)] * pt_price                       # << make sure d_val is defined!
                + beta_cost_bike[(o,d,a)] * bike_price
                + beta_pttime[(o,d,a)] * pt_time[(o,d,a)]
                + beta_biketime[(o,d,a)] * bike_time.get((o,d,a))
                + beta_transfer_time_bike[(o,d,a)] * transfers[(o,d,a)])
        
            obj.add(q[(o, d, a)], V_a)


        # ---------- PT‑only arcs -------------------------------------------------
        for arc in arcs_pt_only.get(od_key, []):
            a  = arc["arc_id"]
            V_a = (
                asc_pt[(o,d,a)]
                # asc_bike = 0 for pure PT
                + beta_cost_pt[(o,d,a)] * pt_price
                 #b3 * 0                          # p = 0
                + beta_pttime[(o,d,a)] * pt_time[(o,d,a)]
                # no bicycle leg → tau = 0
                + beta_transfer_time_pt[(o,d,a)] * transfers[(o,d,a)]
            )
            obj.add(q[(o, d, a)], V_a)

        # car arcs — set ℬ
        B_arcs = car_paths.get(od_key, [])
        for arc in B_arcs:
            a = arc["arc_id"]

            F_val  = total_cost_car[(o,d, a)]      # F_b
            Tt_val = travel_time[(o,d, a)]         # Tt_b
            Tr_val  = transfers[(o,d,a)]           # car pickup time, on foot transfers
            V_b = (
                        asc_car[(o,d,a)]
                        + beta_cost_car[(o,d,a)] * (F_val - dep_cost)
                        + beta_cost_park[(o,d,a)] *  parking_fee 
                        + beta_car_time[(o,d,a)] * Tt_val
                    )
            obj.add(q[(o, d, a)], V_b)

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
    
    os.makedirs(save_folder, exist_ok=True)
    json_filename = os.path.basename(json_file_path)
    gurobi_output_name = os.path.basename(json_file_path).replace(".json", "")
    gurobi_output_path = os.path.join(save_folder, "gurobi_outputs")
    if not os.path.exists(gurobi_output_path):
        os.makedirs(gurobi_output_path)
    log_file = os.path.join(gurobi_output_path, f"gurobi_output_{gurobi_output_name}.txt")
    m.Params.LogFile = log_file
    model_file = os.path.join(gurobi_output_path, f"model_{gurobi_output_name}.lp")
    m.write(model_file)
    m.Params.NodefileStart= 2
    m.Params.NodefileDir= r"C:\b_b_gurobi"
    m.Params.Threads =4
    
    start_time = time.time()
    m.setParam("TimeLimit", 7200) # 2 hour time limit

    # -------------------------------------------------------------------
    m.optimize()
    end_time = time.time()
    solution_time = end_time - start_time

    print(f"Solution time for {gurobi_output_name}: {solution_time:.2f} seconds")
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
            price = bike_price
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
        "SolutionTime": solution_time,
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
