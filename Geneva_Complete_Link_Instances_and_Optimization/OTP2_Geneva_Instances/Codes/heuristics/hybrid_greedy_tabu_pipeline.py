# hybrid_greedy_tabu_pipeline.py
# ------------------------------------------------------------------------------
# Hybrid Greedy + Tabu Search pipeline on top of your IncrementalBilevelLP.
# This module:
#   1) Builds a balanced initial selection (PT-only + competitive PT+Bike)
#   2) Runs a greedy forward-add seed phase using trial solves on model copies
#   3) Switches to a tabu search that explores adds/drops/swaps with a tabu list
#   4) Keeps the best solution seen and provides IO helpers compatible with your
#      existing writer
#
# All key functions/classes below have docstrings and inline comments explaining
# what they do and why.
# ------------------------------------------------------------------------------

from __future__ import annotations
import time
import heapq
from dataclasses import dataclass
from collections import deque
from typing import Dict, List, Tuple, Optional

import gurobipy as gp
from gurobipy import GRB

from incremental_lp import IncrementalBilevelLP


# ==============================================================================
# Scoring helpers (lower = better): replicate your utility structure consistently
# ==============================================================================

def _score_pt_only(parsed, o, d, a, pt_price: float) -> float:
    """
    Compute PT-only disutility used for ranking / benchmarking.

    Matches your LP’s gamma-row constants for PT-only:
      ASC_PT + B_CPT*pt_price + B_TIME*pt_time + B_TR*transfers
    """
    ASC_PT, B_TIME, B_TR, B_CPT = -0.756, 0.101, 0.208, 0.779
    return (ASC_PT
            + B_CPT * pt_price
            + B_TIME * parsed["pt_time_min"][(o, d, a)]
            + B_TR   * parsed["transfer_time_min"][(o, d, a)])


def _score_a1_at_price_lb(parsed, o, d, a, *, P_bar: float, pt_price: float) -> float:
    """
    Compute PT+Bike disutility at bike price = P_bar (lower bound).
    Used to approximate how competitive an A1 arc could be before pricing moves.

    Matches your LP’s gamma-row structure for PT+Bike, with p replaced by P_bar.
    """
    ASC_PT, ASC_BIKE = -0.756, 0.0
    B_PT, B_BIKE, B_TRB, B_CPT, B_CB = 0.101, 0.108, 0.199, 0.779, 0.689
    return (ASC_PT + ASC_BIKE
            + B_CPT * pt_price
            + B_CB  * P_bar
            + B_PT  * parsed["pt_time_min"][(o, d, a)]
            + B_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
            + B_TRB * parsed["transfer_time_min"][(o, d, a)])


def _best_car_score(parsed, o, d, *, dep_cost: float, parking_fee: float) -> float:
    """
    Compute the best (minimum) Car disutility across all car paths for an OD.

    Matches your car gamma-row coefficients:
      ASC_CAR + B_CC*(F - dep_cost) + B_CP*parking_fee + B_CT*travel_time
    """
    ASC_CAR, B_CC, B_CP, B_CT = -0.669, 0.474, 0.532, 0.116
    best = float("inf")
    od = f"{o}_{d}"
    for arc in parsed["car_paths"].get(od, []):
        a = arc["arc_id"]
        F  = parsed["total_cost_car"][(o, d, a)]
        Tt = parsed["travel_time_min"][(o, d, a)]
        s  = (ASC_CAR + B_CC*(F - dep_cost) + B_CP*parking_fee + B_CT*Tt)
        best = min(best, s)
    return best


# ==============================================================================
# Initial selection (balanced between PT-only and competitive PT+Bike)
# ==============================================================================

