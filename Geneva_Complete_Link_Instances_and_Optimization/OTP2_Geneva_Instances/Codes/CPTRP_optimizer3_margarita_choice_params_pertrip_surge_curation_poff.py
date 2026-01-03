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




def solve_bilevel_model__margarita_choice_params_pertrip_surge_curation_poff(
    parsed_data: dict, *,
    json_file_path, save_folder,
    max_displayed_alternatives=10, mult_A1=1,
    capacity=None, inventory_level=None,
    dep_cost=0, cost_bike=0.6, parking_fee=2.8,
    P_bar=0.5, pt_price=2, theta=0.5,ridership_weight=2*4, sol_method=-1,
    verbose=True, verbose2=True,
    p_off_map=None, disable_set=None, global_p_off=None
):
    


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
    k_bike_legs      = parsed_data["k_bike_legs"]

    # Station info: bike stations from GBFS, assigned inventory and capacity
    stations_list     = parsed_data["stations_list"]
    station_capacity  = parsed_data["station_capacity"]
    station_inventory = parsed_data["station_inventory"]
    if capacity is None:
        station_capacity  = parsed_data["station_capacity"]
    elif isinstance(capacity, Mapping):
        station_capacity = {str(k):int(v) for k,v in capacity.items()}
    elif isinstance(capacity, numbers.Number):
        station_capacity = {str(i): int(capacity) for i in stations_list}
    else:
        raise TypeError( "`capacity` must be None, a scalar, or a dict-like object")

    if inventory_level is not None:
        low, high = inventory_level
        station_inventory = {
            sid: int(round(rand.uniform(low, high) * station_capacity[sid]))
            for sid in station_capacity
        }
    else:
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

 
   # --- Heuristic-style competitiveness scan to precompute OD caps ---


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
    

    #activate here for surge capacities
    '''
    def best_car_utility(o, d):
        od_key = f"{o}_{d}"
        best = float("inf")
        for arc in car_paths.get(od_key, []):
            a = arc["arc_id"]
            F  = total_cost_car[(o, d, a)]
            Tt = travel_time[(o, d, a)]
            u  = (ASC_CAR
                + BETA_Cost_Car  * (F - dep_cost)
                + BETA_Cost_park * parking_fee
                + BETA_Time_Car  * Tt)
            if u < best:
                best = u
        return best

    def pt_bike_utility_at_Pbar(o, d, a):
        # include k_a (0,1,2) in the bike-price term
        k = int(k_bike_legs.get((o, d, a), 1))
        return (ASC_PT + ASC_BIKE
                + BETA_Cost_PT   * pt_price
                + BETA_Cost_BIKE * k * P_bar
                + BETA_Time_PT   * pt_time[(o, d, a)]
                + BETA_Time_BIKE * bike_time.get((o, d, a), 0.0)
                + BETA_TR_BIKE   * transfers[(o, d, a)])





    L_base = int(max_displayed_alternatives)
    A1_base_per_od = {}
    L_total_cap_od = {}   # final OD cap to enforce
    total_extra = 0
    num_ods = 0

    for (o, d) in W:
        od_key = f"{o}_{d}"
        # base A1 share from multiplier (heuristic)
        A1_base = max(0, math.ceil(float(mult_A1) * L_base))
        A1_base_per_od[(o, d)] = A1_base

        # competitiveness vs car at P_bar
        car_best = best_car_utility(o, d)
        comp_count = 0
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            u = pt_bike_utility_at_Pbar(o, d, a)
            if u < car_best:
                comp_count += 1

        # heuristic A1 cap with surge

        extra  = min(L_base, comp_count)          # extra slots reserved for A1
        L_total_cap_od[(o, d)] = L_base + extra    # total OD cap (A1+A2)
        total_extra += extra
        num_ods += 1

    avg_extra_per_od = (total_extra / num_ods) if num_ods else 0.0
    print(f"Average extra additions per OD: {avg_extra_per_od:.3f} (over {num_ods} ODs)")
    '''
    #main time
    ############### Let's start optimizing ############### 


    # Create the Gurobi model
    model = gp.Model("Bilevel_Model")

    # Decision Variables
    # nu[(o,d), arc_id], p[(o,d), arc_id], q[(o,d), arc_id], z[(o,d), arc_id]
    # gamma_[(o,d)] for the constraints with gamma if you need them
    nu = {}
    p  = {}
    q_ = {}
    z_ = {}
    #pi = {}   # continuous >=0, one per A-arc
    #ksi  = {}   # product t = pi * nu (for strong duality term)
    #walkers = {}
    gamma_ = {}
    d_val = {}
    bike_cost = {}
    Pbar = {}  #lower bound for bike price
    M = {}
    w = {}
    for (o,d) in W:
        # gamma^(o,d), if used
        gamma_[(o,d)] = model.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"gamma_{o}_{d}")

        # A1 = arcs in PT+Bike, A2 = arcs in PT-only
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        B_arcs  = car_paths.get(od_key, [])

        for arc in A1_arcs:
            arc_id = arc["arc_id"]
            p[(o,d,arc_id)]  = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"p_{o}_{d}_{arc_id}")
            z_[(o,d,arc_id)] = model.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"z_{o}_{d}_{arc_id}")
            bike_cost[(o,d,arc_id)] = cost_bike
            Pbar[(o,d,arc_id)] = P_bar
            if p_off_map and (o,d,arc_id) in p_off_map:
                M[(o,d,arc_id)] = float(p_off_map[(o,d,arc_id)])
            else:
                M[(o,d,arc_id)] = float(global_p_off if global_p_off is not None else 4.0)
            
            w[(o, d, arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"w_{o}_{d}_{arc_id}")
        # For arcs in A1 or A2 => we have nu, p, q, z
        for arc in A1_arcs + A2_arcs:
            arc_id = arc["arc_id"]
            nu[(o,d,arc_id)] = model.addVar(vtype=GRB.BINARY, name=f"nu_{o}_{d}_{arc_id}")

            q_[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")
            d_val[(o,d,arc_id)] = pt_price
            #pi[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"pi_{o}_{d}_{arc_id}")
            #ksi[(o,d,arc_id)]  = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"t_{o}_{d}_{arc_id}")  # = pi*nu

        # For arcs in B => only q_ (assuming no bike usage => no nu, p, z)
        for arc in B_arcs:
            arc_id = arc["arc_id"]
            q_[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{arc_id}")
            #walkers[(o,d,arc_id)] = model.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_walk_{arc_id}")

    OFF_PRICE = 10.0  # or a per-arc value if you computed P_off[(o,d,a)]

    model.update()
    # Constraints
    
    # 1) sum_{a in A^(o,d)} nu_a^(o,d) <= L + surge_slack(o,d)
    #  sum_{a in A2^(o,d)} nu_a^(o,d) <= L
    # or sum_{a in A^(o,d)} nu_a^(o,d) <= L
    # --- OD caps mirroring the heuristic logic ---
    
    for (o, d) in W:
        od_key  = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        
        lhs = gp.quicksum(nu[(o, d, arc["arc_id"])] for arc in A1_arcs + A2_arcs)
        model.addConstr(lhs <= max_displayed_alternatives, name=f"MaxDisp_{o}_{d}")
        
        if A1_arcs + A2_arcs:
            model.addConstr(lhs >= 1, name=f"MaxDisp_{o}_{d}_base")
        
        '''
        # (i) PT-only cannot use the surge share: A2 ≤ L_base
        if A2_arcs:
            model.addConstr(
                gp.quicksum(nu[(o, d, arc["arc_id"])] for arc in A2_arcs) <= L_base,
                name=f"Cap_A2_base_{o}_{d}"
            )

        # (ii) Total (A1 + A2) ≤ L_total_cap_od[(o,d)]
        if A1_arcs or A2_arcs:
            model.addConstr(
                gp.quicksum(nu[(o, d, arc["arc_id"])] for arc in A1_arcs + A2_arcs) 
                <= L_total_cap_od[(o, d)],
                name=f"Cap_Total_{o}_{d}"
            )
        '''
        
    
    # 2) p_a^(o,d) >= Pbar * nu_a^(o,d) for a in A1
    # p_a^(o,d) <= M * nu_a^(o,d)    for a in A1
    # -----------------------------------
    # 1) On/off price bounds (linear in ν)
    # -----------------------------------
    for (o,d) in W:
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            # p >= Pbar*nu + OFF_PRICE*(1-nu)
            model.addConstr(
                p[(o,d,a)] >= Pbar[(o,d,a)]*nu[(o,d,a)] + M[(o,d,a)]*(1 - nu[(o,d,a)]),
                name=f"p_onoff_lb_{o}_{d}_{a}"
            )
            # p <= M*nu + OFF_PRICE*(1-nu)
            model.addConstr(
                p[(o,d,a)] <= M[(o,d,a)],
                name=f"p_onoff_ub_{o}_{d}_{a}"
            )

    # 3) q_a^(o,d) <= Q_{(o,d)} * nu_a^(o,d), for a in A^(o,d)
    for (o,d) in W:
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        
        for arc in A1_arcs + A2_arcs:
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
        model.addConstr(lhs_expr <= capacity_i - inventory_i, name=f"StationCap_{i}")
        
        model.addConstr(lhs_expr + inventory_i >= 0, name=f"StationCap_nonneg_{i}")
        
    # 5) sum_{a in A^(o,d)} q_a^(o,d) + sum_{b in B^(o,d)} q_b^(o,d) = Q_{(o,d)}
    for (o,d) in W:
        od_key = f"{o}_{d}"
        A1_arcs = arcs_pt_bike.get(od_key, [])
        A2_arcs = arcs_pt_only.get(od_key, [])
        arcs_all = A1_arcs + A2_arcs
        lhs_expr = gp.quicksum(q_[(o,d, arc["arc_id"])] for arc in arcs_all) + gp.quicksum(q_[(o,d, arc["arc_id"])] for arc in car_paths.get(od_key, []))

        model.addConstr(lhs_expr == demands[(o,d)], name=f"demand_{o}_{d}")


    # 6) Non-negativity & binary constraints are handled by var definitions
    # nu is BINARY, p,q,z are CONTINUOUS with lb=0

    # 7) If you use gamma^(o,d) constraints: gamma^(o,d) <= V_a^(o,d), etc. 
    for (o,d) in W:
        # beta values for OD pair


        od_key = f"{o}_{d}"

        # ---------- PT+Bike arcs ------------------------------------------------
        for arc in arcs_pt_bike.get(od_key, []):
            a  = arc["arc_id"]
            rhs = (asc_bike[(o,d,a)]
                + asc_pt[(o,d,a)]
                + beta_cost_pt[(o,d,a)] * d_val[(o,d,a)]                       # << make sure d_val is defined!
                + beta_cost_bike[(o,d,a)] * k_bike_legs[(o,d,a)] * p[(o,d,a)]
                + beta_pttime[(o,d,a)] * pt_time[(o,d,a)]
                + beta_biketime[(o,d,a)] * bike_time.get((o,d,a))
                + beta_transfer_time_bike[(o,d,a)] * transfers[(o,d,a)])
            
            model.addConstr(gamma_[(o,d)] <= rhs ,
                            name=f"gammaA_{o}_{d}_{a}")

        # ---------- PT‑only arcs -------------------------------------------------
        for arc in arcs_pt_only.get(od_key, []):
            a  = arc["arc_id"]
            rhs = (
                asc_pt[(o,d,a)]
                # asc_bike = 0 for pure PT
                + beta_cost_pt[(o,d,a)] * d_val[(o,d,a)]
                 #b3 * 0                          # p = 0
                + beta_pttime[(o,d,a)] * pt_time[(o,d,a)]
                # no bicycle leg → tau = 0
                + beta_transfer_time_pt[(o,d,a)] * transfers[(o,d,a)]
            )
            model.addConstr(gamma_[(o,d)] <= rhs, 
                            name=f"gammaA_{o}_{d}_{a}")
        
        for arc in car_paths.get(od_key, []):
            a = arc["arc_id"]
            F_val  = total_cost_car[(o,d,a)]
            Tt_val = travel_time[(o,d,a)]
            Tr_val = transfers[(o,d,a)]

            rhs_expr = (asc_car[(o,d,a)]
                        + beta_cost_car[(o,d,a)] * (F_val - dep_cost)
                        + beta_cost_park[(o,d,a)] *  parking_fee 
                        + beta_car_time[(o,d,a)] * Tt_val
                        )

            model.addConstr(gamma_[(o,d)] <= rhs_expr,
                            name=f"gammaB_{o}_{d}_{a}_car")

    # 8) Strong Duality constraint 
    lhs_expr = gp.LinExpr()

    # The RIGHT-hand side: sum_{(o,d)} Q_{(o,d)} * gamma_(o,d)
    rhs_expr = gp.quicksum(demands[(o,d)] * gamma_[(o,d)] for (o,d) in W)

    for (o,d) in W:

        # beta values for OD pair
        # Arc sets
        od_key = f"{o}_{d}"

        B_arcs = car_paths.get(od_key, [])

        # ---------- PT + Bike arcs ------------------------------------
        for arc in arcs_pt_bike.get(od_key, []):

            a       = arc["arc_id"]
            q_var   = q_[(o,d,a)]
            z_var   = z_[(o,d,a)]
            d_pt   = d_val[(o,d,a)]
            tau_val = bike_time.get((o,d,a), 0.0)
            Tt_val  = pt_time[(o,d,a)]
            Tr_val  = transfers[(o,d,a)]
            asc_val = asc_bike[(o,d,a)] + asc_pt[(o,d,a)]

            lhs_expr.add(q_var, beta_cost_pt[(o,d,a)] * d_pt)
            lhs_expr.add(z_var, beta_cost_bike[(o,d,a)]*k_bike_legs[(o,d,a)])                      
            lhs_expr.add(q_var, beta_pttime[(o,d,a)] * Tt_val)
            lhs_expr.add(q_var, beta_biketime[(o,d,a)] * tau_val)
            lhs_expr.add(q_var, beta_transfer_time_bike[(o,d,a)] * Tr_val)
            lhs_expr.add(q_var, asc_val)
        
        # ---------- PT‑only arcs --------------------------------------
        for arc in arcs_pt_only.get(od_key, []):

            a       = arc["arc_id"]
            q_var   = q_[(o,d,a)]
            d_pt   = d_val[(o,d,a)]   
            Tt_val  = pt_time [(o,d,a)]
            Tr_val  = transfers[(o,d,a)]
            asc_val = asc_pt[(o,d,a)]                    

            lhs_expr.add(q_var, beta_cost_pt[(o,d,a)] * d_pt)
            lhs_expr.add(q_var, beta_pttime[(o,d,a)] * Tt_val)
            lhs_expr.add(q_var, beta_transfer_time_pt[(o,d,a)] * Tr_val)
            lhs_expr.add(q_var, asc_val)

        # (2) Summation over arcs in B^(o,d) (car arcs)
        for barc in B_arcs:

            a = barc["arc_id"]
            F_val  = total_cost_car[(o,d, a)]     # F_b
            Ttb_val= travel_time[(o,d, a)]   # Tt_b
            #Tr_val = transfers[(o,d,a)] #car pickup on foot transfers
            q_var  = q_[(o,d, a)]
            asc_val = asc_car[(o,d,a)]                    

            lhs_expr.add(q_var, beta_cost_car[(o,d,a)] * (F_val -dep_cost))
            lhs_expr.add(q_var, parking_fee*beta_cost_park[(o,d,a)])
            lhs_expr.add(q_var, beta_car_time[(o,d,a)] * Ttb_val)
            lhs_expr.add(q_var,asc_val)

    
    # Add the equality constraint
    model.addConstr(lhs_expr == rhs_expr, name=f"StrongDuality")
    
    # -----------------------------------------------------
    # 2) Linearization of w = nu * q  (Big-M with M = Q_od)
    # -----------------------------------------------------
    for (o,d) in W:
        Qod = demands[(o,d)]
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]
            # 0 <= w <= q
            model.addConstr(w[(o,d,a)] <= q_[(o,d,a)], name=f"w_le_q_{o}_{d}_{a}")
            # w <= Q * nu
            model.addConstr(w[(o,d,a)] <= Qod * nu[(o,d,a)], name=f"w_le_Qnu_{o}_{d}_{a}")
            # w >= q - Q * (1 - nu)   <-- NOTE the MINUS here
            model.addConstr(w[(o,d,a)] >= q_[(o,d,a)] - Qod * (1 - nu[(o,d,a)]),
                            name=f"w_ge_q_minus_Q1mnu_{o}_{d}_{a}")
            # (w >= 0 by variable LB)
    
    # 9) z_{a}^{(o,d)} constraints for a in A1^(o,d)
    #    z_a >= Pbar*q_a
    #    z_a >= M*q_a + p_a*Q_od - M*Q_od*nu_a
    #    z_a <= M*q_a
    #    z_a <= p_a*Q_od + Pbar*q_a - Pbar*Q_od*nu_a
    # -------------------------------------------------------
    # 3) Switched McCormick planes for z = p * q (via w, ν)
    # -------------------------------------------------------
    for (o,d) in W:
        Qod = demands[(o,d)]
        od_key = f"{o}_{d}"
        for arc in arcs_pt_bike.get(od_key, []):
            a = arc["arc_id"]

            # pL(ν) q  = Pbar*w + M*(q - w)
            model.addConstr(
                z_[(o,d,a)] >= Pbar[(o,d,a)]*w[(o,d,a)] + M[(o,d,a)]*(q_[(o,d,a)] - w[(o,d,a)]),
                name=f"z_ge_pLq_{o}_{d}_{a}"
            )
            
            # pU(ν) q  = M*q
            model.addConstr(
                z_[(o,d,a)] <= M[(o,d,a)]*q_[(o,d,a)],
                name=f"z_le_pUq_{o}_{d}_{a}"
            )
            # z >= pU(ν) q + Q p - pU(ν) Q
            model.addConstr(
                z_[(o,d,a)] >= M[(o,d,a)]*q_[(o,d,a)]
                + Qod * p[(o,d,a)]
                - (M[(o,d,a)]*Qod),
                name=f"z_ge_pUq_plus_Qp_minus_pUQ_{o}_{d}_{a}"
            )
            # z <= pL(ν) q + Q p - pL(ν) Q
            model.addConstr(
                z_[(o,d,a)] <=
                (Pbar[(o,d,a)]*w[(o,d,a)] + M[(o,d,a)]*(q_[(o,d,a)] - w[(o,d,a)]))
                + Qod * p[(o,d,a)]
                - (Pbar[(o,d,a)]*Qod*nu[(o,d,a)] + M[(o,d,a)]*Qod*(1 - nu[(o,d,a)])),
                name=f"z_le_pLq_plus_Qp_minus_pLQ_{o}_{d}_{a}"
            )
    '''
    # 10) ksi_{a}^{(o,d)} constraints for a in A^(o,d)
    # McCormick for t = pi * nu  (nu ∈ {0,1}, 0 ≤ pi ≤ Pi_bar)
    for (o,d) in W:
        od_key = f"{o}_{d}"
        PiMax = 1000
        for arc in arcs_pt_bike.get(od_key, []) + arcs_pt_only.get(od_key, []):
            a = arc["arc_id"]
            model.addConstr(ksi[(o,d,a)] <= pi[(o,d,a)],                       name=f"t_le_pi_{o}_{d}_{a}")
            model.addConstr(ksi[(o,d,a)] <= PiMax * nu[(o,d,a)],               name=f"t_le_Pi_nu_{o}_{d}_{a}")
            model.addConstr(ksi[(o,d,a)] >= pi[(o,d,a)] + PiMax*(nu[(o,d,a)]-1),name=f"pi_minus_t_le_Pi_1mnu_{o}_{d}_{a}")
            model.addConstr(ksi[(o,d,a)] >= 0.0,                               name=f"t_ge_0_{o}_{d}_{a}")
    '''


    # Objective
    #   max φ ( sum_{(o,d)} sum_{a in A1} q_a )
    #       + sum_{(o,d)} sum_{a in A1} [ z_a *  - bike_cost *  * q_a ]
    #
    tolerance = 1e-3

    #DELETED TIME COMPONENT FROM WEIGHTS
    ridership =  gp.quicksum(ridership_weight*q_[(o,d,arc["arc_id"])] for (o,d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", []))

    revenue = gp.quicksum(z_[(o,d,arc["arc_id"])]*float(k_bike_legs[(o,d,arc["arc_id"])]) for (o,d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", []))
    
    cost = gp.quicksum(bike_cost[(o,d,arc["arc_id"])]*float(k_bike_legs[(o,d,arc["arc_id"])]) * q_[(o,d,arc["arc_id"])] for (o,d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", []))
    
    resource_man = gp.quicksum((q_[(o,d,arc["arc_id"])]) * theta * gp.quicksum(delta_ia.get(arc["arc_id"], {}).get(str(i), 0) * (1 - station_inventory[str(i)] / station_capacity[str(i)]) 
                                                                             for i in stations_list if delta_ia.get(arc["arc_id"], {}).get(str(i), 0)) 
                                                                             for (o,d) in W for arc in arcs_pt_bike.get(f"{o}_{d}", []) )



    obj_expr = ridership + revenue - cost + resource_man 

    model.setObjective(obj_expr, GRB.MAXIMIZE)
    
    # Set solution pool parameters to capture multiple feasible solutions
    #model.setParam("PoolSearchMode", 2)
    #model.setParam("PoolSolutions", 10)
    
    start_time = time.time()
    # Solve with
    #model.setParam("NonConvex", 2) 
    #model.setParam("Presolve", 0)
  
    #Gurobi output files
    os.makedirs(save_folder, exist_ok=True)
    json_filename = os.path.basename(json_file_path)
    gurobi_output_name = os.path.basename(json_file_path).replace(".json", "")
    gurobi_output_path = os.path.join(save_folder, "gurobi_outputs")
    if not os.path.exists(gurobi_output_path):
        os.makedirs(gurobi_output_path)
    inv_tag = f"{low}_{high}" if inventory_level is not None else "invDefault"

    log_file   = os.path.join(gurobi_output_path, f"gurobi_output_{gurobi_output_name}_{P_bar}_{capacity}_{inv_tag}.txt")
    model_file = os.path.join(gurobi_output_path, f"model_{gurobi_output_name}_{P_bar}_{capacity}_{inv_tag}.lp")
    model.Params.LogFile = log_file
    model.write(model_file)
    model.Params.NodefileStart= 4
    model.Params.NodefileDir= r"C:\b_b_gurobi"
    model.Params.Threads =4
    model.Params.Method = sol_method  # dual simplex

    # Optimize
    #model.feasRelaxS(0, False, False, True)
    model.setParam("TimeLimit", 7200) # 2 hour time limit
    try:
        print(f"Starting optimization with solution method (Gurobi Method): {sol_method}")        
        model.optimize()
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
    except gp.GurobiError as e:
        print(f"Gurobi error during optimization: {e}")
        if "Out of memory" in str(e):
            print("Memory error detected - will attempt solution recovery")
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
    except Exception as e:
        print(f"Unexpected error during optimization: {e}")
        # Still try to save any solutions found
        save_solution_files_safely(model, gurobi_output_path, gurobi_output_name)
    
    end_time = time.time()
    solution_time = end_time - start_time

    print(f"Solution time for {gurobi_output_name}: {solution_time:.2f} seconds")


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
                "instances":        solution_df,
            }
            os.makedirs(save_folder, exist_ok=True)
            sol_name = os.path.basename(json_file_path).replace(".json", f"_{P_bar}_{capacity}_{inv_tag}_solution.json")
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
                
                sol_name = os.path.basename(json_file_path).replace(".json", f"_{P_bar}_{capacity}_{inv_tag}_RECOVERED.json")
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
    
    return solution, solution_dict, sol_path






