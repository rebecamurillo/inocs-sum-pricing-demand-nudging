# tabu_pipeline.py
import heapq
import time
from typing import Optional, Dict, List, Tuple
from collections import deque
import gurobipy as gp
from gurobipy import GRB

from incremental_lp import IncrementalBilevelLP

# ------------------ local scoring (same coefficients as your model) ------------------

ASC_PT, ASC_BIKE, ASC_CAR = -0.756, 0.0, -0.669
B_PT, B_TRPT   = 0.101, 0.208
B_BIKE, B_TRB  = 0.108, 0.199
B_CPT, B_CB    = 0.779, 0.689
B_CC, B_CP, B_CT = 0.474, 0.532, 0.116

def score_pt_only(parsed, o, d, a, *, pt_price: float) -> float:
    return (ASC_PT
            + B_CPT * pt_price
            + B_PT  * parsed["pt_time_min"][(o, d, a)]
            + B_TRPT* parsed["transfer_time_min"][(o, d, a)])

def score_car(parsed, o, d, a, *, dep_cost: float, parking_fee: float) -> float:
    F  = parsed["total_cost_car"][(o, d, a)]
    Tt = parsed["travel_time_min"][(o, d, a)]
    return (ASC_CAR
            + B_CC*(F - dep_cost)
            + B_CP*parking_fee
            + B_CT*Tt)

def score_a1_at_p(parsed, o, d, a, *, pt_price: float, p_val: float) -> float:
    return (ASC_PT + ASC_BIKE
            + B_CPT * pt_price
            + B_CB  * p_val
            + B_PT  * parsed["pt_time_min"][(o, d, a)]
            + B_BIKE* parsed["bike_time_min"].get((o, d, a), 0.0)
            + B_TRB * parsed["transfer_time_min"][(o, d, a)])


# ------------------ initial selection (self-contained) ------------------

def initial_selection_pt_and_a1_vs_pt_car(
    parsed, *,
    K_PT: int,
    L: int,
    mult_A1: int,
    P_bar: float,
    pt_price: float,
    dep_cost: float,
    parking_fee: float,
) -> Dict[Tuple[int,int], Dict[str, List[str]]]:
    """
    For each OD:
      - keep top-K PT-only (with fare)
      - benchmark = min(best PT-only, best Car)
      - keep A1 whose score at p=P_bar beats the benchmark; cap to max(L, mult_A1*L)
    """
    sel: Dict[Tuple[int,int], Dict[str, List[str]]] = {}
    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"

        # PT-only
        A2 = []
        best_PT = float("inf")
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            s = score_pt_only(parsed, o, d, a, pt_price=pt_price)
            A2.append((s, a))
            if s < best_PT: best_PT = s
        A2.sort(key=lambda t: t[0])
        kept_A2 = [a for _, a in A2[:K_PT]]

        # Car benchmark
        best_Car = float("inf")
        for arc in parsed["car_paths"].get(od, []):
            a = arc["arc_id"]
            s = score_car(parsed, o, d, a, dep_cost=dep_cost, parking_fee=parking_fee)
            if s < best_Car: best_Car = s

        benchmark = min(best_PT, best_Car)

        # A1 @ p=P_bar, keep only if beats benchmark
        A1 = []
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            s = score_a1_at_p(parsed, o, d, a, pt_price=pt_price, p_val=P_bar)
            if s < benchmark:
                A1.append((s, a))
        A1.sort(key=lambda t: t[0])
        cap = max(L, mult_A1 * L)
        kept_A1 = [a for _, a in A1[:cap]]

        sel[(o, d)] = {"A2": kept_A2, "A1": kept_A1}
    return sel


# ------------------ Tabu Search pipeline ------------------