def make_initial_selection_enhanced(
    parsed, L: int, K_PT: int, mult_A1: int,
    *, P_bar: float, pt_price: float, dep_cost: float, parking_fee: float
) -> Dict[Tuple[int, int], Dict[str, List[str]]]:
    """
    Build an initial restricted set per OD:
      • Keep top-K_PT PT-only by PT disutility.
      • Keep PT+Bike arcs that beat the best Car alternative at p = P_bar.
      • If PT+Bike is competitive on an OD, allocate more A1 slots and slightly
        fewer PT-only slots to give PT+Bike a fair starting chance.

    Returns
    -------
    sel : dict
        Mapping (o,d) -> {"A1":[aids], "A2":[aids]} used to build the first LP.
    """
    sel: Dict[Tuple[int,int], Dict[str, List[str]]] = {}
    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"

        # --- PT-only: score and keep top-K ---
        a2_scored = []
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            a2_scored.append((_score_pt_only(parsed, o, d, a, pt_price), a))
        a2_scored.sort(key=lambda t: t[0])
        kept_A2 = [a for _, a in a2_scored[:K_PT]]

        # --- PT+Bike vs Car: at lower-bound price P_bar ---
        best_car = _best_car_score(parsed, o, d, dep_cost=dep_cost, parking_fee=parking_fee)
        a1_scored = []
        competitive = 0
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            s = _score_a1_at_price_lb(parsed, o, d, a, P_bar=P_bar, pt_price=pt_price)
            a1_scored.append((s, a))
            if s < best_car:
                competitive += 1
        a1_scored.sort(key=lambda t: t[0])

        # If competitive, give A1 more capacity (and relax A2 a bit)
        if competitive > 0:
            A1_cap = max(L, mult_A1 * L, min(2 * L, len(a1_scored)))
            A2_cap = max(1, K_PT - 1)
        else:
            A1_cap = max(L, mult_A1 * L)
            A2_cap = K_PT

        kept_A1 = [a for _, a in a1_scored[:A1_cap]]
        kept_A2 = kept_A2[:A2_cap]
        sel[(o, d)] = {"A1": kept_A1, "A2": kept_A2}
    return sel


# ==============================================================================
# Global candidate heap (price-aware)
# ==============================================================================

def build_candidate_heap_priceaware(
    parsed, sel,
    *, P_bar: float, pt_price: float, dep_cost: float, parking_fee: float,
    H_PT: int = 3, H_A1: int = 5
) -> List[Tuple[float, Tuple[int,int,str], str]]:
    """
    Build a global min-heap of candidates not in the current selection:

    PT-only (A2): key = PT disutility.
    PT+Bike (A1): key = gap = Score(A1 at P_bar) - min(best_PT, best_Car).

    We keep only top H_PT / H_A1 per OD to limit trials.
    """
    heap: List[Tuple[float, Tuple[int,int,str], str]] = []

    # quick set to skip already present items
    present = {(o, d, aid, "A1") for (o, d), grp in sel.items() for aid in grp["A1"]}
    present |= {(o, d, aid, "A2") for (o, d), grp in sel.items() for aid in grp["A2"]}

    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"

        # Compute benchmark = min(best PT-only, best Car) for OD
        best_PT = float("inf")
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            s = _score_pt_only(parsed, o, d, a, pt_price)
            best_PT = min(best_PT, s)
        best_Car = _best_car_score(parsed, o, d, dep_cost=dep_cost, parking_fee=parking_fee)
        benchmark = min(best_PT, best_Car)

        # --- PT-only pool ---
        pool_A2 = []
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            if (o, d, a, "A2") in present:
                continue
            s = _score_pt_only(parsed, o, d, a, pt_price)
            pool_A2.append((s, (o, d, a)))
        pool_A2.sort(key=lambda t: t[0])
        for s, key in pool_A2[:H_PT]:
            heapq.heappush(heap, (s, key, "A2"))

        # --- PT+Bike pool: rank by gap vs benchmark (smaller gap = more promising) ---
        pool_A1 = []
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            if (o, d, a, "A1") in present:
                continue
            s_a1 = _score_a1_at_price_lb(parsed, o, d, a, P_bar=P_bar, pt_price=pt_price)
            gap = s_a1 - benchmark
            pool_A1.append((gap, s_a1, (o, d, a)))
        pool_A1.sort(key=lambda t: (t[0], t[1]))
        for gap, _s, key in pool_A1[:H_A1]:
            heapq.heappush(heap, (gap, key, "A1"))

    return heap


# ==============================================================================
# Move representation for tabu search
# ==============================================================================

