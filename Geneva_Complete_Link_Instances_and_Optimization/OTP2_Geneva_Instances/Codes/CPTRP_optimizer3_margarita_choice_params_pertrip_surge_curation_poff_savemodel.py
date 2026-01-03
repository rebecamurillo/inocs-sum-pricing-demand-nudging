import gc
import gurobipy as gp
from gurobipy import GRB
import os
import json
import time
import numbers
from collections.abc import Mapping
import random as rand
from save_solution_files_safely import save_solution_files_safely
import math

from pathlib import Path

def find_existing_base_model(base_model_folder: str, instance_path: str, price_lb, capacity=None, inv_tag="invDefault"):
    gurobi_output_name = Path(instance_path).stem
    gurobi_output_path = Path(base_model_folder) / "gurobi_outputs"
    # match your naming convention exactly:
    base_file = gurobi_output_path / f"model_{gurobi_output_name}_{price_lb}_{capacity}_{inv_tag}_BASE.mps"
    if base_file.exists():
        return str(base_file)
    # also allow compressed
    base_file_gz = Path(str(base_file) + ".gz")
    if base_file_gz.exists():
        return str(base_file_gz)
    return None


def build_and_save_base_model(
    parsed_data,
    *,
    json_file_path,
    save_folder,
    max_displayed_alternatives=10,
    mult_A1=1,
    capacity=None,
    inventory_level=None,
    dep_cost=0,
    cost_bike=0.6,
    parking_fee=2.8,
    P_bar=0.6,
    pt_price=2,
    theta=0.5,
    ridership_weight=8,
    p_off_map=None,
    disable_set=None,
    global_p_off=None,
):
    """
    Build (but do NOT solve) the full MIP model.
    Returns a dict 'bundle' with the model + all structures needed for solving
    and extracting solutions later.
    """

    # ---------- 1. Parse data ----------
    W                = parsed_data["OD_pairs"]
    demands          = parsed_data["demands"]
    arcs_pt_bike     = parsed_data["arcs_pt_bike"]
    arcs_pt_only     = parsed_data["arcs_pt_only"]
    car_paths        = parsed_data["car_paths"]
    k_bike_legs      = parsed_data["k_bike_legs"]

    stations_list     = parsed_data["stations_list"]
    station_capacity  = parsed_data["station_capacity"]
    station_inventory = parsed_data["station_inventory"]

    # capacity override
    if capacity is None:
        station_capacity  = parsed_data["station_capacity"]
    elif isinstance(capacity, Mapping):
        station_capacity = {str(k): int(v) for k, v in capacity.items()}
    elif isinstance(capacity, numbers.Number):
        station_capacity = {str(i): int(capacity) for i in stations_list}
    else:
        raise TypeError("`capacity` must be None, a scalar, or a dict-like object")

    # inventory override
    if inventory_level is not None:
        low, high = inventory_level
        station_inventory = {
            sid: int(round(rand.uniform(low, high) * station_capacity[sid]))
            for sid in station_capacity
        }
        inv_tag = f"{low}_{high}"
    else:
        station_inventory = parsed_data["station_inventory"]
        inv_tag = "invDefault"

    delta_ia       = parsed_data["delta_ia"]
    bike_time      = parsed_data["bike_time_min"]
    pt_time        = parsed_data["pt_time_min"]
    transfers      = parsed_data["transfer_time_min"]
    parking_time   = parsed_data["parking_time_min"]
    total_cost_car = parsed_data["total_cost_car"]
    travel_time    = parsed_data["travel_time_min"]

    # ---------- 2. Utility parameters ----------
    ASC_PT   = -0.756
    ASC_BIKE = 0.0
    ASC_CAR  = -0.669

    BETA_Cost_BIKE  = 0.689
    BETA_Time_BIKE  = 0.108
    BETA_TR_BIKE    = 0.199

    BETA_Cost_PT    = 0.779
    BETA_Time_PT    = 0.101
    BETA_TR_PT      = 0.208

    BETA_Cost_Car   = 0.474
    BETA_Cost_park  = 0.532
    BETA_Time_Car   = 0.116

    beta_cost_pt   = {}
    beta_cost_bike = {}
    beta_cost_car  = {}
    beta_cost_park = {}

    beta_biketime          = {}
    beta_pttime            = {}
    beta_car_time          = {}
    beta_transfer_time_pt  = {}
    beta_transfer_time_bike= {}
    asc_bike    = {}
    asc_pt      = {}
    asc_car     = {}

    for (o, d) in W:
        od_key = f"{o}_{d}"

        # PT+Bike arcs
        for arc in arcs_pt_bike.get(od_key, []):
            a_id = arc["arc_id"]

            asc_bike[(o, d, a_id)] = ASC_BIKE
            asc_pt[(o, d, a_id)]   = ASC_PT

            beta_biketime[(o, d, a_id)]          = BETA_Time_BIKE
            beta_pttime[(o, d, a_id)]            = BETA_Time_PT
            beta_transfer_time_pt[(o, d, a_id)]  = BETA_TR_PT
            beta_transfer_time_bike[(o, d, a_id)] = BETA_TR_BIKE
            beta_cost_bike[(o, d, a_id)]         = BETA_Cost_BIKE
            beta_cost_pt[(o, d, a_id)]           = BETA_Cost_PT

        # PT-only arcs
        for arc in arcs_pt_only.get(od_key, []):
            a_id = arc["arc_id"]
            asc_pt[(o, d, a_id)] = ASC_PT
            asc_bike[(o, d, a_id)] = 0.0
            beta_pttime[(o, d, a_id)] = BETA_Time_PT
            beta_transfer_time_pt[(o, d, a_id)] = BETA_TR_PT
            beta_cost_pt[(o, d, a_id)] = BETA_Cost_PT

        # Car arcs
        for arc in car_paths.get(od_key, []):
            a_id = arc["arc_id"]
            asc_car[(o, d, a_id)]      = ASC_CAR
            beta_car_time[(o, d, a_id)] = BETA_Time_Car
            beta_cost_car[(o, d, a_id)] = BETA_Cost_Car
            beta_cost_park[(o, d, a_id)] = BETA_Cost_park

    # ---------- 3. Create model & variables ----------
    model = gp.Model("Bilevel_Model")

    nu = {}
    p  = {}
    q_ = {}
    z_ = {}
    gamma_ = {}
    d_val = {}
    bike_cost = {}
    Pbar = {}
    M_poff = {}
    w = {}

    for (o, d) in W:
        gamma_[(o, d)] = model.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY,
                                      vtype=GRB.CONTINUOUS, name=f"gamma_{o}_{d}")
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        B_arcs  = car_paths.get(od_key, [])

        # PT+Bike arcs
        for arc in A1_arcs:
            arc_id = arc["arc_id"]
            p[(o, d, arc_id)]  = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS,
                                              name=f"p_{o}_{d}_{arc_id}")
            z_[(o, d, arc_id)] = model.addVar(lb=-GRB.INFINITY, vtype=GRB.CONTINUOUS,
                                              name=f"z_{o}_{d}_{arc_id}")
            bike_cost[(o, d, arc_id)] = cost_bike
            Pbar[(o, d, arc_id)] = P_bar

            if p_off_map and (o, d, arc_id) in p_off_map:
                M_poff[(o, d, arc_id)] = float(p_off_map[(o, d, arc_id)])
            else:
                M_poff[(o, d, arc_id)] = float(global_p_off if global_p_off is not None else 4.0)

            w[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS,
                                             name=f"w_{o}_{d}_{arc_id}")

        # PT+Bike & PT-only (shared nu,q,d_val)
        for arc in A1_arcs + A2_arcs:
            arc_id = arc["arc_id"]
            nu[(o, d, arc_id)] = model.addVar(vtype=GRB.BINARY,
                                              name=f"nu_{o}_{d}_{arc_id}")
            q_[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS,
                                              name=f"q_{o}_{d}_{arc_id}")
            d_val[(o, d, arc_id)] = pt_price

        # Car arcs
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            q_[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS,
                                              name=f"q_{o}_{d}_{arc_id}")

    model.update()

    # ---------- 4. Constraints ----------

    # 4.1 Max displayed alternatives (L) per OD
    # RHS will be updated later, but we set an initial value here.
    for (o, d) in W:
        od_key  = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        lhs = gp.quicksum(nu[(o, d, arc["arc_id"])] for arc in A1_arcs + A2_arcs)
        model.addConstr(lhs <= max_displayed_alternatives, name=f"MaxDisp_{o}_{d}")

    # 4.2 On/off price bounds
    for (o, d) in W:
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            model.addConstr(
                p[(o, d, a)] >= Pbar[(o, d, a)] * nu[(o, d, a)] +
                                M_poff[(o, d, a)] * (1 - nu[(o, d, a)]),
                name=f"p_onoff_lb_{o}_{d}_{a}"
            )
            model.addConstr(
                p[(o, d, a)] <= M_poff[(o, d, a)],
                name=f"p_onoff_ub_{o}_{d}_{a}"
            )

    # 4.3 q <= Q * nu for A arcs
    for (o, d) in W:
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        for arc in A1_arcs + A2_arcs:
            a = arc["arc_id"]
            model.addConstr(
                q_[(o, d, a)] <= demands[(o, d)] * nu[(o, d, a)],
                name=f"q_le_{o}_{d}_{a}"
            )

    # 4.4 Station capacity & nonnegativity
    for i in stations_list:
        i_str = str(i)
        capacity_i = station_capacity[i_str]
        inventory_i= station_inventory[i_str]
        lhs_expr = gp.LinExpr()
        for (o, d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):
                a = arc["arc_id"]
                delta_val = delta_ia.get(a, {}).get(i_str, 0.0)
                if delta_val:
                    lhs_expr.add(q_[(o, d, a)], delta_val)

        model.addConstr(lhs_expr <= capacity_i - inventory_i, name=f"StationCap_{i}")
        model.addConstr(lhs_expr  >= - inventory_i, name=f"StationCap_nonneg_{i}")

    # 4.5 Demand conservation
    for (o, d) in W:
        od_key  = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        B_arcs  = car_paths.get(od_key, [])

        lhs_expr = gp.quicksum(q_[(o, d, arc["arc_id"])] for arc in A1_arcs + A2_arcs) \
                   + gp.quicksum(q_[(o, d, arc["arc_id"])] for arc in B_arcs)
        model.addConstr(lhs_expr == demands[(o, d)], name=f"demand_{o}_{d}")

    # 4.6 gamma <= V for all arcs
    for (o, d) in W:
        od_key = f"{o}_{d}"

        # PT+Bike
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            rhs = (asc_bike[(o, d, a)] + asc_pt[(o, d, a)]
                   + beta_cost_pt[(o, d, a)] * d_val[(o, d, a)]
                   + beta_cost_bike[(o, d, a)] * k_bike_legs[(o, d, a)] * p[(o, d, a)]
                   + beta_pttime[(o, d, a)] * pt_time[(o, d, a)]
                   + beta_biketime[(o, d, a)] * bike_time.get((o, d, a), 0.0)
                   + beta_transfer_time_bike[(o, d, a)] * transfers[(o, d, a)])
            model.addConstr(gamma_[(o, d)] <= rhs, name=f"gammaA_{o}_{d}_{a}")

        # PT-only
        for arc in arcs_pt_only.get(od_key, []):
            a = arc["arc_id"]
            rhs = (asc_pt[(o, d, a)]
                   + beta_cost_pt[(o, d, a)] * d_val[(o, d, a)]
                   + beta_pttime[(o, d, a)] * pt_time[(o, d, a)]
                   + beta_transfer_time_pt[(o, d, a)] * transfers[(o, d, a)])
            model.addConstr(gamma_[(o, d)] <= rhs, name=f"gammaA_{o}_{d}_{a}_ptonly")

        # Car
        for arc in car_paths.get(od_key, []):
            a = arc["arc_id"]
            F_val  = total_cost_car[(o, d, a)]
            Tt_val = travel_time[(o, d, a)]
            rhs = (asc_car[(o, d, a)]
                   + beta_cost_car[(o, d, a)] * (F_val - dep_cost)
                   + beta_cost_park[(o, d, a)] * parking_fee
                   + beta_car_time[(o, d, a)] * Tt_val)
            model.addConstr(gamma_[(o, d)] <= rhs, name=f"gammaB_{o}_{d}_{a}_car")

    # 4.7 Strong duality
    lhs_expr = gp.LinExpr()
    rhs_expr = gp.quicksum(demands[(o, d)] * gamma_[(o, d)] for (o, d) in W)

    for (o, d) in W:
        od_key = f"{o}_{d}"
        B_arcs = car_paths.get(od_key, [])

        # PT+Bike
        for arc in arcs_pt_bike.get(od_key, []):
            a       = arc["arc_id"]
            q_var   = q_[(o, d, a)]
            z_var   = z_[(o, d, a)]
            d_pt    = d_val[(o, d, a)]
            tau_val = bike_time.get((o, d, a), 0.0)
            Tt_val  = pt_time[(o, d, a)]
            Tr_val  = transfers[(o, d, a)]
            asc_val = asc_bike[(o, d, a)] + asc_pt[(o, d, a)]

            lhs_expr.add(q_var, beta_cost_pt[(o, d, a)] * d_pt)
            lhs_expr.add(z_var, beta_cost_bike[(o, d, a)] * k_bike_legs[(o, d, a)])
            lhs_expr.add(q_var, beta_pttime[(o, d, a)] * Tt_val)
            lhs_expr.add(q_var, beta_biketime[(o, d, a)] * tau_val)
            lhs_expr.add(q_var, beta_transfer_time_bike[(o, d, a)] * Tr_val)
            lhs_expr.add(q_var, asc_val)

        # PT-only
        for arc in arcs_pt_only.get(od_key, []):
            a       = arc["arc_id"]
            q_var   = q_[(o, d, a)]
            d_pt    = d_val[(o, d, a)]
            Tt_val  = pt_time[(o, d, a)]
            Tr_val  = transfers[(o, d, a)]
            asc_val = asc_pt[(o, d, a)]

            lhs_expr.add(q_var, beta_cost_pt[(o, d, a)] * d_pt)
            lhs_expr.add(q_var, beta_pttime[(o, d, a)] * Tt_val)
            lhs_expr.add(q_var, beta_transfer_time_pt[(o, d, a)] * Tr_val)
            lhs_expr.add(q_var, asc_val)

        # Car
        for barc in B_arcs:
            a      = barc["arc_id"]
            q_var  = q_[(o, d, a)]
            F_val  = total_cost_car[(o, d, a)]
            Ttb_val= travel_time[(o, d, a)]
            asc_val= asc_car[(o, d, a)]

            lhs_expr.add(q_var, beta_cost_car[(o, d, a)] * (F_val - dep_cost))
            lhs_expr.add(q_var, parking_fee * beta_cost_park[(o, d, a)])
            lhs_expr.add(q_var, beta_car_time[(o, d, a)] * Ttb_val)
            lhs_expr.add(q_var, asc_val)

    model.addConstr(lhs_expr == rhs_expr, name="StrongDuality")

    # 4.8 w = q * nu linearization
    for (o, d) in W:
        Qod = demands[(o, d)]
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            model.addConstr(w[(o, d, a)] <= q_[(o, d, a)], name=f"w_le_q_{o}_{d}_{a}")
            model.addConstr(w[(o, d, a)] <= Qod * nu[(o, d, a)],
                            name=f"w_le_Qnu_{o}_{d}_{a}")
            model.addConstr(w[(o, d, a)] >= q_[(o, d, a)] - Qod * (1 - nu[(o, d, a)]),
                            name=f"w_ge_q_minus_Q1mnu_{o}_{d}_{a}")

    # 4.9 McCormick for z = p*q
    for (o, d) in W:
        Qod = demands[(o, d)]
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]

            # pL(ν) q  = Pbar*w + M*(q - w)
            model.addConstr(
                z_[(o, d, a)] >= Pbar[(o, d, a)] * w[(o, d, a)] +
                                M_poff[(o, d, a)] * (q_[(o, d, a)] - w[(o, d, a)]),
                name=f"z_ge_pLq_{o}_{d}_{a}"
            )
            # pU(ν) q  = M q
            model.addConstr(
                z_[(o, d, a)] <= M_poff[(o, d, a)] * q_[(o, d, a)],
                name=f"z_le_pUq_{o}_{d}_{a}"
            )
            model.addConstr(
                z_[(o, d, a)] >= M_poff[(o, d, a)] * q_[(o, d, a)] +
                                Qod * p[(o, d, a)] -
                                M_poff[(o, d, a)] * Qod,
                name=f"z_ge_pUq_plus_Qp_minus_pUQ_{o}_{d}_{a}"
            )
            model.addConstr(
                z_[(o, d, a)] <=
                (Pbar[(o, d, a)] * w[(o, d, a)] +
                 M_poff[(o, d, a)] * (q_[(o, d, a)] - w[(o, d, a)])) +
                Qod * p[(o, d, a)] -
                (Pbar[(o, d, a)] * Qod * nu[(o, d, a)] +
                 M_poff[(o, d, a)] * Qod * (1 - nu[(o, d, a)])),
                name=f"z_le_pLq_plus_Qp_minus_pLQ_{o}_{d}_{a}"
            )

    # ---------- 5. Objective ----------
    ridership = gp.quicksum(
        ridership_weight * q_[(o, d, arc["arc_id"])]
        for (o, d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", [])
    )

    revenue = gp.quicksum(
        z_[(o, d, arc["arc_id"])] * float(k_bike_legs[(o, d, arc["arc_id"])])
        for (o, d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", [])
    )

    cost = gp.quicksum(
        bike_cost[(o, d, arc["arc_id"])] *
        float(k_bike_legs[(o, d, arc["arc_id"])]) *
        q_[(o, d, arc["arc_id"])]
        for (o, d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", [])
    )

    resource_man = gp.quicksum(
        q_[(o, d, arc["arc_id"])] * theta *
        gp.quicksum(
            delta_ia.get(arc["arc_id"], {}).get(str(i), 0) *
            (1 - station_inventory[str(i)] / station_capacity[str(i)])
            for i in stations_list
            if delta_ia.get(arc["arc_id"], {}).get(str(i), 0)
        )
        for (o, d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", [])
    )

    obj_expr = ridership + revenue - cost + resource_man
    # ... all your current build code ...
    model.setObjective(obj_expr, GRB.MAXIMIZE)
    model.update()

    # Save model
    os.makedirs(save_folder, exist_ok=True)
    json_filename = os.path.basename(json_file_path)
    gurobi_output_name = os.path.basename(json_file_path).replace(".json", "")
    gurobi_output_path = os.path.join(save_folder, "gurobi_outputs")
    os.makedirs(gurobi_output_path, exist_ok=True)

    if inventory_level is not None:
        low, high = inventory_level
        inv_tag = f"{low}_{high}"
    else:
        inv_tag = "invDefault"

    sav_file = os.path.join(
        gurobi_output_path,
        f"model_{gurobi_output_name}_{P_bar}_{capacity}_{inv_tag}_BASE.mps"
    )
    model.write(sav_file)
    print(f"Base model written to {sav_file}")

    return sav_file

def rebuild_handles_from_sav(model):
    """Rebuild dicts nu, q, p, z, gamma, w from variable names."""
    nu = {}
    q  = {}
    p  = {}
    z  = {}
    gamma = {}
    w  = {}

    for v in model.getVars():
        name = v.VarName
        if name.startswith("nu_"):
            # nu_o_d_arcid (arcid may contain underscores)
            _, o, d, rest = name.split("_", 3)
            nu[(int(o), int(d), rest)] = v
        elif name.startswith("q_"):
            _, o, d, rest = name.split("_", 3)
            q[(int(o), int(d), rest)] = v
        elif name.startswith("p_"):
            _, o, d, rest = name.split("_", 3)
            p[(int(o), int(d), rest)] = v
        elif name.startswith("z_"):
            _, o, d, rest = name.split("_", 3)
            z[(int(o), int(d), rest)] = v
        elif name.startswith("w_"):
            _, o, d, rest = name.split("_", 3)
            w[(int(o), int(d), rest)] = v
        elif name.startswith("gamma_"):
            _, o, d = name.split("_", 2)
            gamma[(int(o), int(d))] = v

    return {"nu": nu, "q": q, "p": p, "z": z, "w": w, "gamma": gamma}

def solve_from_sav(
    parsed_data,
    sav_file,
    *,
    json_file_path,
    save_folder,
    P_bar=None,
    cost_bike=0.6,
    parking_fee=2.8,
    pt_price=2,
    L,
    theta,
    ridership_weight,
    capacity_override=None,      # dict station -> cap or scalar or None
    inventory_override=None,     # (low, high) or dict or None
    sol_method=-1,
    time_limit=7200,
):
    model = None
    try:
        # 1) Read model
        model = gp.read(sav_file)

        # 2) Data
        W              = parsed_data["OD_pairs"]
        arcs_pt_bike   = parsed_data["arcs_pt_bike"]
        arcs_pt_only   = parsed_data["arcs_pt_only"]
        car_paths      = parsed_data["car_paths"]
        demands        = parsed_data["demands"]
        k_bike_legs    = parsed_data["k_bike_legs"]
        stations_list  = parsed_data["stations_list"]
        delta_ia       = parsed_data["delta_ia"]
        bike_time      = parsed_data["bike_time_min"]
        pt_time        = parsed_data["pt_time_min"]
        transfers      = parsed_data["transfer_time_min"]
        parking_time   = parsed_data["parking_time_min"]
        total_cost_car = parsed_data["total_cost_car"]
        travel_time    = parsed_data["travel_time_min"]

        # 3) Rebuild variable handles
        handles = rebuild_handles_from_sav(model)
        nu     = handles["nu"]
        q_     = handles["q"]
        p      = handles["p"]
        z_     = handles["z"]
        gamma_ = handles["gamma"]

        # 4) Scenario station capacities/inventories
        # base as in parsed_data
        base_capacity  = parsed_data["station_capacity"].copy()
        base_inventory = parsed_data["station_inventory"].copy()

        # capacity override
        if capacity_override is None:
            station_capacity = base_capacity
        elif isinstance(capacity_override, numbers.Number):
            station_capacity = {str(i): int(capacity_override) for i in stations_list}
        elif isinstance(capacity_override, Mapping):
            station_capacity = {str(k): int(v) for k, v in capacity_override.items()}
        else:
            raise TypeError("capacity_override must be None, scalar, or mapping")

        # inventory override
        if inventory_override is None:
            station_inventory = base_inventory
            inv_tag = "invDefault"
        elif isinstance(inventory_override, tuple) and len(inventory_override) == 2:
            low, high = inventory_override
            station_inventory = {
                sid: int(round(rand.uniform(low, high) * station_capacity[sid]))
                for sid in station_capacity
            }
            inv_tag = f"{low}_{high}"
        elif isinstance(inventory_override, Mapping):
            station_inventory = {str(k): int(v) for k, v in inventory_override.items()}
            inv_tag = "invCustom"
        else:
            raise TypeError("inventory_override must be None, (low,high), or mapping")

        # 5) Update RHS for L (MaxDisp) and station constraints
        for (o, d) in W:
            c = model.getConstrByName(f"MaxDisp_{o}_{d}")
            if c is None:
                raise RuntimeError(f"MaxDisp_{o}_{d} not found in model.")
            c.RHS = L

        for i in stations_list:
            i_str = str(i)
            cap_i = station_capacity[i_str]
            inv_i = station_inventory[i_str]

            c_cap   = model.getConstrByName(f"StationCap_{i}")
            c_nonneg= model.getConstrByName(f"StationCap_nonneg_{i}")
            if c_cap is None or c_nonneg is None:
                raise RuntimeError(f"Station constraints for {i} not found.")

            c_cap.RHS    = cap_i - inv_i
            c_nonneg.RHS = -inv_i

        model.update()

        # 6) Rebuild objective with new theta & ridership_weight
        # NOTE: we completely override the old objective.
        # We need pt_price & cost_bike & P_bar from your config, so pass them or fix them here:


        ridership_expr = gp.quicksum(
            ridership_weight * q_[(o, d, arc["arc_id"])]
            for (o, d) in W
            for arc in arcs_pt_bike.get(f"{o}_{d}", [])
        )

        revenue_expr = gp.quicksum(
            z_[(o, d, arc["arc_id"])] * float(k_bike_legs[(o, d, arc["arc_id"])])
            for (o, d) in W
            for arc in arcs_pt_bike.get(f"{o}_{d}", [])
        )

        cost_expr = gp.quicksum(
            cost_bike * float(k_bike_legs[(o, d, arc["arc_id"])]) *
            q_[(o, d, arc["arc_id"])]
            for (o, d) in W
            for arc in arcs_pt_bike.get(f"{o}_{d}", [])
        )

        resource_man_expr = gp.quicksum(
            q_[(o, d, arc["arc_id"])] * theta *
            gp.quicksum(
                delta_ia.get(arc["arc_id"], {}).get(str(i), 0) *
                (1 - station_inventory[str(i)] / station_capacity[str(i)])
                for i in stations_list
                if delta_ia.get(arc["arc_id"], {}).get(str(i), 0)
            )
            for (o, d) in W
            for arc in arcs_pt_bike.get(f"{o}_{d}", [])
        )

        obj_expr = ridership_expr + revenue_expr - cost_expr + resource_man_expr
        model.setObjective(obj_expr, GRB.MAXIMIZE)
        model.update()

        # 7) Gurobi params & solve
        os.makedirs(save_folder, exist_ok=True)
        gurobi_output_name = os.path.basename(json_file_path).replace(".json", "")
        gurobi_output_path = os.path.join(save_folder, "gurobi_outputs")
        os.makedirs(gurobi_output_path, exist_ok=True)

        P_bar = 0.6  # or pass as argument
        log_file = os.path.join(
            gurobi_output_path,
            f"gurobi_output_{gurobi_output_name}_{P_bar}_{capacity_override}_{inv_tag}_L{L}.txt"
        )
        model_file = os.path.join(
            gurobi_output_path,
            f"model_{gurobi_output_name}_{P_bar}_{capacity_override}_{inv_tag}_L{L}.lp"
        )
        sav_out = os.path.join(
            gurobi_output_path,
            f"model_{gurobi_output_name}_{P_bar}_{capacity_override}_{inv_tag}_L{L}.mps"
        )

        model.Params.LogFile = log_file
        #model.write(model_file)
        #model.write(sav_out)
        model.Params.NodefileStart = 4
        model.Params.NodefileDir   = r"C:\b_b_gurobi"
        model.Params.Method        = sol_method
        model.setParam("TimeLimit", time_limit)

        start = time.time()
        model.optimize()
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
        end = time.time()
        solution_time = end - start

        print(f"Solved {gurobi_output_name} with L={L}, theta={theta}, ridership_weight={ridership_weight} in {solution_time:.1f}s")

        # 8) Extraction – reuse your existing code, just using reconstructed handles.
        
        # Check solution
        if model.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED]:
            
            try:
                best_objective = model.ObjVal if model.SolCount > 0 else None  # Get best objective if a solution exists

                print(f"Solver ended {gurobi_output_name} with status {model.status}. Best objective found: {best_objective}")
                print(f"Total feasible solutions found: {model.SolCount}")

                # 1) Compute total extra slots used
                # For each OD:
                # used_total = number of displayed (A1+A2)
                # used_extra = max(0, used_total - L_base)   # these must be A1, by construction
                
                solution = {}
                solution_df=[]
                '''
                used_extra_total = 0
                for (o, d) in W:
                    od_key  = f"{o}_{d}"
                    A1_arcs = arcs_pt_bike.get(od_key, [])
                    A2_arcs = arcs_pt_only.get(od_key, [])

                    used_total = sum(1 for arc in A1_arcs + A2_arcs if nu[(o, d, arc["arc_id"])].X > 0.5)
                    used_extra = max(0, used_total - L_base)
                    used_extra_total += used_extra

                    solution_df.append({
                        "OD": f"{o}->{d}",
                        "Displayed total": used_total,
                        "Base cap (L_base)": L_base,
                        "Heuristic total cap": L_total_cap_od[(o, d)],
                        "Extra used (surge)": used_extra
                    })
                print(f"Total surge slots used: {used_extra_total}")
                '''

                # Save the solution to a file
                

                for (o, d) in W:
                    od_key = f"{o}_{d}"
                    A1_all = arcs_pt_bike.get(od_key, [])
                    A2_all = arcs_pt_only.get(od_key, [])
                    B_arcs = car_paths.get(od_key, [])
                    A_all  = A1_all + A2_all

                    # (1) find selected PT+Bike arcs
                    sol_nu_arcs = [
                        arc["arc_id"] 
                        for arc in A_all 
                        if nu[(o, d, arc["arc_id"])].X > 0.5
                    ]



                    # record γ once per OD
                    solution_df.append({
                        "Instance OD": f"{o}->{d}",
                        "OD":       f"{o}->{d}",
                        "gamma":    gamma_[(o, d)].X,
                    })

                    # (2) PT+Bike
                    for aid in sol_nu_arcs:
                        if (o, d, aid) not in bike_time:
                            continue
                        arc_id = aid
                        p_val = p[(o, d, aid)].X
                        q_val = q_[(o, d, aid)].X
                        #total_price = p_val * bike_time[(o, d, aid)] + pt_price
                        total_price = p_val + pt_price
                        bt          = bike_time[(o, d, aid)]
                        ptm         = pt_time[(o, d, aid)]
                        tr_min      = transfers[(o, d, aid)]
                        z_val       = z_[(o, d, aid)].X

                        solution_df.append({
                            "OD":           f"{o}->{d}",
                            "Arc ID": arc_id,
                            "Type":         "PT+Bike",
                            "nu":           nu[(o, d, aid)].X,
                            "Flow (q)":     q_val,
                            "Bike Price":   p_val,
                            "Total Price":  total_price,
                            "PT Time":      ptm,
                            "Bike Time":    bt,
                            "Transfers":    tr_min,
                            "z value":      z_val,
                            "Relaxation Difference": z_val - p_val * q_val                })

                    # (3) PT-Only
                    for arc in A2_all:
                        aid   = arc["arc_id"]
                        q_val = q_[(o, d, aid)].X
                        tr_min= transfers[(o, d, aid)]
                        solution_df.append({
                            "OD":           f"{o}->{d}",
                            "Arc ID": aid,
                            "Type":         "PT-Only",
                            "nu":           nu[(o, d, aid)].X,
                            "Flow (q)":     q_val,
                            "Bike Price":   0.0,
                            "Total Price":  pt_price,
                            "PT Time":     pt_time[(o, d, aid)],
                            "Bike Time":   0.0,
                            "Transfers":         tr_min,
                            "z value":      0.0,
                            "Relaxation Difference": 0.0
                        })

                    # (4) Car arcs
                    for arc in B_arcs:
                        aid     = arc["arc_id"]
                        q_val   = q_[(o, d, aid)].X
                        dur     = travel_time[(o, d, aid)]
                        park    = parking_time[(o, d, aid)]
                        tr_min  = transfers[(o, d, aid)]
                        cost_car= total_cost_car[(o, d, aid)]
                        solution_df.append({
                            "OD":           f"{o}->{d}",
                            "Arc ID": aid,
                            "Type":         "Car",
                            "nu":           0,
                            "Flow (q)":     q_val,
                            "Bike Price":   0.0,
                            "Total Price":  cost_car,
                            "PT Time":     0.0,
                            "Bike Time":   0.0,
                            "Transfers":         tr_min,
                            "Parking Time (min)": park,
                            "Total Travel Time (min)": dur
                        })

                solution_dict = {
                    "Solution Time (s)": solution_time,
                    "Objective Value":  model.ObjVal,
                    "Gap (%)":          model.MIPGap * 100,
                    "Solution Method":  sol_method,
                    "L":                 L,
                    "theta":             theta,
                    "ridership_weight":  ridership_weight,
                    "station_capacity":  station_capacity,    # <- scenario dict
                    "station_inventory": station_inventory,   # <- scenario dict (after randomization if any)
                    "instances":        solution_df,
                }
                os.makedirs(save_folder, exist_ok=True)
                sol_name = os.path.basename(json_file_path).replace(".json", f"_{P_bar}_{capacity_override}_{inv_tag}_solution.json")
                sol_path = os.path.join(save_folder, sol_name)
                with open(sol_path, 'w', encoding='utf-8') as f:
                    json.dump(solution_dict, f, indent=4, ensure_ascii=False)
                print(f"Solution saved to: {sol_path}")
            except Exception as extract_error:
                print(f"Error during solution extraction: {extract_error}")
                # Create a minimal solution file with basic info
                try:
                    # Calculate key metrics even with limited memory
                    total_pt_bike_flow = 0
                    total_pt_only_flow = 0 
                    total_revenue = 0
                    
                    print("Attempting to extract key solution metrics...")
                    
                    # Try to extract flows and revenue with memory-efficient approach
                    for (o, d) in W:
                        od_key = f"{o}_{d}"
                        
                        # PT+Bike arcs flow and revenue
                        try:
                            A1_all = arcs_pt_bike.get(od_key, [])
                            for arc in A1_all:
                                aid = arc["arc_id"]
                                if (o, d, aid) in q_:
                                    q_val = q_[(o, d, aid)].X
                                    total_pt_bike_flow += q_val
                                    
                                    # Calculate revenue: p * q
                                    if (o, d, aid) in p:
                                        p_val = p[(o, d, aid)].X
                                        total_revenue += p_val * q_val
                        except Exception as flow_error:
                            print(f"Error extracting PT+Bike flow for {od_key}: {flow_error}")
                            continue
                        
                        # PT-Only arcs flow
                        try:
                            A2_all = arcs_pt_only.get(od_key, [])
                            for arc in A2_all:
                                aid = arc["arc_id"]
                                if (o, d, aid) in q_:
                                    q_val = q_[(o, d, aid)].X
                                    total_pt_only_flow += q_val
                        except Exception as flow_error:
                            print(f"Error extracting PT-Only flow for {od_key}: {flow_error}")
                            continue
                    
                    # Get gap safely
                    try:
                        gap_percent = model.MIPGap * 100
                    except:
                        gap_percent = None
                    
                    minimal_solution = {
                        "Solution Time (s)": solution_time,
                        "Status": "PARTIAL_RECOVERY_WITH_METRICS", 
                        "Objective Value": model.ObjVal if hasattr(model, 'ObjVal') else None,
                        "Gap (%)": gap_percent,
                        "SolCount": model.SolCount if hasattr(model, 'SolCount') else 0,
                        "Total PT+Bike Flow": total_pt_bike_flow,
                        "Total PT-Only Flow": total_pt_only_flow,
                        "Total Revenue (p*q for PT+Bike)": total_revenue,
                        "Total Combined PT Flow": total_pt_bike_flow + total_pt_only_flow,
                        "Error": str(extract_error),
                        "Recovery_Note": "Extracted key metrics despite memory constraints"
                    }
                    
                    sol_name = os.path.basename(json_file_path).replace(".json", f"_{P_bar}_{capacity_override}_{inv_tag}_RECOVERED.json")
                    sol_path = os.path.join(save_folder, sol_name)
                    
                    with open(sol_path, 'w', encoding='utf-8') as f:
                        json.dump(minimal_solution, f, indent=4, ensure_ascii=False)
                        
                    print(f"Partial solution with key metrics saved to: {sol_path}")
                    print(f"  - PT+Bike Flow: {total_pt_bike_flow}")
                    print(f"  - PT-Only Flow: {total_pt_only_flow}")  
                    print(f"  - Total Revenue: {total_revenue}")
                    print(f"  - Gap: {gap_percent}%" if gap_percent is not None else "  - Gap: N/A")
                    
                    return None, minimal_solution, sol_path
                    
                except Exception as save_error:
                    print(f"Could not save even minimal solution: {save_error}")
                    return None, None, None

        else:
            # Compute IIS and write to a file for inspection.
            #model.computeIIS()
            #model.write("model_infeasible.ilp")
            #print("IIS computed and written to model_infeasible.ilp")
            
            # Compute conflict analysis and write results.
            #model.computeConflicts()
            #model.write("model_conflicts.ilp")
            print("Conflict analysis computed and written to model_conflicts.ilp")
            solution = None
            solution_dict = None
            sol_path = None
            print(f"Solver ended with status {model.status}")
            

        
        return solution, None, sol_path
    finally:
        if model is not None:
            model.dispose()
        del model
        gc.collect()


def solve_bilevel_model_from_bundle(
    bundle: dict,
    *,
    json_file_path,
    save_folder,
    max_displayed_alternatives: int,
    sol_method: int = -1,
    time_limit: int = 7200,
):
    model              = bundle["model"]
    W                  = bundle["W"]
    arcs_pt_bike       = bundle["arcs_pt_bike"]
    arcs_pt_only       = bundle["arcs_pt_only"]
    car_paths          = bundle["car_paths"]
    demands            = bundle["demands"]
    k_bike_legs        = bundle["k_bike_legs"]
    stations_list      = bundle["stations_list"]
    station_capacity   = bundle["station_capacity"]
    station_inventory  = bundle["station_inventory"]
    bike_time          = bundle["bike_time"]
    pt_time            = bundle["pt_time"]
    transfers          = bundle["transfers"]
    parking_time       = bundle["parking_time"]
    total_cost_car     = bundle["total_cost_car"]
    travel_time        = bundle["travel_time"]
    nu                 = bundle["nu"]
    p                  = bundle["p"]
    q_                 = bundle["q"]
    z_                 = bundle["z"]
    gamma_             = bundle["gamma"]
    P_bar_scalar       = bundle["P_bar_scalar"]
    capacity_arg       = bundle["capacity_arg"]
    inventory_level    = bundle["inventory_level_arg"]
    inv_tag            = bundle["inv_tag"]
    pt_price          = 2  # Assuming constant pt_price as in model building

    # --- update MaxDisp RHS to new L ---
    for (o, d) in W:
        c = model.getConstrByName(f"MaxDisp_{o}_{d}")
        if c is None:
            raise RuntimeError(f"Constraint MaxDisp_{o}_{d} not found.")
        c.RHS = max_displayed_alternatives
    model.update()

    # --- set params & solve (your existing logic) ---
    os.makedirs(save_folder, exist_ok=True)
    json_filename        = os.path.basename(json_file_path)
    gurobi_output_name   = os.path.basename(json_file_path).replace(".json", "")
    gurobi_output_path   = os.path.join(save_folder, "gurobi_outputs")
    os.makedirs(gurobi_output_path, exist_ok=True)

    log_file   = os.path.join(
        gurobi_output_path,
        f"gurobi_output_{gurobi_output_name}_{P_bar_scalar}_{capacity_arg}_{inv_tag}_L{max_displayed_alternatives}.txt"
    )
    model_file = os.path.join(
        gurobi_output_path,
        f"model_{gurobi_output_name}_{P_bar_scalar}_{capacity_arg}_{inv_tag}_L{max_displayed_alternatives}.lp"
    )
    sav_file = os.path.join(
        gurobi_output_path,
        f"model_{gurobi_output_name}_{P_bar_scalar}_{capacity_arg}_{inv_tag}_L{max_displayed_alternatives}.sav"
    )

    model.Params.LogFile = log_file
    model.write(model_file)
    model.write(sav_file)

    model.Params.NodefileStart = 4
    model.Params.NodefileDir   = r"C:\b_b_gurobi"
    model.Params.Method        = sol_method
    model.setParam("TimeLimit", time_limit)

    start_time = time.time()
    try:
        print(f"Starting optimization with Method={sol_method}, L={max_displayed_alternatives}")
        model.optimize()
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
    except gp.GurobiError as e:
        print(f"Gurobi error during optimization: {e}")
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
    except Exception as e:
        print(f"Unexpected error during optimization: {e}")
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)

    end_time = time.time()
    solution_time = end_time - start_time
    print(f"Solution time for {gurobi_output_name} (L={max_displayed_alternatives}): {solution_time:.2f} seconds")

    # --- solution extraction: identical to your current block ---
    if model.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED]:
        try:
            best_objective = model.ObjVal if model.SolCount > 0 else None
            print(f"Solver ended with status {model.status}. Best objective: {best_objective}")
            print(f"Total feasible solutions: {model.SolCount}")

            solution_df = []

            for (o, d) in W:
                od_key = f"{o}_{d}"
                A1_all = arcs_pt_bike.get(od_key, [])
                A2_all = arcs_pt_only.get(od_key, [])
                B_arcs = car_paths.get(od_key, [])
                A_all  = A1_all + A2_all

                sol_nu_arcs = [
                    arc["arc_id"]
                    for arc in A_all
                    if nu[(o, d, arc["arc_id"])].X > 0.5
                ]

                # gamma row
                solution_df.append({
                    "Instance OD": f"{o}->{d}",
                    "OD":          f"{o}->{d}",
                    "gamma":       gamma_[(o, d)].X,
                })

                # PT+Bike
                for aid in sol_nu_arcs:
                    if (o, d, aid) not in bike_time:
                        continue
                    p_val = p[(o, d, aid)].X
                    q_val = q_[(o, d, aid)].X
                    total_price = p_val + pt_price
                    bt          = bike_time[(o, d, aid)]
                    ptm         = pt_time[(o, d, aid)]
                    tr_min      = transfers[(o, d, aid)]
                    z_val       = z_[(o, d, aid)].X

                    solution_df.append({
                        "OD":           f"{o}->{d}",
                        "Arc ID":       aid,
                        "Type":         "PT+Bike",
                        "nu":           nu[(o, d, aid)].X,
                        "Flow (q)":     q_val,
                        "Bike Price":   p_val,
                        "Total Price":  total_price,
                        "PT Time":      ptm,
                        "Bike Time":    bt,
                        "Transfers":    tr_min,
                        "z value":      z_val,
                        "Relaxation Difference": z_val - p_val * q_val,
                    })

                # PT-only
                for arc in A2_all:
                    aid   = arc["arc_id"]
                    q_val = q_[(o, d, aid)].X
                    tr_min= transfers[(o, d, aid)]
                    solution_df.append({
                        "OD":           f"{o}->{d}",
                        "Arc ID":       aid,
                        "Type":         "PT-Only",
                        "nu":           nu[(o, d, aid)].X,
                        "Flow (q)":     q_val,
                        "Bike Price":   0.0,
                        "Total Price":  pt_price,
                        "PT Time":      pt_time[(o, d, aid)],
                        "Bike Time":    0.0,
                        "Transfers":    tr_min,
                        "z value":      0.0,
                        "Relaxation Difference": 0.0,
                    })

                # Car
                for arc in B_arcs:
                    aid   = arc["arc_id"]
                    q_val = q_[(o, d, aid)].X
                    dur   = travel_time[(o, d, aid)]
                    park  = parking_time[(o, d, aid)]
                    tr_min= transfers[(o, d, aid)]
                    cost_car = total_cost_car[(o, d, aid)]
                    solution_df.append({
                        "OD":                     f"{o}->{d}",
                        "Arc ID":                 aid,
                        "Type":                   "Car",
                        "nu":                     0,
                        "Flow (q)":               q_val,
                        "Bike Price":             0.0,
                        "Total Price":            cost_car,
                        "PT Time":                0.0,
                        "Bike Time":              0.0,
                        "Transfers":              tr_min,
                        "Parking Time (min)":     park,
                        "Total Travel Time (min)": dur,
                    })

            try:
                gap_pct = model.MIPGap * 100
            except Exception:
                gap_pct = None

            solution_dict = {
                "Solution Time (s)": solution_time,
                "Objective Value":   model.ObjVal,
                "Gap (%)":           gap_pct,
                "Solution Method":   sol_method,
                "L":                 max_displayed_alternatives,
                "instances":         solution_df,
            }

            sol_name = os.path.basename(json_file_path).replace(
                ".json",
                f"_{P_bar_scalar}_{capacity_arg}_{inv_tag}_L{max_displayed_alternatives}_solution.json"
            )
            sol_path = os.path.join(save_folder, sol_name)

            with open(sol_path, 'w', encoding='utf-8') as f:
                json.dump(solution_dict, f, indent=4, ensure_ascii=False)

            print(f"Solution saved to: {sol_path}")
            return solution_df, solution_dict, sol_path

        except Exception as extract_error:
            print(f"Error during solution extraction: {extract_error}")
            return None, None, None

    else:
        print(f"Solver ended with status {model.status}")
        return None, None, None
