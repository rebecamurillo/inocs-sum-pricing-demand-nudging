#incremental_lp.py

'''
What it does (summary):

Builds the shared part of your model once: γ variables per OD, all car arcs, demand balances, station capacity rows, and the Strong Duality equality.

Lets you add PT-only and PT+Bike alternatives on demand. Each add:

creates variables (q and possibly p,z),

wires them into demand, capacity, γ-rows, and Strong Duality (via chgCoeff),

updates the objective exactly as in your code (revenue via z, ridership and resource signal via q, minus bike cost).

Lets you deactivate a PT+Bike (or PT-only) alternative without rebuilding:

fixes its variables at 0,

relaxes its γ-row so it cannot bind,

removes its contributions from Strong Duality.

Uses Dual Simplex (Method = 1) so each small change re-optimizes fast from the previous basis.

Provides extract_solution_df(...) to produce the same JSON structure you had before.
'''


import time
import gurobipy as gp
from gurobipy import GRB


class IncrementalBilevelLP:
    """
    Incremental, add-only builder for your single-level LP (no ν / cardinality / slacks).
    - Build core once (γ per OD, car arcs, demand, station capacity, Strong Duality).
    - Add PT-only / PT+Bike alternatives as needed.
    - Optionally deactivate (drop) previously added alternatives.
    """
    def set_per_arc_price_caps(self, p_off_map: dict, global_p_off: float | None = None):
        """Install per-arc P_up exactly as provided; keep a global fallback."""
        # keys are already (o,d,a); values are floats from your p_off function
        self.P_up_arc = {(int(o), int(d), str(a)): float(v) for (o, d, a), v in p_off_map.items()}
        self.P_up = float(global_p_off) if global_p_off is not None else self.P_up_default
    # -------- construction --------

    def __init__(
            self,
            parsed_data, *,
            P_bar=0.5, P_up=4.0, theta = 0.5, pt_price=2.0,
            cost_bike=0.6, parking_fee=2.8, dep_cost=0.0,
            tolerance=1e-3, 
            ASC_PT=-0.756, ASC_BIKE=0.0, ASC_CAR=-0.669, 
            BETA_Cost_BIKE = 0.689,
            BETA_Time_BIKE = 0.108,
            BETA_TR_BIKE   = 0.199,
            BETA_Cost_PT   = 0.779,
            BETA_Time_PT   = 0.101,
            BETA_TR_PT     = 0.208,
            BETA_Cost_Car  = 0.474,
            BETA_Cost_park = 0.532,
            BETA_Time_Car  = 0.116,
            quiet=True, nodefile_dir=None, threads=4, time_limit=None,
            p_off_map = None,
            disable_arcs = None,
            global_p_off = None
            ):     
            
        self.data = parsed_data


        #Sets and data extraction

        self.W                = parsed_data["OD_pairs"]
        self.demands          = parsed_data["demands"]
        self.arcs_pt_bike     = parsed_data["arcs_pt_bike"]
        self.arcs_pt_only     = parsed_data["arcs_pt_only"]
        self.car_paths        = parsed_data["car_paths"]
        self.stations_list    = parsed_data["stations_list"]
        self.station_capacity = parsed_data["station_capacity"]
        self.station_inventory= parsed_data["station_inventory"]
        self.delta_ia         = parsed_data["delta_ia"]
        self.bike_time        = parsed_data["bike_time_min"]
        self.pt_time          = parsed_data["pt_time_min"]
        self.transfers        = parsed_data["transfer_time_min"]
        self.parking_time     = parsed_data["parking_time_min"]
        self.total_cost_car   = parsed_data["total_cost_car"]
        self.travel_time      = parsed_data["travel_time_min"]
        self.k_bike_legs      = parsed_data["k_bike_legs"]
        # Parameters / coefficients
        


        self.P_bar = P_bar
        self.P_up_default  = P_up
        self.P_up_arc = {}
        self.disable_arcs = set(disable_arcs or [])
        if p_off_map:
            self.set_per_arc_price_caps(p_off_map, global_p_off)



        self.pt_price = pt_price
        self.cost_bike = cost_bike
        self.parking_fee = parking_fee
        self.dep_cost = dep_cost
        self.tolerance = tolerance
        self.theta = theta

        #Choice Model

        self.ASC_PT   = ASC_PT
        self.ASC_BIKE = ASC_BIKE
        self.ASC_CAR  = ASC_CAR
        
        self.BETA_Cost_BIKE = BETA_Cost_BIKE
        self.BETA_Time_BIKE = BETA_Time_BIKE
        self.BETA_TR_BIKE   = BETA_TR_BIKE
        
        self.BETA_Cost_PT   = BETA_Cost_PT
        self.BETA_Time_PT   = BETA_Time_PT
        self.BETA_TR_PT     = BETA_TR_PT

        self.BETA_Cost_Car  = BETA_Cost_Car
        self.BETA_Cost_park = BETA_Cost_park
        self.BETA_Time_Car  = BETA_Time_Car



        #Single Level Model

        self.m = gp.Model("Bilevel_Incremental")        
        self.m.ModelSense = GRB.MAXIMIZE     # <-- add this
        if quiet:
            #self.m.Params.OutputFlag = 0
            self.m.Params.LogFile    = ""

        self.m.Params.Method = 1 #Dual Simplex Method

        if nodefile_dir:
            self.m.Params.NodefileDir = nodefile_dir
            self.m.Params.NodefileStart = 2
        if threads:
            self.m.Params.Threads = int(threads)
        if time_limit is not None:
            self.m.Params.TimeLimit = int(time_limit)

        
        #Handles

        self.gamma = {}      # gamma[(o,d)]
        self.q = {}          # q[(o,d,a)] for all arcs (car, PT-only, PT+Bike)
        self.p = {}          # p[(o,d,a)] for PT+Bike
        self.z = {}          # z[(o,d,a)] for PT+Bike
        self.dem_eq = {}     # demand constraints per OD
        self.cap_constr = {} # station capacity upper bound per station
        self.cap_nonneg = {} # station inventory lower bound per station
        self.sd_constr = None
        self.gamma_rows = {} # γ-row per arc key (o,d,a) when present

        # Track which A1/A2 arcs are in the model currely

        self._present_A1 = set()
        self._present_A2 = set()

        #precompute resource coefficient

        self._resource_coeff = {}

        for (o,d) in self.W:
            od = f"{o}_{d}"

            for arc in self.arcs_pt_bike.get(od,[]):
                a = arc["arc_id"]
                sig=sum(
                    self.delta_ia.get(a, {}).get(str(i), 0)*  (1 - self.station_inventory[str(i)] / self.station_capacity[str(i)])
                    for i in self.stations_list
                    if self.delta_ia.get(a, {}).get(str(i), 0))* self.tolerance
                self._resource_coeff[(o,d,a)] = sig
        
        # Build the core rows and car arcs once
        self._build_core()
    
    
    def _build_core(self):

        """Builds γ vars, car arcs, demand balances, station capacity rows, and SD equality."""

        for (o,d) in self.W:
            self.gamma[(o,d)] = self.m.addVar(lb=-GRB.INFINITY, ub = GRB.INFINITY, vtype=GRB.CONTINUOUS, name = f"gamma_{o}_{d}")
        
        for (o,d) in self.W:
            od=f"{o}_{d}"
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                self.q[(o,d,a)] = self.m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name = f"q_{o}_{d}_{a}")

        self.m.update()

        # Demand conservation constraints (setup)

        for (o,d) in self.W:
            expr = gp.LinExpr()
            od=f"{o}_{d}"
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                expr.add(self.q[(o,d,a)], 1)
            self.dem_eq[(o,d)] = self.m.addConstr(expr == self.demands[(o,d)], name=f"demand_{o}_{d}")
        
        #station capacities constraints (setup)
        for i in self.stations_list:
            i_str=str(i)
            cap_i = self.station_capacity[i_str]
            inv_i = self.station_inventory[i_str]
            self.cap_constr[i_str] = self.m.addConstr(0 <= cap_i - inv_i, name=f"StationCap_{i_str}")
            self.cap_nonneg[i_str]   = self.m.addConstr(inv_i >= 0.0,        name=f"StationCap_nonneg_{i_str}")

        #strong duality constraints (setup) for pt only and pt bike
        self.sd_constr = self.m.addConstr(0.0 == 0.0, name="StrongDuality")
        for (o, d) in self.W:
            self.m.chgCoeff(self.sd_constr, self.gamma[(o, d)], -float(self.demands[(o, d)]))

        #duality and strong duality(setup)  for cars

        for (o,d) in self.W:
            od=f"{o}_{d}"
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                qv = self.q[(o,d,a)]
                F = self.total_cost_car[(o,d,a)]
                Tt = self.travel_time[(o,d,a)]

                #Add Dual feasibility for car arcs
                rhs = (self.ASC_CAR
                       +self.BETA_Cost_Car*(F-self.dep_cost)
                       +self.BETA_Time_Car*Tt
                       +self.BETA_Cost_park*self.parking_fee               
                       )
                self.m.addConstr(self.gamma[(o,d)] <= rhs, name = f"gamma_car_{o}_{d}_{a}")
                
                #add q_b^o,d *V_b^o,d to Strong Duality LHS
                coeff_sd = (self.ASC_CAR
                       +self.BETA_Cost_Car*(F-self.dep_cost)
                       +self.BETA_Time_Car*Tt
                       +self.BETA_Cost_park*self.parking_fee)
                self.m.chgCoeff(self.sd_constr,qv,coeff_sd)
        
        self.m.update()

    def add_pt_only(self, o,d,a):

        """Add PT-only arc (o,d,a) and its constraints to the model"""

        if (o, d, a) in self._present_A2:
            return
        self._present_A2.add((o,d,a))

        Qod = self.demands[(o,d)]
        q = self.m.addVar(lb = 0, ub = Qod, vtype=GRB.CONTINUOUS, name = f"q_{o}_{d}_{a}")
        self.q[(o,d,a)] = q
        
        #Add Dual feasibility for pt only arcs

        rhs = ( self.ASC_PT
              + self.BETA_Cost_PT * self.pt_price
              + self.BETA_Time_PT * self.pt_time[(o, d, a)]
              + self.BETA_TR_PT   * self.transfers[(o, d, a)] )
        
        self.gamma_rows[(o,d,a)] = self.m.addConstr(self.gamma[(o, d)] <= rhs, name=f"gammaPT_{o}_{d}_{a}")

        #add q_a^o,d *V_a^o,d to Strong Duality LHS for pt only arcs

        coeff_sd_q = ( self.BETA_Cost_PT * self.pt_price
                     + self.BETA_Time_PT * self.pt_time[(o, d, a)]
                     + self.BETA_TR_PT   * self.transfers[(o, d, a)]
                     + self.ASC_PT )
        self.m.chgCoeff(self.sd_constr, q, coeff_sd_q)

        #add pt only flow to flow conservation constraints

        self.m.chgCoeff(self.dem_eq[(o, d)], q, +1.0)

        #exclude pt only flow from obj
        q.setAttr(GRB.Attr.Obj, 0)
        self.m.update()

    def add_pt_bike(self, o,d,a):
        
        """Add PT+Bike arc (o,d,a) and its constraints with price and McCormick linearization."""

        if (o,d,a) in self._present_A1:
            return
        self._present_A1.add((o,d,a))

        Qod = self.demands[(o,d)]
        Pup = self.P_up_arc.get((o,d,a), self.P_up)

        p = self.m.addVar(lb=self.P_bar, ub=Pup, vtype=GRB.CONTINUOUS, name=f"p_{o}_{d}_{a}")
        q = self.m.addVar(lb = 0, ub = Qod, vtype=GRB.CONTINUOUS, name = f"q_{o}_{d}_{a}")
        z = self.m.addVar(lb = -GRB.INFINITY, ub = GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"z_{o}_{d}_{a}")

        self.p[(o,d,a)], self.q[(o,d,a)], self.z[(o,d,a)] = p, q, z

        #McCormick Envelopes for z = p*q with bounds known, (ν=1 implicitly for included arcs, no need for it in the constraints)
        self.m.addConstr(z >= self.P_bar * q,                        name=f"z_min1_{o}_{d}_{a}")
        self.m.addConstr(z <= Pup  * q,                        name=f"z_max1_{o}_{d}_{a}")
        self.m.addConstr(z >= Pup*q + p*Qod - Pup*Qod,   name=f"z_min2_{o}_{d}_{a}")
        self.m.addConstr(z <= p*Qod + self.P_bar*q - self.P_bar*Qod, name=f"z_max2_{o}_{d}_{a}")

        # Dual feasibility for pt+bike arcs

        rhs = ( self.ASC_BIKE + self.ASC_PT
              + self.BETA_Cost_PT   * self.pt_price
              + self.BETA_Cost_BIKE * self.k_bike_legs[(o,d,a)] * p
              + self.BETA_Time_PT   * self.pt_time[(o, d, a)]
              + self.BETA_Time_BIKE * self.bike_time.get((o, d, a), 0.0)
              + self.BETA_TR_BIKE   * self.transfers[(o, d, a)] )
        self.gamma_rows[(o, d, a)] = self.m.addConstr(self.gamma[(o, d)] <= rhs, name=f"gammaA_{o}_{d}_{a}")

        #Capacity constraints updated with pt+bike arcs

        self.m.chgCoeff(self.dem_eq[(o,d)], q, +1)
        for i_str, delta in self.delta_ia.get(a, {}).items():
            if delta:
                self.m.chgCoeff(self.cap_constr[i_str], q, delta)
                self.m.chgCoeff(self.cap_nonneg[i_str], q, delta)
        
        #add q_a^o,d *V_a^o,d to Strong Duality LHS for pt+bike arcs

        coeff_sd_q = ( self.ASC_BIKE + self.ASC_PT
                     + self.BETA_Cost_PT * self.pt_price
                     + self.BETA_Time_PT * self.pt_time[(o, d, a)]
                     + self.BETA_Time_BIKE * self.bike_time.get((o, d, a), 0.0)
                     + self.BETA_TR_BIKE   * self.transfers[(o, d, a)])
        self.m.chgCoeff(self.sd_constr, q, coeff_sd_q)
        self.m.chgCoeff(self.sd_constr, z, self.BETA_Cost_BIKE * self.k_bike_legs[(o,d,a)])

        #add pt+bike stuff to objective
        ridership_coeff = 2 * self.P_up
        resource_coeff  = self._resource_coeff.get((o, d, a), 0.0)

        z.setAttr(GRB.Attr.Obj, float(self.k_bike_legs[(o,d,a)]))
        q.setAttr(GRB.Attr.Obj, ridership_coeff - self.cost_bike*float(self.k_bike_legs[(o,d,a)]) + self.theta * resource_coeff)

        self.m.update()

    # -------- deactivate operations --------

    def deactivate_pt_bike(self, o, d, a, bigM_gamma:float = 1e9):
        """
        Deactivate PT+Bike arc (o,d,a) without deleting:
        - fix q,p,z to zero
        - relax its γ-row so it cannot bind
        - remove its SD coefficients
        - used for flipping an additional alternative next in line to evaluate participation to obj. 
        - This func is used for removing effect of the arc.
        """

        if (o, d, a) not in self._present_A1:
            return
        m = self.m
        q = self.q[(o, d, a)]; p = self.p[(o, d, a)]; z = self.z[(o, d, a)]
        # fix vars
        q.LB = 0.0; q.UB = 0.0
        p.LB = 0.0; p.UB = 0.0
        z.LB = 0.0; z.UB = 0.0
        # relax γ-row
        crow = self.gamma_rows.get((o, d, a))
        if crow is not None:
            try:
                m.chgCoeff(crow, q, 0.0)
                m.chgCoeff(crow, p, 0.0)
                m.chgCoeff(crow, z, 0.0)
                crow.RHS = bigM_gamma
            except gp.GurobiError:
                m.addConstr(self.gamma[(o, d)] <= bigM_gamma, name=f"gammaLoose_{o}_{d}_{a}")
        # remove SD coefficients
        try:
            m.chgCoeff(self.sd_constr, q, 0.0)
            m.chgCoeff(self.sd_constr, z, 0.0)
        except gp.GurobiError:
            pass
        m.update()

    def deactivate_pt_only(self, o, d, a, bigM_gamma: float = 1e9):
        """
        Deactivate PT-only arc (o,d,a):
        - fix q to zero
        - relax its γ-row so it cannot bind
        - remove its SD coefficients
        """
        if (o, d, a) not in self._present_A2:
            return
        m = self.m
        q = self.q[(o, d, a)]
        q.LB = 0.0; q.UB = 0.0
        crow = self.gamma_rows.get((o, d, a))
        if crow is not None:
            try:
                m.chgCoeff(crow, q, 0.0)
                crow.RHS = bigM_gamma
            except gp.GurobiError:
                m.addConstr(self.gamma[(o, d)] <= bigM_gamma, name=f"gammaLoosePT_{o}_{d}_{a}")
        try:
            m.chgCoeff(self.sd_constr, q, 0.0)
        except gp.GurobiError:
            pass
        m.update()

    # -------- solve & reporting --------

    def optimize(self):
        self.m.optimize()
        return float(self.m.ObjVal) if self.m.SolCount > 0 else None
    
    def objective_value(self):
        return float(self.m.ObjVal) if self.m.SolCount > 0 else None
    
    def solution_summary(self):
        return {"Objective Value": self.objective_value(),
                "SolCount": int(self.m.SolCount),
                "Status": int(self.m.Status)}
    
    def extract_solution_df(self,q_tol:float = 0):

        """
        Build the per-arc records similar to your original 'solution_df'.
        q_tol: include arcs with q >= q_tol (set to 0.0 to list everything).
        """
        rows = []
        # per-OD header (gamma)
        for (o, d) in self.W:
            rows.append({
                "Instance OD": f"{o}->{d}",
                "OD":          f"{o}->{d}",
                "gamma":       self.gamma[(o, d)].X,
            })

            od = f"{o}_{d}"

            # PT+Bike arcs currently present
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                key = (o, d, a)
                if key not in self._present_A1:
                    continue
                qv = self.q[key].X
                if qv < q_tol:
                    continue
                pv = self.p[key].X
                zv = self.z[key].X
                rows.append({
                    "OD":            f"{o}->{d}",
                    "Arc ID":        a,
                    "Type":          "PT+Bike",
                    "nu":            1,  # implicitly "on" because present
                    "Flow (q)":      qv,
                    "Bike Price":    pv,
                    "Total Price":   pv + self.pt_price,
                    "PT Time":       self.pt_time[(o, d, a)],
                    "Bike Time":     self.bike_time.get((o, d, a), 0.0),
                    "Transfers":     self.transfers[(o, d, a)],
                    "z value":       zv,
                    "Relaxation Difference": zv - pv * qv
                })

            # PT-only arcs currently present
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                key = (o, d, a)
                if key not in self._present_A2:
                    continue
                qv = self.q[key].X
                if qv < q_tol:
                    continue
                rows.append({
                    "OD":            f"{o}->{d}",
                    "Arc ID":        a,
                    "Type":          "PT-Only",
                    "nu":            1,
                    "Flow (q)":      qv,
                    "Bike Price":    0.0,
                    "Total Price":   self.pt_price,
                    "PT Time":       self.pt_time[(o, d, a)],
                    "Bike Time":     0.0,
                    "Transfers":     self.transfers[(o, d, a)],
                    "z value":       0.0,
                    "Relaxation Difference": 0.0
                })

            # Car arcs (always present)
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                qv = self.q[(o, d, a)].X
                if qv < q_tol:
                    continue
                rows.append({
                    "OD":                     f"{o}->{d}",
                    "Arc ID":                 a,
                    "Type":                   "Car",
                    "nu":                     0,
                    "Flow (q)":               qv,
                    "Bike Price":             0.0,
                    "Total Price":            self.total_cost_car[(o, d, a)],
                    "PT Time":                0.0,
                    "Bike Time":              0.0,
                    "Transfers":              self.transfers[(o, d, a)],
                    "Parking Time (min)":     self.parking_time[(o, d, a)],
                    "Total Travel Time (min)": self.travel_time[(o, d, a)]
                })

        return rows
    # ---------- DEBUG: quick counts / totals ----------
    def _debug_count_present(self):
        return len(self._present_A1), len(self._present_A2)

    def _debug_totals_by_mode(self, q_tol: float = 0.0):
        """Return totals of q by PT+Bike, PT-only, Car."""
        tot_a1 = tot_a2 = tot_car = 0.0
        for (o, d) in self.W:
            od = f"{o}_{d}"
            # A1
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                if (o, d, a) in self._present_A1:
                    qv = self.q[(o, d, a)].X if (o, d, a) in self.q else 0.0
                    if qv >= q_tol:
                        tot_a1 += qv
            # A2
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                if (o, d, a) in self._present_A2:
                    qv = self.q[(o, d, a)].X if (o, d, a) in self.q else 0.0
                    if qv >= q_tol:
                        tot_a2 += qv
            # Car
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                qv = self.q[(o, d, a)].X if (o, d, a) in self.q else 0.0
                if qv >= q_tol:
                    tot_car += qv
        return tot_a1, tot_a2, tot_car

    def _debug_station_slacks(self):
        """Compute used slack per station from flows (sum q * delta)."""
        used = {str(i): 0.0 for i in self.stations_list}
        inflow = {str(i): 0.0 for i in self.stations_list}    # bikes added to station
        outflow = {str(i): 0.0 for i in self.stations_list}   # bikes taken from station
        for (o, d) in self.W:
            od = f"{o}_{d}"
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                if (o, d, a) not in self._present_A1:
                    continue
                qv = self.q[(o, d, a)].X if (o, d, a) in self.q else 0.0
                if qv == 0.0:
                    continue
                for i_str, delta in self.delta_ia.get(a, {}).items():
                    if delta:
                        flow_contribution = qv * delta
                        used[i_str] += flow_contribution
                        
                        if flow_contribution > 0:
                            inflow[i_str] += flow_contribution
                        else:
                            outflow[i_str] += abs(flow_contribution)
        report = []
        for i_str in used:
            cap_i = self.station_capacity[i_str]
            inv_i = self.station_inventory[i_str]
            slack_up = cap_i - inv_i
            report.append((i_str, used[i_str], slack_up, inflow[i_str], outflow[i_str]))
        return sorted(report, key=lambda t: t[0])

    # ---------- DEBUG: check SD equality numerically ----------
    def debug_check_strong_duality(self, echo_first_k=3):
        """
        Recompute SD LHS and RHS at current solution and print the residual.
        LHS = sum over all arcs present [ q * (ASC + time terms + PT cost) + z * BETA_Cost_BIKE ]
            + sum over car arcs [ q * (ASC_CAR + time + cost terms) ]
        RHS = sum_{OD} Q_od * gamma_od
        NOTE: uses the same coefficients as when we built rows.
        """
        if self.m.SolCount == 0:
            print("[SD] No solution yet.")
            return

        LHS = 0.0
        # cars
        for (o, d) in self.W:
            od = f"{o}_{d}"
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                qv = self.q[(o, d, a)].X
                F = self.total_cost_car[(o, d, a)]
                Tt = self.travel_time[(o, d, a)]
                term = (self.ASC_CAR
                        + self.BETA_Cost_Car * (F - self.dep_cost)
                        + self.BETA_Time_Car * Tt
                        + self.BETA_Cost_park * self.parking_fee)
                LHS += qv * term

        # PT-only present
        for (o, d) in self.W:
            od = f"{o}_{d}"
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                if (o, d, a) not in self._present_A2:
                    continue
                qv = self.q[(o, d, a)].X
                term = ( self.ASC_PT
                        + self.BETA_Cost_PT * self.pt_price
                        + self.BETA_Time_PT * self.pt_time[(o, d, a)]
                        + self.BETA_TR_PT   * self.transfers[(o, d, a)] )
                LHS += qv * term

        # PT+Bike present
        for (o, d) in self.W:
            od = f"{o}_{d}"
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                if (o, d, a) not in self._present_A1:
                    continue
                qv = self.q[(o, d, a)].X
                zv = self.z[(o, d, a)].X
                term_q = ( self.ASC_BIKE + self.ASC_PT
                        + self.BETA_Cost_PT * self.pt_price
                        + self.BETA_Time_PT * self.pt_time[(o, d, a)]
                        + self.BETA_Time_BIKE * self.bike_time.get((o, d, a), 0.0)
                        + self.BETA_TR_BIKE   * self.transfers[(o, d, a)] )
                LHS += qv * term_q + zv * self.BETA_Cost_BIKE

        RHS = 0.0
        for (o, d) in self.W:
            RHS += self.demands[(o, d)] * self.gamma[(o, d)].X

        resid = LHS - RHS
        print(f"[SD] LHS={LHS:.6f}  RHS={RHS:.6f}  (LHS-RHS)={resid:.6e}")
        if abs(resid) > 1e-4:
            print("      WARNING: strong duality residual is not tiny; check coefficients & chgCoeff wiring.")

        # show a couple of ODs to see gamma vs best RHS
        shown = 0
        for (o, d) in self.W:
            if shown >= echo_first_k:
                break
            g = self.gamma[(o, d)].X
            print(f"   gamma[{o},{d}] = {g:.6f}")
            shown += 1

    # ---------- DEBUG: print initial build counts + after-solve summary ----------
    def debug_after_opt(self, label=""):
        """Prints what we actually added and how flow split looks like."""
        if self.m.SolCount == 0:
            print(f"[{label}] No solution yet.")
            return
        nA1, nA2 = self._debug_count_present()
        tot_a1, tot_a2, tot_car = self._debug_totals_by_mode(q_tol=0.0)
        print(f"[{label}] present A1={nA1}  A2={nA2}  | totals  A1={tot_a1:.3f}  A2={tot_a2:.3f}  Car={tot_car:.3f}")
        # station usage
        station_report = self._debug_station_slacks()
        active_stations = [(i, u, s, inf, outf) for (i, u, s, inf, outf) in station_report if inf > 1e-9 or outf > 1e-9]
        total_inflow = sum(inf for _, _, _, inf, _ in active_stations)
        total_outflow = sum(outf for _, _, _, _, outf in active_stations)
        
        print(f"[{label}] stations with bike activity: {len(active_stations)} / {len(station_report)}")
        print(f"[{label}] total inflow: {total_inflow:.3f}, total outflow: {total_outflow:.3f}")




    def get_station_lambdas(lp) -> dict[str, float]:
        """
        lp is your IncrementalBilevelLP instance.
        Returns lambda_eff[i] = cap_dual(i) - nonneg_dual(i), handling signs.
        """
        m = lp.m
        lam = {}
        for i in lp.stations_list:
            i_str = str(i)
            pi_up  = lp.cap_constr[i_str].Pi               # ≥ 0 for a ≤ row in a max model
            pi_loG = lp.cap_nonneg[i_str].Pi               # ≤ 0 for a ≥ row in a max model
            rho    = -pi_loG                                # make it ≥ 0
            lam[i_str] = pi_up - rho
        return lam



