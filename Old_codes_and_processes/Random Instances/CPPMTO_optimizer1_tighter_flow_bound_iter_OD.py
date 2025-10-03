import gurobipy as gp
from gurobipy import GRB
import CPPMTO_instance_parser_2
from CPPMTO_instance_parser_2 import parse_bilevel_instance1
import os
import json
import time

def solve_bilevel_model_with_tight_flow_bound_iter_OD(json_file_path, save_folder, num_iter, M, Pbar, od_bounds=None, ops=min, verbose=True, verbose2=True):
    """
    Builds and solves the bilevel model with tight flow bounds.
    
    Parameters:
        json_file_path: str, path to instance JSON file.
        save_folder: str, folder where to save the solution.
        M: float, global upper bound for price (if od_bounds not provided).
        Pbar: float, global lower bound for price (if od_bounds not provided).
        od_bounds: dict or None, keys: (o,d), values: (lb, ub) for the price bounds for that OD pair.
        ops: function, used for flow_ub computation.
        verbose, verbose2: booleans controlling output.
    """
    parsed_data = parse_bilevel_instance1(json_file_path)
    # 1. Parse Data from JSON/dict
    max_displayed_alternatives = parsed_data["max_disp_alts"]
    ridership_weight = parsed_data["ridership_weight"]

    # OD pairs
    W = parsed_data["OD_pairs"]
    # A1^(o,d): PT+Bike arcs; A2^(o,d): PT-only arcs; B^(o,d): car_paths
    arcs_pt_bike = parsed_data["arcs_pt_bike"]
    arcs_pt_only = parsed_data["arcs_pt_only"]
    car_paths = parsed_data["car_paths"]

    bike_time = parsed_data["bike_time"]
    pt_time = parsed_data["pt_time"]
    fixed_pt_price = parsed_data["fixed_pt_price"]
    bike_cost = parsed_data["bike_cost"]
    transfers = parsed_data["transfers"]
    travel_time = parsed_data["travel_time"]
    fuel_cost = parsed_data["fuel_cost"]

    arcs_all = {}
    for (o, d) in W:
        od_key = f"{o}_{d}"
        bike_arcs = arcs_pt_bike.get(od_key, [])
        pt_arcs = arcs_pt_only.get(od_key, [])
        arcs_all[(o, d)] = bike_arcs + pt_arcs

    # Station capacity & inventory
    stations_list = parsed_data["stations_list"]
    station_capacity = parsed_data["station_capacity"]
    station_inventory = parsed_data["station_inventory"]

    # Demand
    demands = parsed_data["demands"]
    # delta_ia gives station membership indicators for each arc
    delta_ia = parsed_data["delta_ia"]

    # Use the provided Pbar and d_val (fixed PT price)
    Pbar = Pbar
    d_val = parsed_data["fixed_pt_price_value"]

    beta_1 = parsed_data["alpha_vals"]
    beta_2 = parsed_data["beta_vals"]
    beta_3 = parsed_data["theta_vals"]

    ############### Precompute flow upper bounds for arcs in A1  ###############
    flow_ub = {}
    if ops == min:
        for (o, d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):
                arc_id = arc["arc_id"]
                ub_values = []
                if arc_id in delta_ia:
                    for i_str, delta_val in delta_ia[arc_id].items():
                        if abs(delta_val) == 1:
                            # Here we assume s_i=0, so we use station_capacity[i_str]
                            ub = station_capacity[i_str]
                            ub_values.append(ub)
                if ub_values:
                    flow_ub[(o, d, arc_id)] = min(ub_values)
                else:
                    flow_ub[(o, d, arc_id)] = demands[(o, d)]
    else:
        for (o, d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):
                arc_id = arc["arc_id"]
                ub_values = []
                if arc_id in delta_ia:
                    for i_str, delta_val in delta_ia[arc_id].items():
                        if delta_val == -1:
                            ub = station_capacity[i_str] + station_inventory[i_str]
                            ub_values.append(ub)
                        elif delta_val == 1:
                            ub = station_capacity[i_str] - station_inventory[i_str]
                            ub_values.append(ub)
                if ub_values:
                    flow_ub[(o, d, arc_id)] = max(ub_values)
                else:
                    flow_ub[(o, d, arc_id)] = demands[(o, d)]
    # *** UPDATED: "flow_ub" computed.

    ############### Start Optimization ###############
    model = gp.Model("Bilevel_Model")

    # Decision Variables
    nu = {}  # binary arc selection
    p = {}   # price variable (continuous)
    q_ = {}  # flow variable
    z_ = {}  # bilinear term: z = p * q
    gamma_ = {}  # auxiliary variable

    for (o, d) in W:
        gamma_[(o, d)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"gamma_{o}_{d}")
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        B_arcs = car_paths.get(od_key, [])
        for arc in A1_arcs + A2_arcs:
            arc_id = arc["arc_id"]
            nu[(o, d, arc_id)] = model.addVar(vtype=GRB.BINARY, name=f"nu_{o}_{d}_{arc_id}")
            p[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"p_{o}_{d}_{arc_id}")
            q_[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")
            z_[(o, d, arc_id)] = model.addVar(vtype=GRB.CONTINUOUS, name=f"z_{o}_{d}_{arc_id}")
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            q_[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")

    model.update()

    # 1) Display Limit: sum_{a in A^(o,d)} nu_a^(o,d) <= L
    for (o, d) in W:
        A_all = arcs_all[(o, d)]
        model.addConstr(gp.quicksum(nu[(o, d, arc["arc_id"])] for arc in A_all) <= max_displayed_alternatives,
                        name=f"MaxDisp_{o}_{d}")

    # 2) Price Constraints:
    # For arcs in A1, we enforce p in [lb,ub]*nu, where lb and ub are taken from od_bounds if provided,
    # otherwise use global Pbar and M.
    for (o, d) in W:
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        # Get OD-specific bounds if available
        if od_bounds is not None:
            lb, ub = od_bounds[(o, d)]
        else:
            lb, ub = Pbar, M
        for arc in A1_arcs:
            arc_id = arc["arc_id"]
            model.addConstr(p[(o, d, arc_id)] >= lb * nu[(o, d, arc_id)],
                            name=f"p_min_{o}_{d}_{arc_id}")  # *** UPDATED: Use OD-specific lower bound.
            model.addConstr(p[(o, d, arc_id)] <= ub * nu[(o, d, arc_id)],
                            name=f"p_max_{o}_{d}_{arc_id}")  # *** UPDATED: Use OD-specific upper bound.
        for arc in A2_arcs:
            arc_id = arc["arc_id"]
            model.addConstr(p[(o, d, arc_id)] == 0,
                            name=f"p_zero_{o}_{d}_{arc_id}")
            model.addConstr(z_[(o, d, arc_id)] == 0,
                            name=f"z_zero_{o}_{d}_{arc_id}")

    # 3) Flow bound: q_a^(o,d) <= Q_(o,d)*nu_a^(o,d)
    for (o, d) in W:
        A_all = arcs_all[(o, d)]
        for arc in A_all:
            arc_id = arc["arc_id"]
            model.addConstr(q_[(o, d, arc_id)] <= demands[(o, d)] * nu[(o, d, arc_id)],
                            name=f"q_le_{o}_{d}_{arc_id}")

    # 4) Station Capacity Constraint
    for i in stations_list:
        i_str = str(i)
        capacity_i = station_capacity[i_str]
        inventory_i = station_inventory[i_str]
        lhs_expr = gp.LinExpr()
        for (o, d) in W:
            od_key = f"{o}_{d}"
            for arc in arcs_pt_bike.get(od_key, []):
                arc_id = arc["arc_id"]
                delta_val = delta_ia.get(arc_id, {}).get(i_str, 0.0)
                lhs_expr.add(q_[(o, d, arc_id)], delta_val)
        model.addConstr(lhs_expr <= capacity_i - inventory_i,
                        name=f"StationCap_{i}")

    # 5) Demand Satisfaction
    for (o, d) in W:
        od_key = f"{o}_{d}"
        lhs_expr = gp.quicksum(q_[(o, d, arc["arc_id"])] for arc in arcs_all[(o, d)]) \
                    + gp.quicksum(q_[(o, d, arc["arc_id"])] for arc in car_paths.get(od_key, []))
        model.addConstr(lhs_expr == demands[(o, d)], name=f"demand_{o}_{d}")

    # 6) Domains are set in variable definitions.

    # 7) Gamma Constraints
    for (o, d) in W:
        b1 = beta_1[(o, d)]
        b2 = beta_2[(o, d)]
        b3 = beta_3[(o, d)]
        od_key = f"{o}_{d}"
        A_arcs = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])
        for arc in A_arcs:
            arc_id = arc["arc_id"]
            d_val_val = fixed_pt_price[(o, d, arc_id)]
            tau_val = bike_time[(o, d, arc_id)]
            Tt_val = pt_time[(o, d, arc_id)]
            Tr_val = transfers[(o, d, arc_id)]
            rhs_expr = (b1 * d_val_val +
                        b1 * tau_val * p[(o, d, arc_id)] +
                        b2 * Tt_val +
                        b2 * tau_val +
                        b3 * Tr_val)
            model.addConstr(gamma_[(o, d)] <= rhs_expr,
                            name=f"gammaA_{o}_{d}_{arc_id}")
        B_arcs = car_paths.get(od_key, [])
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            F_val = fuel_cost[(o, d, arc_id)]
            Tt_val = travel_time[(o, d, arc_id)]
            rhs_expr = b1 * F_val + b2 * Tt_val
            model.addConstr(gamma_[(o, d)] <= rhs_expr,
                            name=f"gammaB_{o}_{d}_{arc_id}")

    # 8) Strong Duality Constraint
    lhs_expr = gp.LinExpr()
    for (o, d) in W:
        b1 = beta_1[(o, d)]
        b2 = beta_2[(o, d)]
        b3 = beta_3[(o, d)]
        od_key = f"{o}_{d}"
        A_arcs = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])
        B_arcs = car_paths.get(od_key, [])
        for arc in A_arcs:
            arc_id = arc["arc_id"]
            d_val_val = fixed_pt_price[(o, d, arc_id)]
            tau_val = bike_time[(o, d, arc_id)]
            Tt_val = pt_time[(o, d, arc_id)]
            Tr_val = transfers[(o, d, arc_id)]
            q_var = q_[(o, d, arc_id)]
            z_var = z_[(o, d, arc_id)]
            lhs_expr.add(q_var, b1 * d_val_val)
            lhs_expr.add(z_var, b1 * tau_val)
            lhs_expr.add(q_var, b2 * Tt_val)
            lhs_expr.add(q_var, b2 * tau_val)
            lhs_expr.add(q_var, b3 * Tr_val)
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            F_val = fuel_cost[(o, d, arc_id)]
            Ttb_val = travel_time[(o, d, arc_id)]
            q_var = q_[(o, d, arc_id)]
            lhs_expr.add(q_var, b1 * F_val)
            lhs_expr.add(q_var, b2 * Ttb_val)
    rhs_expr = gp.quicksum(demands[(o, d)] * gamma_[(o, d)] for (o, d) in W)
    model.addConstr(lhs_expr == rhs_expr, name="StrongDuality")

    # 9) McCormick Envelopes for z = p * q, using flow_ub as the upper bound for q.
    for (o, d) in W:
        od_dem = demands[(o, d)]
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            arc_id = arc["arc_id"]
            ub_val = flow_ub[(o, d, arc_id)]
            # Use the OD-specific lower and upper bounds if available; otherwise, use global Pbar and M.
            if od_bounds is not None:
                lb, ub = od_bounds[(o, d)]
            else:
                lb, ub = Pbar, M
            model.addConstr(z_[(o, d, arc_id)] >= lb * q_[(o, d, arc_id)],
                            name=f"z_min_1_{o}_{d}_{arc_id}")
            model.addConstr(z_[(o, d, arc_id)] >= ub * q_[(o, d, arc_id)]
                            + p[(o, d, arc_id)] * ub_val
                            - ub * ub_val * nu[(o, d, arc_id)],
                            name=f"z_min_2_{o}_{d}_{arc_id}")
            model.addConstr(z_[(o, d, arc_id)] <= ub * q_[(o, d, arc_id)],
                            name=f"z_max_1_{o}_{d}_{arc_id}")
            model.addConstr(z_[(o, d, arc_id)] <= p[(o, d, arc_id)] * ub_val
                            + lb * q_[(o, d, arc_id)]
                            - lb * ub_val * nu[(o, d, arc_id)],
                            name=f"z_max_2_{o}_{d}_{arc_id}")

    # 10) Objective:
    # Maximize φ * (sum_{(o,d)} sum_{a in A1} q_a) + sum_{(o,d)} sum_{a in A1} [ z_a*tau_a - lb*tau_a*q_a ]
    # Here, we use lb from the OD-specific bounds (or global Pbar if not provided) in the subtraction term.
    obj_expr = gp.LinExpr()
    for (o, d) in W:
        od_key = f"{o}_{d}"
        # For arcs in A1
        for arc in arcs_pt_bike.get(od_key, []):
            arc_id = arc["arc_id"]
            tau_val = bike_time[(o, d, arc_id)]
            if od_bounds is not None:
                lb, _ = od_bounds[(o, d)]
            else:
                lb = Pbar
            obj_expr.add(q_[(o, d, arc_id)], ridership_weight * 4)  # scale factor; adjust if needed
            obj_expr.add(z_[(o, d, arc_id)], tau_val)
            obj_expr.add(q_[(o, d, arc_id)], -lb * tau_val)
    model.setObjective(obj_expr, GRB.MAXIMIZE)

    model.update()
    start_time = time.time()
    model.setParam("NonConvex", 2)
    model.setParam("Presolve", 0)
  
    # Gurobi output files
    os.makedirs(save_folder, exist_ok=True)
    json_filename = os.path.basename(json_file_path)
    gurobi_output_name = os.path.basename(json_file_path).replace(".json", "")
    gurobi_output_path = os.path.join(save_folder, "gurobi_outputs")
    if not os.path.exists(gurobi_output_path):
        os.makedirs(gurobi_output_path)
    log_file = os.path.join(gurobi_output_path, f"gurobi_output_{gurobi_output_name}.txt")
    model.Params.LogFile = log_file
    model_file = os.path.join(gurobi_output_path, f"model_{gurobi_output_name}.lp")
    model.write(model_file)
    
    # Solve
    model.setParam("TimeLimit", 3600)
    model.optimize()
    end_time = time.time()
    solution_time = end_time - start_time
    print(f"Solution time for {gurobi_output_name}: {solution_time:.2f} seconds")

    if model.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED]:
        best_objective = model.ObjVal if model.SolCount > 0 else None
        print(f"Solver ended {gurobi_output_name} with status {model.status}. Best objective found: {best_objective}")
        
        solution = {}
        solution_df = []
        
        for (o, d) in W:
            sol_nu_arcs = []
            od_key = f"{o}_{d}"
            A1_all = arcs_pt_bike.get(od_key, [])
            A2_all = arcs_pt_only.get(od_key, [])
            B_arcs = car_paths.get(od_key, [])
            A_all = arcs_all[(o, d)]
            if od_bounds is not None:
                lb, ub = od_bounds[(o, d)]
            else:
                lb, ub = Pbar, M
            if verbose2:
                print(f"\nOD=({o}->{d})")
                print(f"  Price bounds: lower bound = {lb:.3f}, upper bound = {ub:.3f}")  # NEW PRINT STATEMENT
            if verbose2:
                print("  Selected arcs (nu=1):", end=" ")
            for arc in A_all:
                arc_id = arc["arc_id"]
                if nu[(o, d, arc_id)].X > 0.5:
                    sol_nu_arcs.append(arc_id)
            if verbose2:
                print(sol_nu_arcs)
            if verbose2:
                print("  Detailed PT+Bike arcs info:")
            for arc in A1_all:
                arc_id = arc["arc_id"]
                p_val = p[(o, d, arc_id)].X
                q_val = q_[(o, d, arc_id)].X
                price = p_val + d_val
                z_val = z_[(o, d, arc_id)].X
                gamma_val = gamma_[(o, d)].X
                mile_type = arc["mile_type"]
                nu_val = nu[(o, d, arc_id)].X
                if verbose2:
                    print(f"    Arc {arc_id}: p={p_val:.3f}, q={q_val:.3f}, total_price={price:.3f}, bounds={lb, ub} "
                          f"pt_time={arc['pt_time']}, bike_time={arc['bike_time']}, transfers={arc['transfers']}, "
                          f"first/last mile: {mile_type}, z={z_val:.3f}, gamma={gamma_val:.3f}")
                solution_df.append({
                    "OD": f"{o}->{d}",
                    "Arc ID": arc_id,
                    "nu": nu_val,
                    "Type": "PT+Bike",
                    "Flow (q)": q_val,
                    "Bike Price": p_val,
                    "Total Cost to Users": price,
                    "PT Time": arc["pt_time"],
                    "Bike Time": arc["bike_time"],
                    "Transfers": arc["transfers"],
                    "Mile Type": mile_type,
                    "z value": z_val,
                    "Relaxation Difference": z_val - p_val*q_val,
                    "Relaxation Difference (ABS)": abs(z_val - p_val*q_val),
                    "Price Lower Bound": lb,
                    "Price Upper Bound": ub
                })
            if verbose2:
                print("  Detailed PT-Only arcs info:")
            for arc in A2_all:
                arc_id = arc["arc_id"]
                p_val = p[(o, d, arc_id)].X
                q_val = q_[(o, d, arc_id)].X
                price = d_val
                if verbose2:
                    print(f"    Arc {arc_id}: p={p_val:.3f}, q={q_val:.3f}, total_price={price:.3f}, "
                          f"pt_time={arc['pt_time']}, transfers={arc['transfers']}, gamma={gamma_val:.3f}")
                solution_df.append({
                    "OD": f"{o}->{d}",
                    "Arc ID": arc_id,
                    "Type": "PT-Only",
                    "Flow (q)": q_val,
                    "Total Cost to Users": price,
                    "PT Time": arc["pt_time"],
                    "Bike Time": None,
                    "Transfers": arc["transfers"]
                })
            if verbose2:
                print("  Car arcs info:")
            for arc in B_arcs:
                arc_id = arc["arc_id"]
                q_val = q_[(o, d, arc_id)].X
                price = arc["fuel_cost"]
                travel_time_val = arc["travel_time"]
                if verbose2:
                    print(f"    Arc {arc_id}: q={q_val:.3f}, travel_time={arc['travel_time']}, fuel_cost={price:.2f}, gamma={gamma_val:.3f}")
                solution_df.append({
                    "OD": f"{o}->{d}",
                    "Arc ID": arc_id,
                    "Type": "Car",
                    "Flow (q)": q_val,
                    "Total Cost to Users": price,
                    "PT Time": None,
                    "Bike Time": None,
                    "Transfers": None,
                    "Travel Time": travel_time_val
                })
        solution_dict = {
            "Solution Time (s)": solution_time,
            "Objective Value": model.ObjVal,
            "Gap (%)": model.MIPGap*100,
            "instances": solution_df
        }
        if od_bounds is not None:
            lb, ub = od_bounds[(o, d)]
        else:
            lb, ub = Pbar, M
        instance_name = os.path.basename(json_file_path).replace(".json", f"_{num_iter}_solution.json")
        solution_file = os.path.join(save_folder, instance_name)
        with open(solution_file, "w") as f:
            json.dump(solution_dict, f, indent=4)
        print(f"Solution saved to: {solution_file}")
    else:
        solution = None
        solution_dict = None
        solution_file = None
        print(f"Solver ended with status {model.status}")
    
    return solution, solution_dict, solution_file