@dataclass(frozen=True)
class Move:
    """
    Represents a local move in tabu search:
      • adds: tuple of (o, d, a, kind) where kind ∈ {"A1", "A2"}
      • drops: tuple of (o, d, a) — assumed A1 here; extend if you want A2 drops.
    """
    adds: Tuple[Tuple[int,int,str,str], ...]
    drops: Tuple[Tuple[int,int,str], ...]

    @staticmethod
    def add(o:int, d:int, a:str, kind:str) -> "Move":
        """Single add move."""
        return Move(adds=((o,d,a,kind),), drops=())

    @staticmethod
    def drop(o:int, d:int, a:str) -> "Move":
        """Single drop move (for A1 by default)."""
        return Move(adds=(), drops=((o,d,a),))

    @staticmethod
    def swap(add_tuple:Tuple[int,int,str,str], drop_tuple:Tuple[int,int,str]) -> "Move":
        """Swap move: add one candidate and drop one incumbent."""
        return Move(adds=(add_tuple,), drops=(drop_tuple,))

    def signature(self) -> Tuple:
        """
        Canonical key for tabu list—order-independent so the same move can be
        recognized regardless of construction order.
        """
        return tuple(sorted(self.adds)) + ("|",) + tuple(sorted(self.drops))


# ==============================================================================
# Hybrid Greedy + Tabu Pipeline
# ==============================================================================

