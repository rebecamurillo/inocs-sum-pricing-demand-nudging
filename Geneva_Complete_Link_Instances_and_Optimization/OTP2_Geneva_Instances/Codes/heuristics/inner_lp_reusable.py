# inner_lp_reusable.py
from __future__ import annotations
from typing import Dict, Tuple, Any
import gurobipy as gp
from gurobipy import GRB

class ReusableInnerLP:
    """
    Build the single-level LP once. For each GA chromosome ν, only update:
      - bounds of p and q (based on ν)
      - RHS of the two McCormick constraints that include ν
    Then re-optimize with dual simplex to reuse the basis.
    """

    def __init__(self, parsed_data: dict,
                 P_bar: float = 0.5, P_up: float = 4.0, pt_price: float = 2.0,
                 cost_bike: float = 0.6, parking_fee: float = 2.8,
                 dep_cost: float = 0.0,
                 method: int = 1,  # 1 = Dual Simplex (good for repeated re-solves)
                 output_flag: int = 0):
        self.data = parsed_data
        self.P_bar = P_bar
        self.P_up = P_up
        self.pt_price = pt_price
        self.cost_bike = cost_bike
        self.parking_fee = parking_fee
        self.dep_cost = dep_cost

        self.model = gp.Model("InnerLP_Reused")
        self.model.Params.Method = method
        self.model.Params.OutputFlag = output_flag
        self.model.Params.Presolve = 2

        # Handles to vars/cons we’ll update fast
        self.gamma = {}     # (o,d) -> Var
        self.q = {}         # (o,d,a) -> Var (A1 + A2 + car B)
        self.p = {}         # (o,d,a) -> Var (A1 only)
        self.z = {}         # (o,d,a) -> Var (A1 only)

        # RHS-updatable constraints for McCormick that include ν
        self.con_z_min2 = {}   # (o,d,a) : z - M q - Q p >= -M Q ν
        self.con_z_max2 = {}   # (o,d,a) : z - Q p - Pbar q <= -Pbar Q ν

        # Static data shortcuts (avoid dict lookups in hot path)
        D = self.data
        self.W = D["OD_pairs"]
        self.demands = D["demands"]
        self.arcs_pt_bike = D["arcs_pt_bike"]
        self.arcs_pt_only = D["arcs_pt_only"]
        self.car_paths = D["car_paths"]
        self.stations_list = D["stations_list"]
        self.station_capacity = D["station_capacity"]
        self.station_inventory = D["station_inventory"]
        self.delta_ia = D["delta_ia"]
        self.bike_time = D["bike_time_min"]
        self.pt_time = D["pt_time_min"]
        self.transfers = D["transfer_time_min"]
        self.parking_time = D["parking_time_min"]
        self.total_cost_car = D["total_cost_car"]
        self.travel_time = D["travel_time_min"]

        # Taste coeffs / ASCs (mirror your current values)
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

        # Precompute per-arc coefficients
        self.asc_bike = {}
        self.asc_pt   = {}
        self.asc_car  = {}
        self.beta_cost_bike = {}
        self.beta_cost_pt   = {}
        self.beta_biketime  = {}
        self.beta_pttime    = {}
        self.beta_tr_pt     = {}
        self.beta_tr_bike   = {}
        self.beta_cost_car  = {}
        self.beta_cost_park = {}
        self.beta_time_car  = {}

        for (o, d) in self.W:
            od = f"{o}_{d}"
            # A1: PT+Bike
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                self.asc_bike[(o,d,a)] = ASC_BIKE
                self.asc_pt[(o,d,a)]   = ASC_PT
                self.beta_cost_bike[(o,d,a)] = BETA_Cost_BIKE
                self.beta_biketime[(o,d,a)]  = BETA_Time_BIKE
                self.beta_pttime[(o,d,a)]    = BETA_Time_PT
                self.beta_tr_pt[(o,d,a)]     = BETA_TR_PT
                self.beta_tr_bike[(o,d,a)]   = BETA_TR_BIKE
                self.beta_cost_pt[(o,d,a)]   = BETA_Cost_PT
            # A2: PT-only
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                self.asc_pt[(o,d,a)]   = ASC_PT
                self.beta_pttime[(o,d,a)]  = BETA_Time_PT
                self.beta_tr_pt[(o,d,a)]   = BETA_TR_PT
                self.beta_cost_pt[(o,d,a)] = BETA_Cost_PT
            # B: car
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                self.asc_car[(o,d,a)]      = ASC_CAR
                self.beta_cost_car[(o,d,a)]  = BETA_Cost_Car
                self.beta_cost_park[(o,d,a)] = BETA_Cost_park
                self.beta_time_car[(o,d,a)]  = BETA_Time_Car

        self._build_model()

    def _build_model(self):
        m = self.model
        D = self.data

        # gamma vars per OD
        for (o,d) in self.W:
            self.gamma[(o,d)] = m.addVar(lb=-gp.GRB.INFINITY, ub=gp.GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"gamma_{o}_{d}")

        # Decision vars
        for (o,d) in self.W:
            od = f"{o}_{d}"
            # A1: PT+Bike (p, q, z)
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                # Defaults: we’ll tighten bounds per design later
                self.p[(o,d,a)]  = m.addVar(lb=0.0, ub=self.P_up, vtype=GRB.CONTINUOUS, name=f"p_{o}_{d}_{a}")
                self.q[(o,d,a)]  = m.addVar(lb=0.0, ub=self.demands[(o,d)], vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{a}")
                self.z[(o,d,a)]  = m.addVar(lb=-gp.GRB.INFINITY, ub=gp.GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"z_{o}_{d}_{a}")
            # A2: PT-only (q)
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                self.q[(o,d,a)]  = m.addVar(lb=0.0, ub=self.demands[(o,d)], vtype=GRB.CONTINUOUS, name=f"q_{o}_{d}_{a}")
            # B: car (q)
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                self.q[(o,d,a)]  = m.addVar(lb=0.0, ub=self.demands[(o,d)], vtype=GRB.CONTINUOUS, name=f"qcar_{o}_{d}_{a}")

        m.update()

        # (1) Station capacities (PT+Bike only)
        for i in self.stations_list:
            i_str = str(i)
            cap_i = self.station_capacity[i_str]
            inv_i = self.station_inventory[i_str]
            lhs = gp.LinExpr()
            for (o,d) in self.W:
                od = f"{o}_{d}"
                for arc in self.arcs_pt_bike.get(od, []):
                    a = arc["arc_id"]
                    delta = self.delta_ia.get(a, {}).get(i_str, 0.0)
                    if delta:
                        lhs.add(self.q[(o,d,a)], delta)
            m.addConstr(lhs <= cap_i - inv_i, name=f"StationCap_{i}")
            m.addConstr(lhs + inv_i >= 0,     name=f"StationCap_nonneg_{i}")

        # (2) Demand conservation
        for (o,d) in self.W:
            od = f"{o}_{d}"
            lhs = gp.quicksum(self.q[(o,d,arc["arc_id"])] for arc in self.arcs_pt_bike.get(od, []))
            lhs += gp.quicksum(self.q[(o,d,arc["arc_id"])] for arc in self.arcs_pt_only.get(od, []))
            lhs += gp.quicksum(self.q[(o,d,arc["arc_id"])] for arc in self.car_paths.get(od, []))
            m.addConstr(lhs == self.demands[(o,d)], name=f"demand_{o}_{d}")

        # (3) gamma constraints (UNGATED version; see notes for gating)
        for (o,d) in self.W:
            od = f"{o}_{d}"
            g = self.gamma[(o,d)]
            # PT+Bike arcs
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                rhs = ( self.asc_bike[(o,d,a)] + self.asc_pt[(o,d,a)]
                        + self.beta_cost_pt[(o,d,a)] * self.pt_price
                        + self.beta_cost_bike[(o,d,a)] * self.p[(o,d,a)]
                        + self.beta_pttime[(o,d,a)] * self.pt_time[(o,d,a)]
                        + self.beta_biketime[(o,d,a)] * self.bike_time.get((o,d,a), 0.0)
                        + self.beta_tr_bike[(o,d,a)] * self.transfers[(o,d,a)] )
                m.addConstr(g <= rhs, name=f"gammaA_{o}_{d}_{a}")
            # PT-only arcs
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                rhs = ( self.asc_pt[(o,d,a)]
                        + self.beta_cost_pt[(o,d,a)] * self.pt_price
                        + self.beta_pttime[(o,d,a)] * self.pt_time[(o,d,a)]
                        + self.beta_tr_pt[(o,d,a)]   * self.transfers[(o,d,a)] )
                m.addConstr(g <= rhs, name=f"gammaPT_{o}_{d}_{a}")
            # Car arcs
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                F  = self.total_cost_car[(o,d,a)]
                Tt = self.travel_time[(o,d,a)]
                rhs = ( self.asc_car[(o,d,a)]
                        + self.beta_cost_car[(o,d,a)]  * (F - self.dep_cost)
                        + self.beta_cost_park[(o,d,a)] * self.parking_fee
                        + self.beta_time_car[(o,d,a)]  * Tt )
                m.addConstr(g <= rhs, name=f"gammaCar_{o}_{d}_{a}")

        # (4) Strong duality equality
        lhs_sd = gp.LinExpr()
        for (o,d) in self.W:
            od = f"{o}_{d}"
            # A1
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                q = self.q[(o,d,a)]
                z = self.z[(o,d,a)]
                lhs_sd.add(q, self.beta_cost_pt[(o,d,a)] * self.pt_price)
                lhs_sd.add(z, self.beta_cost_bike[(o,d,a)])
                lhs_sd.add(q, self.beta_pttime[(o,d,a)] * self.pt_time[(o,d,a)])
                lhs_sd.add(q, self.beta_biketime[(o,d,a)] * self.bike_time.get((o,d,a), 0.0))
                lhs_sd.add(q, self.beta_tr_bike[(o,d,a)] * self.transfers[(o,d,a)])
                lhs_sd.add(q, self.asc_bike[(o,d,a)] + self.asc_pt[(o,d,a)])
            # A2
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                q = self.q[(o,d,a)]
                lhs_sd.add(q, self.beta_cost_pt[(o,d,a)] * self.pt_price)
                lhs_sd.add(q, self.beta_pttime[(o,d,a)] * self.pt_time[(o,d,a)])
                lhs_sd.add(q, self.beta_tr_pt[(o,d,a)]   * self.transfers[(o,d,a)])
                lhs_sd.add(q, self.asc_pt[(o,d,a)])
            # B
            for arc in self.car_paths.get(od, []):
                a = arc["arc_id"]
                q = self.q[(o,d,a)]
                F  = self.total_cost_car[(o,d,a)]
                Tt = self.travel_time[(o,d,a)]
                lhs_sd.add(q, self.beta_cost_car[(o,d,a)]  * (F - self.dep_cost))
                lhs_sd.add(q, self.beta_cost_park[(o,d,a)] * self.parking_fee)
                lhs_sd.add(q, self.beta_time_car[(o,d,a)]  * Tt)
                lhs_sd.add(q, self.asc_car[(o,d,a)])
        rhs_sd = gp.quicksum(self.demands[(o,d)] * self.gamma[(o,d)] for (o,d) in self.W)
        m.addConstr(lhs_sd == rhs_sd, name="StrongDuality")

        # (5) McCormick constraints (the two with ν-free RHS; the two with ν on RHS)
        for (o,d) in self.W:
            od = f"{o}_{d}"
            Qod = self.demands[(o,d)]
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                q = self.q[(o,d,a)]
                p = self.p[(o,d,a)]
                z = self.z[(o,d,a)]
                # z >= Pbar q
                m.addConstr(z >= self.P_bar * q, name=f"z_min1_{o}_{d}_{a}")
                # z <= M q
                m.addConstr(z <= self.P_up * q, name=f"z_max1_{o}_{d}_{a}")
                # z - M q - Q p >= - M Q ν   [RHS updates per design]
                c1 = m.addConstr(z - self.P_up*q - Qod*p >= 0.0, name=f"z_min2_{o}_{d}_{a}")
                # z - Q p - Pbar q <= - Pbar Q ν  [RHS updates per design]
                c2 = m.addConstr(z - Qod*p - self.P_bar*q <= 0.0, name=f"z_max2_{o}_{d}_{a}")
                self.con_z_min2[(o,d,a)] = c1
                self.con_z_max2[(o,d,a)] = c2

        # Objective: same as your LP (no slack here)
        tolerance = 1e-3
        ridership = gp.quicksum(2*self.P_up * self.q[(o,d,arc["arc_id"])]
                                for (o,d) in self.W for arc in self.arcs_pt_bike.get(f"{o}_{d}", []))
        revenue   = gp.quicksum(self.z[(o,d,arc["arc_id"])]
                                for (o,d) in self.W for arc in self.arcs_pt_bike.get(f"{o}_{d}", []))
        cost      = gp.quicksum(self.cost_bike * self.q[(o,d,arc["arc_id"])]
                                for (o,d) in self.W for arc in self.arcs_pt_bike.get(f"{o}_{d}", []))
        res_man   = gp.quicksum(
                        self.q[(o,d,arc["arc_id"])] * tolerance *
                        gp.quicksum(self.delta_ia.get(arc["arc_id"], {}).get(str(i), 0) *
                                    (1 - self.station_inventory[str(i)] / self.station_capacity[str(i)])
                                    for i in self.stations_list
                                    if self.delta_ia.get(arc["arc_id"], {}).get(str(i), 0))
                        for (o,d) in self.W for arc in self.arcs_pt_bike.get(f"{o}_{d}", []))

        m.setObjective(ridership + revenue - cost + res_man, GRB.MAXIMIZE)
        m.update()

    # --- Hot path: apply GA design and solve ---
    def evaluate(self, bits: list[int], nu_keys: list[Tuple], time_limit: int | None = None) -> float:
        """
        Apply ν (from bits) by updating bounds/RHS, then re-solve.
        Returns the objective value (float) or -inf if no solution.
        """
        # Map bits -> ν
        nu = {nu_keys[i]: int(bits[i]) for i in range(len(nu_keys))}

        # Update bounds and RHS
        for (o,d) in self.W:
            od = f"{o}_{d}"
            Qod = self.demands[(o,d)]
            # A1: PT+Bike
            for arc in self.arcs_pt_bike.get(od, []):
                a = arc["arc_id"]
                ν = nu.get((o,d,a), 0)
                # q upper bound
                self.q[(o,d,a)].UB = Qod * ν
                # p bounds
                if ν == 0:
                    self.p[(o,d,a)].LB = 0.0
                    self.p[(o,d,a)].UB = 0.0
                else:
                    self.p[(o,d,a)].LB = self.P_bar
                    self.p[(o,d,a)].UB = self.P_up
                # McCormick RHS updates
                # z - M q - Q p >= - M Q ν
                self.con_z_min2[(o,d,a)].RHS = - self.P_up * Qod * ν
                # z - Q p - Pbar q <= - Pbar Q ν
                self.con_z_max2[(o,d,a)].RHS = - self.P_bar * Qod * ν
            # A2: PT-only
            for arc in self.arcs_pt_only.get(od, []):
                a = arc["arc_id"]
                ν = nu.get((o,d,a), 0)
                self.q[(o,d,a)].UB = Qod * ν
            # B: car unchanged

        if time_limit is not None:
            self.model.Params.TimeLimit = time_limit

        # Re-optimize; reuses previous basis automatically with dual simplex
        self.model.optimize()

        if getattr(self.model, "SolCount", 0) > 0:
            try:
                return float(self.model.ObjVal)
            except Exception:
                return float("-inf")
        return float("-inf")
