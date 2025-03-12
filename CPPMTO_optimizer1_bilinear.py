import gurobipy as gp
from gurobipy import GRB
import CPPMTO_instance_parser_2
from CPPMTO_instance_parser_2 import parse_bilevel_instance1
import os
import json
import time


def solve_bilevel_model_bilinear(json_file_path, save_folder, M, verbose=True, verbose2=True):
    


    parsed_data = parse_bilevel_instance1(json_file_path)
    """
    Builds and solves the model in your LaTeX using the JSON-like data from `parsed_data`.
    Adapt the code as needed to match exactly how you interpret each parameter.
    """

    # 1. Parse Data from your JSON/dict
    max_displayed_alternatives = parsed_data["max_disp_alts"]  # L
    ridership_weight = parsed_data["ridership_weight"]                      # φ (varphi)

    # OD pairs
    W = parsed_data["OD_pairs"]  # list of (o,d) tuples
        # We interpret: 
    #   A1^(o,d) = arcs_pt_bike
    #   A2^(o,d) = arcs_pt_only
    #   B^(o,d)  = car_paths
    arcs_pt_bike = parsed_data["arcs_pt_bike"]   # dict: key "o_d", value = list of arcs
    arcs_pt_only = parsed_data["arcs_pt_only"]   # dict: key "o_d", value = list of arcs
    car_paths    = parsed_data["car_paths"]      # dict: key "o_d", value = list of arcs

    bike_time = parsed_data["bike_time"]
    pt_time = parsed_data["pt_time"]
    fixed_pt_price = parsed_data["fixed_pt_price"]
    bike_cost = parsed_data["bike_cost"]
    transfers = parsed_data["transfers"]
    travel_time = parsed_data["travel_time"] #car travel time
    fuel_cost=parsed_data["fuel_cost"] #car fuel cost

    arcs_all = {}

    for (o, d) in W:
        od_key = f"{o}_{d}"
        bike_arcs = arcs_pt_bike.get(od_key, [])
        pt_arcs   = arcs_pt_only.get(od_key, [])
        arcs_all[(o, d)] = bike_arcs + pt_arcs

    # Station capacity & inventory
    stations_list = parsed_data["stations_list"]    # e.g. [1,0,5,2,7,6,4]
    station_capacity = parsed_data["station_capacity"]  # dict: {"1":21, ...}
    station_inventory= parsed_data["station_inventory"] # dict: {"1":12, ...}

    # Demand Q_{(o,d)}
    demands = parsed_data["demands"]  # e.g. {(3,6):187, ...}
    # The big dictionary delta_ia that gives how arcs change station usage:
    # delta_ia[ arc_id ][ station_str ] = integer

    delta_ia = parsed_data["delta_ia"]

    #M=15

    Pbar = parsed_data["bike_cost_operator"]

    d_val = parsed_data["fixed_pt_price_value"]

    beta_1 = parsed_data["alpha_vals"]
    beta_2 = parsed_data["beta_vals"]
    beta_3 = parsed_data["theta_vals"]


    ############### Let's start optimizing ############### 


    # Create the Gurobi model
    model = gp.Model("Bilevel_Model")

    # Decision Variables
    # nu[(o,d), arc_id], p[(o,d), arc_id], q[(o,d), arc_id], arc_id]
    # gamma_[(o,d)] for the constraints with gamma if you need them
    nu = {}
    p  = {}
    q_ = {}
    gamma_ = {}

    for (o,d) in W:
        # gamma^(o,d), if used
        gamma_[(o,d)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"gamma_{o}_{d}")
        
        # A1 = arcs in PT+Bike, A2 = arcs in PT-only
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        B_arcs  = car_paths.get(od_key, [])

        # For arcs in A1 or A2 => we have nu, p, q, z
        for arc in A1_arcs + A2_arcs:
            arc_id = arc["arc_id"]
            nu[(o,d,arc_id)] = model.addVar(vtype=GRB.BINARY, name=f"nu_{o}_{d}_{arc_id}")
            p[(o,d,arc_id)]  = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"p_{o}_{d}_{arc_id}")
            q_[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")

        # For arcs in B => only q_ (assuming no bike usage => no nu, p, z)
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            q_[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")

    model.update()
    # Constraints

    # 1) sum_{a in A^(o,d)} nu_a^(o,d) <= L
    for (o,d) in W:
        A_all = arcs_all[(o,d)]
        model.addConstr(
            gp.quicksum(nu[(o,d, arc["arc_id"])] for arc in A_all) <= max_displayed_alternatives,
            name=f"MaxDisp_{o}_{d}"
        )

    # 2) p_a^(o,d) >= Pbar * nu_a^(o,d) for a in A1
    #    p_a^(o,d) <= M * nu_a^(o,d)    for a in A1
    #    p_a^(o,d) = 0                  for a in A2
    for (o,d) in W:
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        
        for arc in A1_arcs:
            arc_id = arc["arc_id"]
            model.addConstr(p[(o,d,arc_id)] >= Pbar*nu[(o,d, arc["arc_id"])],
                            name=f"p_min_{o}_{d}_{arc_id}")
            model.addConstr(p[(o,d,arc_id)] <= M*nu[(o,d, arc["arc_id"])],
                            name=f"p_max_{o}_{d}_{arc_id}")
        
        for arc in A2_arcs:
            arc_id = arc["arc_id"]
            model.addConstr(p[(o,d,arc_id)] == 0,
                            name=f"p_zero_{o}_{d}_{arc_id}")
        


    # 3) q_a^(o,d) <= Q_{(o,d)} * nu_a^(o,d), for a in A^(o,d)
    for (o,d) in W:
        A_all = arcs_all[(o,d)]
        for arc in A_all:
            arc_id = arc["arc_id"]
            model.addConstr(
                q_[(o,d,arc_id)] <= demands[(o,d)] * nu[(o,d,arc_id)],
                name=f"q_le_{o}_{d}_{arc_id}"
            )

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
                lhs_expr.add(q_[(o,d,arc_id)], delta_val)
        model.addConstr(
            lhs_expr <= capacity_i - inventory_i,
            name=f"StationCap_{i}")
        
    # 5) sum_{a in A^(o,d)} q_a^(o,d) + sum_{b in B^(o,d)} q_b^(o,d) = Q_{(o,d)}
    for (o,d) in W:
        od_key = f"{o}_{d}"
        lhs_expr = gp.quicksum(q_[(o,d, arc["arc_id"])] for arc in arcs_all[(o,d)]) \
                    + gp.quicksum(q_[(o,d, arc["arc_id"])] for arc in car_paths.get(od_key, []))
        model.addConstr(lhs_expr == demands[(o,d)], name=f"demand_{o}_{d}")


    # 6) Non-negativity & binary constraints are handled by var definitions
    # nu is BINARY, p,q are CONTINUOUS with lb=0

    # 7) If you use gamma^(o,d) constraints: gamma^(o,d) <= V_a^(o,d), etc. 
    for (o,d) in W:
        b1 = beta_1[(o,d)]
        b2 = beta_2[(o,d)]
        b3 = beta_3[(o,d)]

        od_key = f"{o}_{d}"
        A_arcs = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])
        for arc in A_arcs:
            arc_id = arc["arc_id"]

            # Retrieve parameters from your dictionaries
            d_val   = fixed_pt_price[(o,d,arc_id)]  # d_a
            tau_val = bike_time[(o,d,arc_id)]       # τ_a
            Tt_val  = pt_time[(o,d,arc_id)]         # Tt_a
            Tr_val  = transfers[(o,d,arc_id)]       # Tr_a

            # p_a is p[(o,d,arc_id)], gamma is gamma_[(o,d)]

            # Directly build the right-hand side as a Python expression
            rhs_expr = (b1 * d_val
                        + b1 * tau_val * p[(o,d,arc_id)]
                        + b2 * Tt_val
                        + b2 * tau_val
                        + b3 * Tr_val)

            # Then add the constraint: gamma_(o,d) <= rhs_expr
            model.addConstr(
                gamma_[(o,d)] <= rhs_expr,
                name=f"gammaA_{o}_{d}_{arc_id}"
            )

        B_arcs = car_paths.get(od_key, [])
        for arc in B_arcs:
            arc_id = arc["arc_id"]

            F_val  = fuel_cost[(o,d, arc_id)]     # F_b
            Tt_val = travel_time[(o,d, arc_id)]   # Tt_b

            rhs_expr = b1 * F_val + b2 * Tt_val

            model.addConstr(
                gamma_[(o,d)] <= rhs_expr,
                name=f"gammaB_{o}_{d}_{arc_id}"
            )


    # 8) Strong Duality constraint, be careful with the bilinear term p*q 
    lhs_expr = gp.LinExpr()

    for (o,d) in W:
        # beta values for OD pair
        b1 = beta_1[(o,d)]
        b2 = beta_2[(o,d)]
        b3 = beta_3[(o,d)]
        
        
        # Arc sets
        od_key = f"{o}_{d}"
        A_arcs = arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, [])
        B_arcs = car_paths.get(od_key, [])

        # (1) Summation over arcs in A^(o,d)
        for arc in A_arcs:
            arc_id = arc["arc_id"]

            # Retrieve parameters
            d_val   = fixed_pt_price[(o,d,arc_id)]   # d_a
            tau_val = bike_time[(o,d,arc_id)]        # tau_a
            Tt_val  = pt_time[(o,d,arc_id)]          # Tt_a
            Tr_val  = transfers[(o,d,arc_id)]        # Tr_a

            # q_a^(o,d) and z_a^(o,d)
            q_var = q_[(o,d, arc_id)]
            p_var = p[(o,d, arc_id)]

            # Add to LHS: beta1[q_a*d_a + q_a*p_a*tau_a]
            lhs_expr.add(q_var, b1 * d_val)
            lhs_expr += p_var * q_var * (b1 * tau_val)

            # Then: q_a * [beta2(Tt_a + tau_a) + beta3*Tr_a]
            # We can split that into separate .add(...) calls:
            lhs_expr.add(q_var, b2 * Tt_val)
            lhs_expr.add(q_var, b2 * tau_val)
            lhs_expr.add(q_var, b3 * Tr_val)

        # (2) Summation over arcs in B^(o,d) (car arcs)
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            F_val  = fuel_cost[(o,d, arc_id)]     # F_b
            Ttb_val= travel_time[(o,d, arc_id)]   # Tt_b
            q_var  = q_[(o,d, arc_id)]

            # Add q_b * [beta1 * F_b + beta2 * Tt_b]
            lhs_expr.add(q_var, b1 * F_val)
            lhs_expr.add(q_var, b2 * Ttb_val)

    # Now the RIGHT-hand side: sum_{(o,d)} Q_{(o,d)} * gamma_(o,d)
    rhs_expr = gp.quicksum(demands[(o,d)] * gamma_[(o,d)] for (o,d) in W)

    # Add the equality constraint
    model.addConstr(lhs_expr == rhs_expr, name="StrongDuality")


    # Objective
    #   max φ ( sum_{(o,d)} sum_{a in A1} q_a )
    #       + sum_{(o,d)} sum_{a in A1} [ q_a*p_a * tau_a - Pbar * tau_a * q_a ]
    #
    # We interpret tau_a^(o,d) for PT+Bike arcs. Possibly you define: tau_a = pt_time or (pt_time + bike_time).
    # Let's assume tau_a = pt_time[(o,d,arc_id)] + bike_time[(o,d,arc_id)]
    obj_expr = gp.LinExpr()
    for (o,d) in W:
        od_key = f"{o}_{d}"
        # We only add arcs from A1^(o,d) = arcs_pt_bike
        for arc in arcs_pt_bike.get(od_key, []):
            arc_id = arc["arc_id"]
            tau_val = bike_time[(o,d,arc_id)]
            # term 1: φ * q_a
            obj_expr.add(q_[(o,d,arc_id)], ridership_weight*M)
            # term 2: tau_a * q_a*p_a
            obj_expr += p[(o,d,arc_id)]*q_[(o,d,arc_id)]*tau_val
            # term 3: -Pbar * tau_a * q_a
            obj_expr.add(q_[(o,d,arc_id)], -Pbar * tau_val)

    model.setObjective(obj_expr, GRB.MAXIMIZE)
    start_time = time.time()
    # Solve with
    model.setParam("NonConvex", 2) 
    model.setParam("Presolve", 0)
  
    #Gurobi output files
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
 
    # Optimize
    model.setParam("TimeLimit", 3600) # 1 hour time limit
    model.optimize()
    end_time = time.time()
    solution_time = end_time - start_time
    print(f"Solution time for {gurobi_output_name}: {solution_time:.2f} seconds")

    # Check solution
    if model.status in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED] and model.SolCount > 0:
        best_objective = model.ObjVal                                                         # Get best objective if a solution exists

        print(f"Solver ended {gurobi_output_name} with status {model.status}. Best objective found: {best_objective}")
        
        solution = {}
        solution_df=[]
        
        # Save the solution to a file
        
        for (o, d) in W:
            sol_nu_arcs = []

            # Get relevant arcs
            od_key = f"{o}_{d}"
            A1_all = arcs_pt_bike.get(od_key, [])  # PT + bike arcs
            A2_all = arcs_pt_only.get(od_key, [])  # PT-only arcs
            B_arcs = car_paths.get(od_key, [])  # Car arcs
            A_all = arcs_all[(o,d)]  # All PT arcs

            # Print OD header
            if verbose2:
                print(f"\nOD=({o}->{d})")

            # (1) Identify selected PT+Bike arcs and store data
            if verbose2:
                print(f"  Selected arcs (nu=1):", end=" ")
            for arc in A_all:
                arc_id = arc["arc_id"]
                if nu[(o, d, arc_id)].X > 0.5:
                    sol_nu_arcs.append(arc_id)

            if verbose2:
                print(sol_nu_arcs)  # Print selected arcs list

            # (2) Process PT+Bike arcs
            if verbose2:
                print("  Detailed PT+Bike arcs info:")
            for arc in A1_all:
                arc_id = arc["arc_id"]
                p_val = p[(o, d, arc_id)].X
                q_val = q_[(o, d, arc_id)].X
                price = p_val + d_val
                gamma_val = gamma_[(o, d)].X
                mile_type = arc["mile_type"]
                nu_val = nu[(o, d, arc_id)].X

                if verbose2:
                    print(f"    Arc {arc_id}: p={p_val:.3f}, q={q_val:.3f}, total_price={price:.3f}, "
                        f"pt_time={arc['pt_time']}, bike_time={arc['bike_time']}, transfers={arc['transfers']}, first/last mile: {mile_type},  gamma={gamma_val:.3f}")

                solution_df.append({
                    "OD": f"{o}->{d}",
                    "Arc ID": arc_id,
                    "Type": "PT+Bike",
                    "Flow (q)": q_val,
                    "Bike Price": p_val,
                    "Total Cost to Users": price,
                    "PT Time": arc["pt_time"],
                    "Bike Time": arc["bike_time"],
                    "Transfers": arc["transfers"],
                    "Mile Type": mile_type,
                    "nu": nu_val
                })

            # (3) Process PT-Only arcs
            if verbose2:
                print("  Detailed PT-Only arcs info:")
            for arc in A2_all:
                arc_id = arc["arc_id"]
                p_val = p[(o, d, arc_id)].X
                q_val = q_[(o, d, arc_id)].X
                price = d_val  # PT-Only price is just the fixed price


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

            # (4) Process Car arcs
            if verbose2:
                print("  Car arcs info:")
            for arc in B_arcs:
                arc_id = arc["arc_id"]
                q_val = q_[(o, d, arc_id)].X
                price = arc["fuel_cost"]  # Car price stays the same
                travel_time = arc["travel_time"]

                if verbose2:
                    print(f"    Arc {arc_id}: q={q_val:.3f}, travel_time={arc['travel_time']}, fuel_cost={price:.2f},gamma={gamma_val:.3f}")

                solution_df.append({
                    "OD": f"{o}->{d}",
                    "Arc ID": arc_id,
                    "Type": "Car",
                    "Flow (q)": q_val,
                    "Total Cost to Users": price,
                    "PT Time": None,
                    "Bike Time": None,
                    "Transfers": None,
                    "Travel Time": travel_time
                })

        # Convert solution list to dictionary
        solution_dict = {
            "Solution Time (s)": solution_time,
            "Objective Value": best_objective,
            "Gap (%)": model.MIPGap*100 if model.SolCount > 0 else None,
            "instances": solution_df
        }
        
        # Save solution as JSON file
        instance_name = os.path.basename(json_file_path).replace(".json", "_solution.json")
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