class HybridGreedyTabuPipeline:
    """
    A two-stage metaheuristic:
      1) Greedy seed — build an initial restricted LP, solve, then incrementally
         add promising A1/A2 via trial solves on model copies (Dual).
      2) Tabu search — explore a neighborhood of adds/drops/swaps, using a tabu
         list with tenure and aspiration to escape cycling and improve solution.

    Uses the IncrementalBilevelLP to avoid full rebuilds when committing moves.
    """

    def __init__(
        self,
        parsed_data: dict,
        *,
        # LP params
        P_bar: float = 0.5, P_up: float = 4.0, theta: float = 0.5,
        pt_price: float = 2.0, cost_bike: float = 0.6,
        parking_fee: float = 2.8, dep_cost: float = 0.0,
        tolerance: float = 1e-3,
        quiet: bool = True, threads: int = 4,
        time_limit_initial: Optional[int] = None,  # None → no limit on initial solve
        time_limit_trial: Optional[int] = 20,      # trial model copies
        # Greedy knobs
        L: int = 10, K_PT: int = 2, mult_A1: int = 1,
        H_PT: int = 3, H_A1: int = 5,
        rel_impr_tol_add: float = 1e-4, patience_add: int = 10, max_trial_add: int = 200,
        # Tabu knobs
        tabu_tenure: int = 15, max_iters: int = 150, neighborhood_size: int = 40,
        stall_limit: int = 15, aspiration_eps: float = 1e-9,
    ):
        # Save instance data + hyperparameters
        self.parsed = parsed_data
        self.P_bar, self.P_up, self.theta = P_bar, P_up, theta
        self.pt_price, self.cost_bike = pt_price, cost_bike
        self.parking_fee, self.dep_cost = parking_fee, dep_cost
        self.tolerance = tolerance
        self.quiet = quiet
        self.threads = threads
        self.time_limit_initial = time_limit_initial
        self.time_limit_trial = time_limit_trial

        # Greedy parameters
        self.L, self.K_PT, self.mult_A1 = L, K_PT, mult_A1
        self.H_PT, self.H_A1 = H_PT, H_A1
        self.rel_impr_tol_add = rel_impr_tol_add
        self.patience_add = patience_add
        self.max_trial_add = max_trial_add

        # Tabu parameters
        self.tabu_tenure = tabu_tenure
        self.max_iters = max_iters
        self.neighborhood_size = neighborhood_size
        self.stall_limit = stall_limit
        self.aspiration_eps = aspiration_eps

        # Build the incremental LP once (shared rows; cars included inside)
        self.lp = IncrementalBilevelLP(
            parsed_data,
            P_bar=P_bar, P_up=P_up, theta=theta,
            pt_price=pt_price, cost_bike=cost_bike,
            parking_fee=parking_fee, dep_cost=dep_cost,
            tolerance=tolerance, quiet=quiet,
            threads=threads, time_limit=time_limit_initial
        )

        # Runtime state
        self.sel = {}                           # (o,d) -> {"A1":[...], "A2":[...]}
        self.heap: List[Tuple[float, Tuple[int,int,str], str]] = []
        self.best_obj: Optional[float] = None   # Best objective found
        self.best_state: Optional[Dict] = None  # Light snapshot (for reporting)

    # ---------- Initial selection + build ----------
    def _initial_selection(self):
        """Compute the initial per-OD selection with the enhanced rule."""
        self.sel = make_initial_selection_enhanced(
            self.parsed, self.L, self.K_PT, self.mult_A1,
            P_bar=self.P_bar, pt_price=self.pt_price,
            dep_cost=self.dep_cost, parking_fee=self.parking_fee
        )

    def _build_initial(self):
        """Add the selected A1/A2 arcs to the incremental LP (cars already built)."""
        for (o, d), grp in self.sel.items():
            for aid in grp["A2"]:
                self.lp.add_pt_only(o, d, aid)
            for aid in grp["A1"]:
                self.lp.add_pt_bike(o, d, aid)

    def _initial_solve(self):
        """
        Solve the initial LP.
        • Allow Gurobi to choose method (Method = -1) for robustness.
        • Apply an optional initial time limit (can be None for large runs).
        • Switch to Dual (Method = 1) for all subsequent incremental solves.
        """
        if self.time_limit_initial is not None:
            self.lp.m.Params.TimeLimit = int(self.time_limit_initial)
        else:
            # effectively unlimited
            self.lp.m.Params.TimeLimit = 1e9
        self.lp.m.Params.Method = -1  # free choice for initial solve
        obj = self.lp.optimize()
        self.lp.m.Params.Method = 1   # dual simplex for incremental solves
        return obj

    # ---------- Greedy forward ----------
    def _build_heap(self):
        """Precompute a small global heap of promising A1/A2 candidates to try adding."""
        self.heap = build_candidate_heap_priceaware(
            self.parsed, self.sel,
            P_bar=self.P_bar, pt_price=self.pt_price,
            dep_cost=self.dep_cost, parking_fee=self.parking_fee,
            H_PT=self.H_PT, H_A1=self.H_A1
        )

    def _trial_add_value(self, o, d, a, kind) -> Optional[float]:
        """
        Trial add (o,d,a) of type `kind` on a *copy* of the current LP:
          • Wires the same gamma/SD/demand/capacity pieces you use in master.
          • Uses Dual Simplex and an optional short time limit.
          • Returns the objective value on the copy, or None if infeasible/failed.
        """
        try:
            mcopy: gp.Model = self.lp.m.copy()
            mcopy.Params.OutputFlag = 0
            mcopy.Params.Method = 1  # Dual Simplex for quick reopt
            if self.time_limit_trial is not None:
                mcopy.Params.TimeLimit = int(self.time_limit_trial)

            # Get anchors from the copy
            Qod = self.lp.demands[(o, d)]
            gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
            sd_c = mcopy.getConstrByName("StrongDuality")
            dem_c = mcopy.getConstrByName(f"demand_{o}_{d}")

            if kind == "A2":
                # Add q and gamma-row; push into demand and SD with the exact coeffs
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
                rhs = (-0.756 + 0.779 * self.lp.pt_price
                       + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                       + 0.208 * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaPT_{o}_{d}_{a}")
                mcopy.chgCoeff(dem_c, q, +1)
                mcopy.chgCoeff(sd_c, q, rhs)
                q.Obj = 0.0  # PT-only has no revenue/cost in objective directly

            else:
                # PT+Bike: add p,q,z, McCormick envelopes, gamma-row, demand, caps, SD terms
                p = mcopy.addVar(lb=self.lp.P_bar, ub=self.lp.P_up, vtype=GRB.CONTINUOUS, name=f"trial_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"trial_z_{o}_{d}_{a}")

                # McCormick for z = p*q bounded by (P_bar,P_up) and (0,Qod)
                mcopy.addConstr(z >= self.lp.P_bar * q, name=f"trial_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= self.lp.P_up  * q, name=f"trial_zmax1_{o}_{d}_{a}")
                mcopy.addConstr(z >= self.lp.P_up*q + p*Qod - self.lp.P_up*Qod,   name=f"trial_zmin2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod, name=f"trial_zmax2_{o}_{d}_{a}")

                # Gamma row with p to preserve the exact dual feasibility structure
                rhs = (0.0 + (-0.756)
                       + 0.779 * self.lp.pt_price
                       + 0.689 * p
                       + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                       + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                       + 0.199 * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaA_{o}_{d}_{a}")

                # Demand + station caps
                mcopy.chgCoeff(dem_c, q, +1)
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),       q, delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)

                # SD terms (exact mirror of your build)
                coeff_q = (0.779 * self.lp.pt_price
                           + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                           + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                           + 0.199 * self.parsed["transfer_time_min"][(o, d, a)]
                           + (0.0 + -0.756))
                mcopy.chgCoeff(sd_c, q, coeff_q)
                mcopy.chgCoeff(sd_c, z, 0.689)

                # Objective: revenue via z + ridership/resource via q
                z.Obj = 1.0
                ridership = 2.0 * self.lp.P_up
                resource  = self.lp._resource_coeff.get((o, d, a), 0.0)
                q.Obj = (ridership - self.lp.cost_bike + resource)

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None

        except Exception:
            # If anything goes wrong (infeasible copy, time-out, etc.), skip
            return None

    def _apply_add_master(self, o, d, a, kind):
        """
        Commit an accepted add move to the *master* incremental LP, and update sel.
        """
        if kind == "A2":
            self.lp.add_pt_only(o, d, a)
            self.sel[(o, d)]["A2"].append(a)
        else:
            self.lp.add_pt_bike(o, d, a)
            self.sel[(o, d)]["A1"].append(a)

    def _greedy_seed(self):
        """
        Stage 1 — Greedy forward:
          • Build initial restricted model and solve.
          • Build a small heap of promising candidates.
          • Iteratively trial-add on copies; accept only if objective improves
            relative to the current master solution (relative tolerance).
          • Apply accepted adds to master and reoptimize (Dual).
        """
        self._initial_selection()
        self._build_initial()
        base = self._initial_solve()
        if base is None:
            base = -1e100
        print(f"[hybrid] initial objective = {base:.6f}")

        self._build_heap()

        added = 0
        trials = 0
        no_improve = 0
        while self.heap and trials < self.max_trial_add and no_improve < self.patience_add:
            _, (o, d, a), kind = heapq.heappop(self.heap)

            # Trial add on a copy
            trial_val = self._trial_add_value(o, d, a, kind)
            trials += 1
            if trial_val is None:
                no_improve += 1
                continue

            # Accept if sufficient relative improvement
            if trial_val > base * (1.0 + self.rel_impr_tol_add):
                self._apply_add_master(o, d, a, kind)
                self.lp.m.Params.Method = 1  # Dual for incremental
                base = self.lp.optimize()
                added += 1
                no_improve = 0
            else:
                no_improve += 1

        # Save best-so-far snapshot (for reporting)
        self.best_obj = base
        self.best_state = self._snapshot_state()
        print(f"[hybrid] greedy seed: added={added}, obj={base:.6f}")
        return base

    # ---------- Contribution and eligible sets ----------
    def _contribution(self, o, d, a) -> float:
        """
        Compute contribution of an A1 arc to the objective:
          contrib = z + q * (2*P_up - cost_bike + resource_signal)
        (Matches the coefficients used in your LP objective.)
        """
        qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
        zv = self.lp.z[(o, d, a)].X if (o, d, a) in self.lp.z else 0.0
        q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o, d, a), 0.0)
        return zv + q_coeff * qv

    def _eligible_drops(self, top_n: int = 20) -> List[Tuple[int,int,str]]:
        """
        Pick low-importance A1 arcs to consider dropping:
          • rank by (small q, then small contribution)
          • return top_n weakest as (o,d,a)
        """
        cand = []
        for (o, d, a) in list(self.lp._present_A1):
            qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
            contrib = self._contribution(o, d, a)
            cand.append((qv, contrib, o, d, a))
        cand.sort(key=lambda t: (t[0], t[1]))
        return [(o, d, a) for _, _, o, d, a in cand[:top_n]]

    def _eligible_adds(self, per_od_cap: int = 2) -> List[Tuple[int,int,str,str]]:
        """
        Build a small pool of promising A1/A2 adds (per OD cap) not currently present.
        Returns tuples (o, d, a, kind) for the neighborhood generator.
        """
        candidates: List[Tuple[float, Tuple[int,int,str], str]] = build_candidate_heap_priceaware(
            self.parsed, self.sel,
            P_bar=self.P_bar, pt_price=self.pt_price,
            dep_cost=self.dep_cost, parking_fee=self.parking_fee,
            H_PT=per_od_cap, H_A1=per_od_cap
        )
        out = []
        seen = set()
        for score, (o, d, a), kind in candidates:
            key = (o, d, a, kind)
            if key in seen:
                continue
            if (kind == "A1" and (o, d, a) in self.lp._present_A1) or \
               (kind == "A2" and (o, d, a) in self.lp._present_A2):
                continue
            out.append((o, d, a, kind))
            seen.add(key)
        return out

    # ---------- Tabu trial helpers (operate on a model copy) ----------
    def _trial_drop_on_copy(self, mcopy: gp.Model, o, d, a):
        """
        On a model copy, deactivate an arc (fix q,p,z=0 and loosen its gamma-row),
        mimicking IncrementalBilevelLP.deactivate_* without modifying master.
        """
        q = mcopy.getVarByName(f"q_{o}_{d}_{a}")
        p = mcopy.getVarByName(f"p_{o}_{d}_{a}")
        z = mcopy.getVarByName(f"z_{o}_{d}_{a}")
        if q is None:
            return
        q.LB = 0.0; q.UB = 0.0
        if p is not None: p.LB = 0.0; p.UB = 0.0
        if z is not None: z.LB = 0.0; z.UB = 0.0
        crow = mcopy.getConstrByName(f"gammaA_{o}_{d}_{a}")
        if crow is None:
            crow = mcopy.getConstrByName(f"gammaPT_{o}_{d}_{a}")
        if crow is not None:
            try:
                crow.RHS = 1e9  # relax so it won’t bind
            except gp.GurobiError:
                pass

    def _trial_add_on_copy(self, mcopy: gp.Model, o, d, a, kind: str):
        """
        On a model copy, add the variables/rows for PT-only or PT+Bike with the
        same coefficients as your master build (including SD terms).
        """
        Qod = self.lp.demands[(o, d)]
        gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
        sd_c = mcopy.getConstrByName("StrongDuality")
        dem_c = mcopy.getConstrByName(f"demand_{o}_{d}")

        if kind == "A2":
            q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
            rhs = (-0.756 + 0.779 * self.lp.pt_price
                   + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                   + 0.208 * self.parsed["transfer_time_min"][(o, d, a)])
            mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaPT_{o}_{d}_{a}")
            mcopy.chgCoeff(dem_c, q, +1)
            mcopy.chgCoeff(sd_c, q, rhs)
            q.Obj = 0.0
        else:
            p = mcopy.addVar(lb=self.lp.P_bar, ub=self.lp.P_up, vtype=GRB.CONTINUOUS, name=f"trial_p_{o}_{d}_{a}")
            q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
            z = mcopy.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"trial_z_{o}_{d}_{a}")
            # McCormick
            mcopy.addConstr(z >= self.lp.P_bar * q, name=f"trial_zmin1_{o}_{d}_{a}")
            mcopy.addConstr(z <= self.lp.P_up  * q, name=f"trial_zmax1_{o}_{d}_{a}")
            mcopy.addConstr(z >= self.lp.P_up*q + p*Qod - self.lp.P_up*Qod,   name=f"trial_zmin2_{o}_{d}_{a}")
            mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod, name=f"trial_zmax2_{o}_{d}_{a}")
            # Gamma
            rhs = (0.0 + (-0.756)
                   + 0.779 * self.lp.pt_price
                   + 0.689 * p
                   + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                   + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                   + 0.199 * self.parsed["transfer_time_min"][(o, d, a)])
            mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaA_{o}_{d}_{a}")
            # Demand + caps
            mcopy.chgCoeff(dem_c, q, +1)
            for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                if delta:
                    mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),       q, delta)
                    mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)
            # SD
            coeff_q = (0.779 * self.lp.pt_price
                       + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                       + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                       + 0.199 * self.parsed["transfer_time_min"][(o, d, a)]
                       + (0.0 + -0.756))
            mcopy.chgCoeff(sd_c, q, coeff_q)
            mcopy.chgCoeff(sd_c, z, 0.689)
            # Obj
            z.Obj = 1.0
            ridership = 2.0 * self.lp.P_up
            resource  = self.lp._resource_coeff.get((o, d, a), 0.0)
            q.Obj = (ridership - self.lp.cost_bike + resource)

    def _trial_move_value(self, move: Move) -> Optional[float]:
        """
        Evaluate a combined add/drop move on a model copy (Dual).
        Returns objective value or None if infeasible/time-out.
        """
        try:
            mcopy: gp.Model = self.lp.m.copy()
            mcopy.Params.OutputFlag = 0
            mcopy.Params.Method = 1
            if self.time_limit_trial is not None:
                mcopy.Params.TimeLimit = int(self.time_limit_trial)

            # Drops first (release capacity/inventory in copy)
            for (o, d, a) in move.drops:
                self._trial_drop_on_copy(mcopy, o, d, a)
            # Adds next
            for (o, d, a, kind) in move.adds:
                self._trial_add_on_copy(mcopy, o, d, a, kind)

            mcopy.optimize()
            if mcopy.SolCount == 0:
                return None
            return float(mcopy.ObjVal)

        except Exception:
            return None

    def _apply_move_master(self, move: Move):
        """
        Commit a move on the master LP:
          • Execute drops (A1) via deactivate_pt_bike
          • Execute adds via add_pt_only / add_pt_bike
        Update self.sel to mirror the model.
        """
        # Drops
        for (o, d, a) in move.drops:
            self.lp.deactivate_pt_bike(o, d, a)  # assumes A1; extend if needed
            if a in self.sel.get((o, d), {}).get("A1", []):
                self.sel[(o, d)]["A1"].remove(a)
        # Adds
        for (o, d, a, kind) in move.adds:
            self._apply_add_master(o, d, a, kind)

    # ---------- Neighborhood & tabu machinery ----------
    def _gen_neighborhood(self, size: int) -> List[Move]:
        """
        Build a small neighborhood of candidate moves:
          • Some single adds
          • Some single drops (weak A1 arcs)
          • Some simple swaps (add promising A1 and drop weak A1)
        """
        adds = self._eligible_adds(per_od_cap=2)
        drops = self._eligible_drops(top_n=10)

        moves: List[Move] = []
        # Add-only moves (top half of the neighborhood)
        for (o, d, a, kind) in adds[: size // 2]:
            moves.append(Move.add(o, d, a, kind))
        # Drop-only moves (next chunk)
        for (o, d, a) in drops[: size // 3]:
            moves.append(Move.drop(o, d, a))
        # Swaps (mix the first few)
        for i, (odrop, ddrop, adrop) in enumerate(drops[: size // 6]):
            if i < len(adds):
                oadd, dadd, aadd, kind = adds[i]
                if kind == "A1":  # A1↔A1 swaps are most natural
                    moves.append(Move.swap((oadd, dadd, aadd, kind), (odrop, ddrop, adrop)))
        return moves[:size]

    def _snapshot_state(self) -> Dict:
        """
        Lightweight snapshot for reporting. (Not a full restorable state.)
        """
        return {
            "A1": list(self.lp._present_A1),
            "A2": list(self.lp._present_A2),
            "obj": self.lp.objective_value()
        }

    def _restore_state(self, state: Dict):
        """
        Placeholder for a full restore routine (not needed here).
        We maintain the best on the *live* model instead.
        """
        pass

    def _tabu_search(self, base_obj: float):
        """
        Stage 2 — Tabu Search:
          • Iteratively explore a neighborhood of moves.
          • Use a FIFO tabu list with tenure; forbid reverse moves.
          • Allow aspiration if a tabu move strictly beats the global best.
          • Mild diversification on stalls (drop a weak A1).
        """
        best = base_obj
        best_seen = self._snapshot_state()

        tabu = deque()      # queue of (signature, expire_iter)
        tabu_set = set()    # fast membership for "is tabu?"

        stall = 0
        for it in range(1, self.max_iters + 1):
            # Neighborhood around current solution
            neigh = self._gen_neighborhood(self.neighborhood_size)
            if not neigh:
                break

            # Evaluate admissible moves; keep the best
            best_move, best_trial = None, None
            for mv in neigh:
                sig = mv.signature()
                trial_val = self._trial_move_value(mv)
                if trial_val is None:
                    continue
                is_tabu = sig in tabu_set
                # Aspiration: allow tabu if trial improves upon best seen
                if (not is_tabu) or (trial_val > best + self.aspiration_eps):
                    if (best_trial is None) or (trial_val > best_trial):
                        best_move, best_trial = mv, trial_val

            # If no admissible improvement found
            if best_move is None:
                stall += 1
                if stall >= self.stall_limit:
                    # Diversify lightly: force a weak drop if any
                    weak = self._eligible_drops(top_n=1)
                    if weak:
                        mv = Move.drop(*weak[0])
                        self._apply_move_master(mv)
                        self.lp.m.Params.Method = 1
                        base_obj = self.lp.optimize()
                        # Push reverse add to tabu to avoid immediate undo
                        rev = Move.add(weak[0][0], weak[0][1], weak[0][2], "A1")
                        rsig = rev.signature()
                        tabu.append((rsig, it + self.tabu_tenure))
                        tabu_set.add(rsig)
                        # Expire aged tabu marks
                        while tabu and tabu[0][1] <= it:
                            expired = tabu.popleft()
                            tabu_set.discard(expired[0])
                        stall = 0
                    continue
                else:
                    continue

            # Apply the chosen admissible move on master and reoptimize
            self._apply_move_master(best_move)
            self.lp.m.Params.Method = 1
            base_obj = self.lp.optimize()

            # Add reverse move to tabu list (tenure-based expiry)
            reverse_adds = tuple()
            reverse_drops = tuple()
            if best_move.adds:
                reverse_drops = tuple((o, d, a) for (o, d, a, _k) in best_move.adds)
            if best_move.drops:
                reverse_adds = tuple((o, d, a, "A1") for (o, d, a) in best_move.drops)
            rsig = Move(adds=reverse_adds, drops=reverse_drops).signature()
            tabu.append((rsig, it + self.tabu_tenure))
            tabu_set.add(rsig)
            while tabu and tabu[0][1] <= it:
                expired = tabu.popleft()
                tabu_set.discard(expired[0])

            # Track improvements
            if base_obj > best + 1e-12:
                best = base_obj
                best_seen = self._snapshot_state()
                stall = 0
                print(f"[tabu] iter={it} improved: obj={best:.6f}")
            else:
                stall += 1
                if stall >= self.stall_limit:
                    stall = 0  # reset (we already diversify on 'no move' path)

        self.best_obj = best
        self.best_state = best_seen
        return best

    # ---------- Public driver ----------
    def run(self):
        """
        Run the full hybrid pipeline:
          1) Greedy seed (initial LP + forward add)
          2) Tabu search
        Returns (best_obj, elapsed_seconds).
        """
        t0 = time.time()
        base = self._greedy_seed()
        best = self._tabu_search(base)
        t1 = time.time()
        print(f"[hybrid] done: best_obj={best:.6f}, time={t1-t0:.2f}s")
        return best, (t1 - t0)

    def write_json(self, json_file_path: str, save_folder: str, P_bar: float, capacity, inventory_level, q_tol: float = 0):
        """
        Save solution in the same JSON structure your greedy pipeline uses.

        Parameters
        ----------
        json_file_path : str
            Original instance path (used only for naming).
        save_folder : str
            Where to write the solution file.
        P_bar, capacity, inventory_level :
            Used to build the output filename like your current method.
        q_tol : float
            Include arcs with q >= q_tol in the output table.
        """
        import os, json
        os.makedirs(save_folder, exist_ok=True)
        base_name = os.path.basename(json_file_path).replace(".json", "")
        if inventory_level is not None:
            low, high = inventory_level
            suffix = f"_{P_bar}_{capacity}_{low}_{high}"
        else:
            suffix = f"_{P_bar}_{capacity}"
        sol_name = f"{base_name}{suffix}_solution.json"
        sol_path = os.path.join(save_folder, sol_name)

        rows = self.lp.extract_solution_df(q_tol=q_tol)
        status = self.lp.m.Status
        if status == GRB.OPTIMAL:
            gap_pct = 0.0
        else:
            try:
                gap_pct = float(self.lp.m.MIPGap) * 100.0
            except Exception:
                gap_pct = None

        sol_obj = {
            "Solution Time (s)": None,
            "Objective Value":  self.lp.objective_value(),
            "Gap (%)":          gap_pct,
            "instances":        rows
        }
        with open(sol_path, "w", encoding="utf-8") as f:
            json.dump(sol_obj, f, indent=4, ensure_ascii=False)
        return sol_path