class TabuSearchPipeline:
    """
    Independent tabu search that manipulates an IncrementalBilevelLP model.
    Moves: ADD A1, ADD A2, DROP A1 (no re-activation, by design).
    """

    def __init__(self,
                 parsed_data: dict, *,
                 L: int = 10, K_PT: int = 2, mult_A1: int = 2,
                 P_bar: float = 0.5, P_up: float = 4.0, pt_price: float = 2.0,
                 cost_bike: float = 0.6, parking_fee: float = 2.8, dep_cost: float = 0.0,
                 tolerance: float = 1e-3, theta: float = 0.5,
                 threads: int = 4, quiet: bool = True, time_limit_eval: Optional[int] = None,
                 # Tabu params
                 max_iters: int = 60, tenure: int = 7,
                 neigh_size_A1: int = 8, neigh_size_A2: int = 3,
                 stall_limit: int = 10,
                 diversify_drops: int = 1):
        self.parsed = parsed_data
        self.L, self.K_PT, self.mult_A1 = L, K_PT, mult_A1
        self.P_bar, self.P_up, self.pt_price = P_bar, P_up, pt_price
        self.cost_bike, self.parking_fee, self.dep_cost = cost_bike, parking_fee, dep_cost
        self.tolerance, self.theta = tolerance, theta

        # model
        self.lp = IncrementalBilevelLP(
            parsed_data,
            P_bar=P_bar, P_up=P_up, pt_price=pt_price,
            cost_bike=cost_bike, parking_fee=parking_fee, dep_cost=dep_cost,
            tolerance=tolerance, theta=theta,
            quiet=quiet, threads=threads, time_limit=time_limit_eval
        )

        # selections (our own bookkeeping for what's been added)
        self.sel = initial_selection_pt_and_a1_vs_pt_car(
            parsed_data, K_PT=K_PT, L=L, mult_A1=mult_A1,
            P_bar=P_bar, pt_price=pt_price, dep_cost=dep_cost, parking_fee=parking_fee
        )

        # tabu settings
        self.max_iters = max_iters
        self.tenure = tenure
        self.neigh_A1 = neigh_size_A1
        self.neigh_A2 = neigh_size_A2
        self.stall_limit = stall_limit
        self.diversify_drops = diversify_drops

        # tabu memory: (op, kind, o, d, a) -> iteration when it expires
        self.tabu_until: Dict[Tuple[str,str,int,int,str], int] = {}
        self.iter_idx = 0

        # best tracking
        self.best_obj: Optional[float] = None

    # ------------ initial build ------------
    def _build_initial(self):
        for (o, d), grp in self.sel.items():
            for a in grp["A2"]:
                self.lp.add_pt_only(o, d, a)
            for a in grp["A1"]:
                self.lp.add_pt_bike(o, d, a)

    # ------------ neighborhood ------------
    def _neighborhood(self) -> List[Tuple[str, str, int, int, str, float]]:
        """
        Build a small list of candidate moves:
          ("ADD","A1",o,d,a,score) or ("ADD","A2",o,d,a,score) or ("DROP","A1",o,d,a,meta)
        Returns a list sorted (best-first) using simple scoring for adds; drops are appended.
        """
        adds: List[Tuple[str,str,int,int,str,float]] = []
        # PT-only ADD candidates (top-neigh_A2 by PT score)
        for (o, d) in self.parsed["OD_pairs"]:
            od = f"{o}_{d}"
            pool = []
            for arc in self.parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a) in self.lp._present_A2:
                    continue
                s = score_pt_only(self.parsed, o, d, a, pt_price=self.pt_price)
                pool.append((s, a))
            pool.sort(key=lambda t: t[0])
            for s, a in pool[:self.neigh_A2]:
                adds.append(("ADD", "A2", o, d, a, s))

        # PT+Bike ADD candidates (rank by "gap" vs benchmark at p = P_bar)
        for (o, d) in self.parsed["OD_pairs"]:
            od = f"{o}_{d}"
            # compute benchmark min(best PT, best Car)
            best_PT = float("inf")
            for arc in self.parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                best_PT = min(best_PT, score_pt_only(self.parsed, o, d, a, pt_price=self.pt_price))
            best_Car = float("inf")
            for arc in self.parsed["car_paths"].get(od, []):
                a = arc["arc_id"]
                best_Car = min(best_Car, score_car(self.parsed, o, d, a, dep_cost=self.dep_cost, parking_fee=self.parking_fee))
            bench = min(best_PT, best_Car)

            pool = []
            for arc in self.parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a) in self.lp._present_A1:
                    continue
                s_a1 = score_a1_at_p(self.parsed, o, d, a, pt_price=self.pt_price, p_val=self.P_bar)
                gap = s_a1 - bench
                pool.append((gap, s_a1, a))
            pool.sort(key=lambda t: (t[0], t[1]))
            for gap, _s, a in pool[:self.neigh_A1]:
                adds.append(("ADD", "A1", o, d, a, gap))

        # sort adds by their score (lower better)
        adds.sort(key=lambda t: t[5])

        # DROP candidates: a few weakest A1 currently present
        drops: List[Tuple[str,str,int,int,str,Tuple[float,float]]] = []
        if self.lp.m.SolCount > 0:
            weak = []
            for (o, d, a) in list(self.lp._present_A1):
                qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
                zv = self.lp.z[(o, d, a)].X if (o, d, a) in self.lp.z else 0.0
                q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o, d, a), 0.0)
                contrib = zv + q_coeff * qv
                weak.append((qv, contrib, (o, d, a)))
            weak.sort(key=lambda t: (t[0], t[1]))
            for qv, contrib, (o, d, a) in weak[:max(1, self.neigh_A1//2)]:
                drops.append(("DROP", "A1", o, d, a, (qv, contrib)))

        # return combined list (adds first, then drops)
        return adds + drops

    # ------------ tabu helpers ------------
    def _is_tabu(self, mv_key) -> bool:
        return self.tabu_until.get(mv_key, -1) > self.iter_idx

    def _make_tabu(self, mv_key):
        self.tabu_until[mv_key] = self.iter_idx + self.tenure

    # ------------ trial evaluation (on a model copy) ------------
    def _trial_add(self, o, d, a, kind) -> Optional[float]:
        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 0
            mcopy.Params.Method = 1

            Qod = self.lp.demands[(o, d)]
            gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
            sd_c    = mcopy.getConstrByName("StrongDuality")
            dem_c   = mcopy.getConstrByName(f"demand_{o}_{d}")

            if kind == "A2":
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
                rhs = score_pt_only(self.parsed, o, d, a, pt_price=self.pt_price)
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaPT_{o}_{d}_{a}")
                mcopy.chgCoeff(dem_c, q, +1.0)
                mcopy.chgCoeff(sd_c, q, rhs)
                q.Obj = 0.0
            else:
                p = mcopy.addVar(lb=self.P_bar, ub=self.P_up, vtype=GRB.CONTINUOUS, name=f"trial_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"trial_z_{o}_{d}_{a}")

                # McCormick
                mcopy.addConstr(z >= self.P_bar*q,                               name=f"trial_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= self.P_up*q,                                name=f"trial_zmax1_{o}_{d}_{a}")
                mcopy.addConstr(z >= self.P_up*q + p*Qod - self.P_up*Qod,        name=f"trial_zmin2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.P_bar*q - self.P_bar*Qod,      name=f"trial_zmax2_{o}_{d}_{a}")

                rhs = (ASC_PT + ASC_BIKE
                       + B_CPT*self.pt_price + B_CB*p
                       + B_PT*self.parsed["pt_time_min"][(o, d, a)]
                       + B_BIKE*self.parsed["bike_time_min"].get((o, d, a), 0.0)
                       + B_TRB*self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaA_{o}_{d}_{a}")

                mcopy.chgCoeff(dem_c, q, +1.0)
                # capacity rows
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),        q, delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)
                # SD
                term_q = (ASC_PT + ASC_BIKE
                          + B_CPT*self.pt_price
                          + B_PT*self.parsed["pt_time_min"][(o, d, a)]
                          + B_BIKE*self.parsed["bike_time_min"].get((o, d, a), 0.0)
                          + B_TRB*self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.chgCoeff(sd_c, q, term_q)
                mcopy.chgCoeff(sd_c, z, B_CB)

                # objective contribution
                ridership = 2.0 * self.P_up
                resource  = self.lp._resource_coeff.get((o, d, a), 0.0)
                z.Obj += 1.0
                q.Obj += (ridership - self.cost_bike + self.theta * resource)

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None

        except Exception:
            return None

    def _trial_drop(self, o, d, a) -> Optional[float]:
        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 0
            mcopy.Params.Method = 1

            q = mcopy.getVarByName(f"q_{o}_{d}_{a}")
            p = mcopy.getVarByName(f"p_{o}_{d}_{a}")
            z = mcopy.getVarByName(f"z_{o}_{d}_{a}")
            if q is None:
                return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None
            q.LB = 0.0; q.UB = 0.0
            if p is not None: p.LB = 0.0; p.UB = 0.0
            if z is not None: z.LB = 0.0; z.UB = 0.0

            crow = mcopy.getConstrByName(f"gammaA_{o}_{d}_{a}")
            if crow is not None:
                try: crow.RHS = 1e9
                except: pass

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None

        except Exception:
            return None

    # ------------ apply moves ------------
    def _apply(self, move) -> Optional[float]:
        op, kind, o, d, a, _meta = move
        if op == "ADD":
            if kind == "A2":
                self.lp.add_pt_only(o, d, a)
                self.sel[(o, d)]["A2"].append(a)
            else:
                self.lp.add_pt_bike(o, d, a)
                self.sel[(o, d)]["A1"].append(a)
        else:  # DROP A1
            self.lp.deactivate_pt_bike(o, d, a)
            try:
                self.sel[(o, d)]["A1"].remove(a)
            except ValueError:
                pass

        return self.lp.optimize()

    # ------------ main search ------------
    def run(self):
        t0 = time.perf_counter()
        # seed model and solve
        self._build_initial()
        cur_obj = self.lp.optimize()
        self.best_obj = cur_obj
        stall = 0

        for self.iter_idx in range(1, self.max_iters + 1):
            moves = self._neighborhood()

            best_mv = None
            best_trial = None
            # evaluate with tabu/aspiration
            for mv in moves:
                key = tuple(mv[:5])  # (op, kind, o, d, a)
                tabu = self._is_tabu(key)
                trial = None
                if mv[0] == "ADD":
                    trial = self._trial_add(mv[2], mv[3], mv[4], mv[1])
                else:
                    trial = self._trial_drop(mv[2], mv[3], mv[4])

                if trial is None:
                    continue
                # aspiration: allow tabu if better than best ever
                if tabu and (self.best_obj is not None) and not (trial > self.best_obj):
                    continue

                if best_trial is None or trial > best_trial:
                    best_trial = trial
                    best_mv = mv

            if best_mv is None:
                stall += 1
            else:
                post_obj = self._apply(best_mv)
                self._make_tabu(tuple(best_mv[:5]))
                if post_obj is not None and (self.best_obj is None or post_obj > self.best_obj):
                    self.best_obj = post_obj
                    stall = 0
                else:
                    stall += 1

            # diversification if stuck
            if stall >= self.stall_limit and self.lp.m.SolCount > 0:
                stall = 0
                # drop a couple of weakest non-tabu A1 arcs
                weak = []
                for (o, d, a) in list(self.lp._present_A1):
                    qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
                    zv = self.lp.z[(o, d, a)].X if (o, d, a) in self.lp.z else 0.0
                    q_coeff = 2*self.P_up - self.cost_bike + self.lp._resource_coeff.get((o, d, a), 0.0)
                    contrib = zv + q_coeff * qv
                    weak.append((qv, contrib, (o, d, a)))
                weak.sort(key=lambda t: (t[0], t[1]))
                for _ in range(self.diversify_drops):
                    if not weak: break
                    _, _, (o, d, a) = weak.pop(0)
                    mv = ("DROP", "A1", o, d, a, (0.0, 0.0))
                    key = tuple(mv[:5])
                    if not self._is_tabu(key):
                        self._apply(mv)
                        self._make_tabu(key)

        t1 = time.perf_counter()
        return {"best_obj": self.best_obj, "time_sec": t1 - t0}

    # ------------ convenience: write solution JSON ------------
    def write_json(self, json_file_path: str, save_folder: str,
                   P_bar: float, capacity, inventory_level, q_tol: float = 0.0):
        """
        Reuses lp.extract_solution_df to output in your expected structure.
        """
        import os, json
        os.makedirs(save_folder, exist_ok=True)
        base_name = os.path.basename(json_file_path).replace(".json", "")
        if inventory_level is not None:
            low, high = inventory_level
            suffix = f"_{P_bar}_{capacity}_{low}_{high}"
        else:
            suffix = f"_{P_bar}_{capacity}"
        sol_path = os.path.join(save_folder, f"{base_name}{suffix}_solution.json")

        rows = self.lp.extract_solution_df(q_tol=q_tol)
        status = self.lp.m.Status
        gap_pct = 0.0 if status == GRB.OPTIMAL else None

        sol_obj = {
            "Solution Time (s)": None,
            "Objective Value":  self.lp.objective_value(),
            "Gap (%)":          gap_pct,
            "instances":        rows
        }
        with open(sol_path, "w", encoding="utf-8") as f:
            json.dump(sol_obj, f, indent=4, ensure_ascii=False)
        return sol_path
