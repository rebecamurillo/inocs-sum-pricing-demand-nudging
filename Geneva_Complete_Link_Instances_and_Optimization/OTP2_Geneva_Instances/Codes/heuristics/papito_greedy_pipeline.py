# greedy_pipeline.py
import json
import time
import heapq
from typing import Dict, List, Tuple, Optional
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import gurobipy as gp
from gurobipy import GRB

from incremental_lp import IncrementalBilevelLP


# -------- Scoring functions (lower = better) --------

def _score_pt_only(parsed, o, d, a) -> float:
    ASC_PT = -0.756; B_TIME = 0.101; B_TR = 0.208
    return (ASC_PT
            + B_TIME * parsed["pt_time_min"][(o, d, a)]
            + B_TR   * parsed["transfer_time_min"][(o, d, a)])

def _score_a1_pricefree(parsed, o, d, a) -> float:
    ASC_PT, ASC_BIKE = -0.756, 0.0
    B_PT, B_BIKE, B_TRB = 0.101, 0.108, 0.199
    return (ASC_PT + ASC_BIKE
            + B_PT   * parsed["pt_time_min"][(o, d, a)]
            + B_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
            + B_TRB  * parsed["transfer_time_min"][(o, d, a)])


def _score_a1_pricefree_inv(parsed, lp_like, o, d, a,
                            inv_lambda: float, alpha_pos: float, alpha_neg: float,
                            slack_cutoff: float, inv_cutoff: float) -> float | None:
    """
    Base disutility (without price) + inventory/capacity penalty.
    Returns None if the arc is hard-forbidden by cutoffs.
    """
    # base (no price)
    ASC_PT, ASC_BIKE = -0.756, 0.0
    B_PT, B_BIKE, B_TRB = 0.101, 0.108, 0.199
    base = (ASC_PT + ASC_BIKE
            + B_PT   * parsed["pt_time_min"][(o, d, a)]
            + B_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
            + B_TRB  * parsed["transfer_time_min"][(o, d, a)])

    # inventory/capacity penalty (use lp_like station data)
    pen = 0.0
    delta_map = lp_like.delta_ia.get(a, {})  # {i_str: delta}
    for i_str, delta in delta_map.items():
        cap_i = lp_like.station_capacity[i_str]
        inv_i = lp_like.station_inventory[i_str]
        slack_up = cap_i - inv_i

        # hard cutoffs
        if delta > 0 and slack_up <= slack_cutoff:
            return None
        if delta < 0 and inv_i <= inv_cutoff:
            return None

        if delta > 0:
            pen += delta * alpha_pos / (1.0 + slack_up)
        elif delta < 0:
            pen += (-delta) * alpha_neg / (1.0 + inv_i)

    return base + inv_lambda * pen



# -------- Initial selection & candidate heap --------




# --- REPLACE your existing build_candidate_heap(...) with this version ---
import heapq
from concurrent.futures import ThreadPoolExecutor

def build_candidate_heap(
    parsed, sel,
    H_PT: int = 3, H_A1: int = 5,
    *,                # explicit-only extra params
    P_bar: float = 0.5,
    pt_price: float = 2.0,
    dep_cost: float = 0.0,
    parking_fee: float = 2.8
) -> list[tuple[float, tuple[int, int, str], str]]:
    """
    Build global min-heap of candidates (score, (o,d,a), kind).
    - PT-only (A2): score = standard PT disutility.
    - PT+Bike (A1): score = 'gap' vs the best of PT-only & Car at p = P_bar.
      (No hard domination filter; we still trial top H_A1 per OD.)
    """
    # utility coefficients (same as in your code)
    ASC_PT, ASC_BIKE, ASC_CAR = -0.756, 0.0, -0.669
    B_PT, B_TRPT = 0.101, 0.208
    B_BIKE, B_TRB = 0.108, 0.199
    B_CPT, B_CB   = 0.779, 0.689
    B_CC, B_CP, B_CT = 0.474, 0.532, 0.116

    heap: list[tuple[float, tuple[int, int, str], str]] = []

    # what's already selected
    present = {(o, d, aid, "A1") for (o, d), grp in sel.items() for aid in grp["A1"]}
    present |= {(o, d, aid, "A2") for (o, d), grp in sel.items() for aid in grp["A2"]}

    def work(od_pair):
        o, d = od_pair
        od = f"{o}_{d}"
        out = []

        # ---- compute best PT-only disutility for (o,d) ----
        best_PT = float("inf")
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            s = (ASC_PT + B_CPT*pt_price
                 + B_PT*parsed["pt_time_min"][(o, d, a)]
                 + B_TRPT*parsed["transfer_time_min"][(o, d, a)])
            if s < best_PT: best_PT = s

        # ---- compute best Car disutility for (o,d) ----
        best_Car = float("inf")
        for arc in parsed["car_paths"].get(od, []):
            a = arc["arc_id"]
            F  = parsed["total_cost_car"][(o, d, a)]
            Tt = parsed["travel_time_min"][(o, d, a)]
            s  = (ASC_CAR + B_CC*(F - dep_cost) + B_CP*parking_fee + B_CT*Tt)
            if s < best_Car: best_Car = s

        benchmark = min(best_PT, best_Car)

        # ---- PT-only pool (A2): keep top H_PT by PT score ----
        pool_A2 = []
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            if (o, d, a, "A2") in present:
                continue
            s = (ASC_PT + B_CPT*pt_price
                 + B_PT*parsed["pt_time_min"][(o, d, a)]
                 + B_TRPT*parsed["transfer_time_min"][(o, d, a)])
            pool_A2.append((s, (o, d, a)))
        pool_A2.sort(key=lambda t: t[0])
        out.extend([(score, key, "A2") for score, key in pool_A2[:H_PT]])

        # ---- PT+Bike pool (A1): use 'gap' vs benchmark at p = P_bar ----
        pool_A1 = []
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            if (o, d, a, "A1") in present:
                continue
            s_a1 = (ASC_PT + ASC_BIKE
                    + B_CPT*pt_price
                    + B_CB*P_bar
                    + B_PT*parsed["pt_time_min"][(o, d, a)]
                    + B_BIKE*parsed["bike_time_min"].get((o, d, a), 0.0)
                    + B_TRB*parsed["transfer_time_min"][(o, d, a)])
            gap = s_a1 - benchmark
            # rank first by gap (closer/better than benchmark), tie-break by raw score
            pool_A1.append((gap, s_a1, (o, d, a)))
        pool_A1.sort(key=lambda t: (t[0], t[1]))
        out.extend([(gap, key, "A1") for gap, _s, key in pool_A1[:H_A1]])

        return out

    # Thread per-OD
    with ThreadPoolExecutor(max_workers=8) as ex:
        for items in ex.map(work, parsed["OD_pairs"]):
            for tup in items:
                heapq.heappush(heap, tup)

    return heap

# --- selections built jointly, price-aware, no inventory terms ---

def make_selections_together_pt_car(
    parsed,
    L: int,
    K_PT: int = 2,
    mult_A1: int = 3,
    *,
    P_bar: float = 0.5,
    pt_price: float = 2.0,
    dep_cost: float = 0.0,
    parking_fee: float = 2.8,
):
    """
    For each OD:
      1) Score PT-only with fare; keep top K_PT.
      2) Find best PT-only score (with fare).
      3) Score Car paths; take min as best Car score.
      4) Score PT+Bike with (PT fare + bike price at P_bar); keep only arcs
         whose score < min(best_PT, best_Car). From survivors keep up to cap=max(L, mult_A1*L).

    Returns: sel[(o,d)] = {"A2": [...], "A1": [...]}
    """

    # Coefficients (same ones used in your model)
    ASC_PT, ASC_BIKE, ASC_CAR = -0.756, 0.0, -0.669
    BETA_Time_PT, BETA_TR_PT   = 0.101, 0.208
    BETA_Time_BIKE, BETA_TR_BIKE = 0.108, 0.199
    BETA_Cost_PT,  BETA_Cost_BIKE = 0.779, 0.689
    BETA_Cost_Car, BETA_Cost_park, BETA_Time_Car = 0.474, 0.532, 0.116

    sel = {}

    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"

        # ---------- PT-only (A2) with fare ----------
        A2_scored = []
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            s = (ASC_PT
                 + BETA_Cost_PT * pt_price
                 + BETA_Time_PT * parsed["pt_time_min"][(o, d, a)]
                 + BETA_TR_PT   * parsed["transfer_time_min"][(o, d, a)])
            A2_scored.append((s, a))
        A2_scored.sort(key=lambda t: t[0])
        kept_A2 = [a for _, a in A2_scored[:K_PT]]
        best_pt_score = A2_scored[0][0] if A2_scored else float("inf")

        # ---------- Car (min across car paths) ----------
        best_car_score = float("inf")
        for arc in parsed["car_paths"].get(od, []):
            a = arc["arc_id"]
            F  = parsed["total_cost_car"][(o, d, a)]
            Tt = parsed["travel_time_min"][(o, d, a)]
            s_car = (ASC_CAR
                     + BETA_Cost_Car * (F - dep_cost)
                     + BETA_Cost_park * parking_fee
                     + BETA_Time_Car * Tt)
            if s_car < best_car_score:
                best_car_score = s_car

        # ---------- PT+Bike (A1) at bike price lower bound P_bar ----------
        threshold = min(best_pt_score, best_car_score)
        A1_scored = []
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            s = (ASC_PT + ASC_BIKE
                 + BETA_Cost_PT   * pt_price
                 + BETA_Cost_BIKE * P_bar               # price at LB
                 + BETA_Time_PT   * parsed["pt_time_min"][(o, d, a)]
                 + BETA_Time_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
                 + BETA_TR_BIKE   * parsed["transfer_time_min"][(o, d, a)])
            if s < threshold:
                A1_scored.append((s, a))
        A1_scored.sort(key=lambda t: t[0])
        cap = max(L, mult_A1 * L)
        kept_A1 = [a for _, a in A1_scored[:cap]]

        sel[(o, d)] = {"A2": kept_A2, "A1": kept_A1}

    return sel


def make_initial_selection_enhanced(parsed, L: int, K_PT: int = 2, mult_A1: int = 3):
    """
    Enhanced initial selection that ensures PT+bike gets a fair chance:
    1. For each OD, identify if ANY PT+bike arc is competitive with car at P_bar
    2. If so, select the most promising PT+bike arcs even if PT-only exists
    3. Use a more balanced selection between PT-only and PT+bike
    """
    
    # Coefficients
    ASC_PT, ASC_BIKE, ASC_CAR = -0.756, 0.0, -0.669
    BETA_Time_PT, BETA_TR_PT = 0.101, 0.208
    BETA_Time_BIKE, BETA_TR_BIKE = 0.108, 0.199
    BETA_Cost_PT, BETA_Cost_BIKE = 0.779, 0.689
    BETA_Cost_Car, BETA_Cost_park, BETA_Time_Car = 0.474, 0.532, 0.116
    
    # Parameters (should match your model)
    P_bar = 0.5
    pt_price = 2.0
    dep_cost = 0.0
    parking_fee = 2.8
    
    sel = {}
    stats = {'total_ods': 0, 'pt_bike_competitive': 0, 'pt_bike_selected': 0}
    
    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"
        stats['total_ods'] += 1
        
        # Find best car utility for this OD
        best_car_util = float('inf')
        for arc in parsed["car_paths"].get(od, []):
            a = arc["arc_id"]
            car_util = (ASC_CAR +
                       BETA_Cost_Car * (parsed["total_cost_car"][(o,d,a)] - dep_cost) +
                       BETA_Cost_park * parking_fee +
                       BETA_Time_Car * parsed["travel_time_min"][(o,d,a)])
            best_car_util = min(best_car_util, car_util)
        
        # Score all PT+bike arcs at P_bar
        pt_bike_scored = []
        competitive_pt_bike = 0
        
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            pt_bike_util = (ASC_PT + ASC_BIKE +
                           BETA_Cost_PT * pt_price +
                           BETA_Cost_BIKE * P_bar +
                           BETA_Time_PT * parsed["pt_time_min"][(o,d,a)] +
                           BETA_Time_BIKE * parsed["bike_time_min"].get((o,d,a), 0.0) +
                           BETA_TR_BIKE * parsed["transfer_time_min"][(o,d,a)])
            
            pt_bike_scored.append((pt_bike_util, a))
            
            if pt_bike_util < best_car_util:
                competitive_pt_bike += 1
        
        # Score PT-only arcs
        pt_only_scored = []
        for arc in parsed["arcs_pt_only"].get(od, []):
            a = arc["arc_id"]
            pt_only_util = (ASC_PT +
                           BETA_Cost_PT * pt_price +
                           BETA_Time_PT * parsed["pt_time_min"][(o,d,a)] +
                           BETA_TR_PT * parsed["transfer_time_min"][(o,d,a)])
            pt_only_scored.append((pt_only_util, a))
        
        # Sort by utility (lower is better)
        pt_bike_scored.sort(key=lambda x: x[0])
        pt_only_scored.sort(key=lambda x: x[0])
        
        # Selection strategy
        if competitive_pt_bike > 0:
            # If PT+bike is competitive, prioritize it
            stats['pt_bike_competitive'] += 1
            
            # Take more PT+bike alternatives when they're competitive
            A1_cap = max(L, mult_A1 * L, min(competitive_pt_bike, 2 * L))
            A2_cap = max(1, K_PT - 1)  # Reduce PT-only to make room
            
            kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
            kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]
            
            if kept_A1:
                stats['pt_bike_selected'] += 1
            
            print(f"OD {o}->{d}: {competitive_pt_bike} competitive PT+bike, selecting {len(kept_A1)} PT+bike + {len(kept_A2)} PT-only")
            
        else:
            # Standard selection when PT+bike is not competitive
            A1_cap = max(L, mult_A1 * L)
            A2_cap = K_PT
            
            kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
            kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]
        
        sel[(o, d)] = {"A1": kept_A1, "A2": kept_A2}
    
    print(f"\nInitial selection stats:")
    print(f"  Total ODs: {stats['total_ods']}")
    print(f"  ODs with competitive PT+bike: {stats['pt_bike_competitive']}")
    print(f"  ODs with PT+bike selected: {stats['pt_bike_selected']}")
    
    return sel

# ---- Capacity-aware greedy packer for initial A1 selection ----

from typing import Dict, List, Tuple

def pack_A1_capacity_aware(
    parsed: dict,
    lp_like,                     # your IncrementalBilevelLP (for station cap/inv, delta_ia)
    L: int,
    mult_A1: int = 3,
    # scoring knobs (same meaning as you already use)
    inv_lambda: float = 5.0,
    alpha_pos: float = 1.0,
    alpha_neg: float = 1.0,
    slack_cutoff: float = 0.0,
    inv_cutoff: float = 0.0,
    # “predicted uptake” cap for each arc (protects budgets while selecting)
    qhat_lambda: float = 0.25,   # fraction of Q_od used as a conservative upper bound
    # density smoothing (avoid divide-by-zero)
    eps_usage: float = 1e-9,
) -> Dict[Tuple[int, int], List[str]]:
    """
    Greedy 'multi-knapsack' selection of PT+Bike arcs (A1) that jointly respect station budgets.

    Returns:
        chosen[(o,d)] -> list of selected A1 arc_ids

    How it works (high level):
      - Build a global pool of candidate A1 arcs (all ODs).
      - For each candidate, compute:
          score = inventory-aware disutility (lower is better)  [uses _score_a1_pricefree_inv]
          qhat  = conservative uptake cap for this (o,d,a)
          usage_plus[i], usage_minus[i] based on delta_ia * qhat
          density = (-score) / (total_usage + eps)  # higher density = better benefit per budget
      - Sort candidates by density (desc), then try to pack while:
          • station up-budgets (C_i - inv_i) never go < 0 when adding +delta usage
          • station down-budgets (inv_i) never go < 0 when adding -delta usage
          • per-OD cap ≤ max(L, mult_A1*L)
    """

    # --- local helpers ---

    def _score_a1_pricefree_inv_local(o, d, a) -> float | None:
        # reuse your inventory-aware score function so the priorities won’t change
        # compared to your current heap-based scoring
        return _score_a1_pricefree_inv(
            parsed, lp_like, o, d, a,
            inv_lambda, alpha_pos, alpha_neg,
            slack_cutoff, inv_cutoff
        )

    def _qhat(o, d, a) -> float:
        """
        Conservative per-arc flow cap:
          qhat = min( Q_od,
                      qhat_lambda * Q_od,
                      min_i station_limit_i )
        where station_limit_i = (slack_up_i / delta) if delta>0,
                                (inv_i / -delta)     if delta<0,
                                +inf                 if delta=0
        """
        Qod = parsed["demands"][(o, d)]
        limit = qhat_lambda * Qod
        delta_map = lp_like.delta_ia.get(a, {})
        for i_str, delta in delta_map.items():
            if not delta:
                continue
            cap_i = lp_like.station_capacity[i_str]
            inv_i = lp_like.station_inventory[i_str]
            if delta > 0:
                slack_up = cap_i - inv_i
                if slack_up < 0:  # already overfull — treat as 0 capacity
                    return 0.0
                limit = min(limit, slack_up / float(delta) if delta != 0 else float('inf'))
            elif delta < 0:
                limit = min(limit, inv_i / float(-delta))
        return max(0.0, min(Qod, limit))

    # --- station budgets (what we must not exceed) ---
    budget_up   = {str(i): (lp_like.station_capacity[str(i)] - lp_like.station_inventory[str(i)])
                   for i in lp_like.stations_list}
    budget_down = {str(i): lp_like.station_inventory[str(i)]
                   for i in lp_like.stations_list}

    # --- per-OD cap for A1 ---
    per_od_cap = {}
    for (o, d) in parsed["OD_pairs"]:
        per_od_cap[(o, d)] = max(L, mult_A1 * L)

    # --- build global candidate pool with density ---
    cand = []  # list of tuples: (density, benefit, usage_sum, o, d, a, qhat, usage_plus_dict, usage_minus_dict)
    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"
        for arc in parsed["arcs_pt_bike"].get(od, []):
            a = arc["arc_id"]
            sc = _score_a1_pricefree_inv_local(o, d, a)
            if sc is None:
                # hard-forbidden by inventory cutoffs
                continue

            qh = _qhat(o, d, a)
            if qh <= 0.0:
                continue

            # compute station usage *if* we allocated qhat on this arc
            uplus = {}
            uminus = {}
            tot_use = 0.0
            for i_str, delta in lp_like.delta_ia.get(a, {}).items():
                if not delta:
                    continue
                if delta > 0:
                    amt = delta * qh
                    uplus[i_str] = amt
                    tot_use += amt
                elif delta < 0:
                    amt = (-delta) * qh
                    uminus[i_str] = amt
                    tot_use += amt

            # benefit = -score (since smaller sc = better)
            benefit = -float(sc)
            density = benefit / (tot_use + eps_usage)

            cand.append((density, benefit, tot_use, o, d, a, qh, uplus, uminus))

    # sort: higher density first (more bang per budget)
    cand.sort(key=lambda t: (-t[0], -t[1], t[2]))

    # --- greedy pack ---
    chosen: Dict[Tuple[int, int], List[str]] = {(o, d): [] for (o, d) in parsed["OD_pairs"]}

    for density, benefit, tot_use, o, d, a, qh, uplus, uminus in cand:
        # OD cap check
        if len(chosen[(o, d)]) >= per_od_cap[(o, d)]:
            continue

        # check if we can afford the usage in budgets
        ok = True
        for i_str, amt in uplus.items():
            if budget_up.get(i_str, 0.0) - amt < 0.0:
                ok = False
                break
        if ok:
            for i_str, amt in uminus.items():
                if budget_down.get(i_str, 0.0) - amt < 0.0:
                    ok = False
                    break

        if not ok:
            continue

        # accept: commit budgets
        for i_str, amt in uplus.items():
            budget_up[i_str] -= amt
        for i_str, amt in uminus.items():
            budget_down[i_str] -= amt
        chosen[(o, d)].append(a)

    return chosen

def make_initial_selection_A2_only(parsed, K_PT: int = 2) -> dict[tuple[int,int], dict[str, list[str]]]:
    """
    Build sel[(o,d)] with only PT-only (A2) top-K. Leave A1 empty;
    A1 will be filled by the capacity-aware packer.
    """
    sel = {}
    for (o, d) in parsed["OD_pairs"]:
        od = f"{o}_{d}"
        A2 = [(_score_pt_only(parsed, o, d, arc["arc_id"]), arc["arc_id"])
              for arc in parsed["arcs_pt_only"].get(od, [])]
        A2.sort(key=lambda t: t[0])
        kept_A2 = [aid for _, aid in A2[:K_PT]]
        sel[(o, d)] = {"A2": kept_A2, "A1": []}  # A1 empty on purpose
    return sel

# -------- Pipeline driver --------
class GreedyFixAndOptimize:
    """
    Greedy add–drop matheuristic:
      - Build restricted LP with initial selection
      - Forward add: try best-scored candidates; accept only if they improve objective
      - Backward prune: try dropping weak A1 arcs; accept if objective improves (or not worse)
      - Extract results and write JSON in your original format
    """
    """
    LNS fix-optimize-repair matheuristic:
        -   run_lns(...) picks a destroy set of weak A1 arcs (by flow & contribution),
        - chooses a small set of candidate additions from the heap,
        - evaluates the batch move on a fresh LP (safe & simple),
        - if improved, applies the same changes to the live LP.
    
    """



    def __init__(self,
                 parsed_data, *,
                 L: int, K_PT: int = 2, mult_A1: int = 4,
                 P_bar = 0.5, P_up = 4, pt_price = 2,
                 cost_bike = 0.6, parking_fee = 2.8, dep_cost = 0,
                 tolerance = 1e-3,
                 quiet = True, nodefile_dir = None, threads=4,
                 time_limit_eval: Optional[int] = None,
                # --- NEW: method selector and LNS knobs ---
                 search_method: str = "first_improvement",   # or "lns"
                 lns_iters: int = 10,
                 lns_destroy_k: int = 20,
                 lns_add_m: int = 30,
                 lns_impr_tol: float = 1e-4,
                 lns_rand_frac: float = 0.25):
        
        self.parsed = parsed_data
        self.L = L
        self.K_PT = K_PT
        self.mult_A1 = mult_A1

        self.lp = IncrementalBilevelLP(parsed_data,
                                       P_bar=P_bar, P_up=P_up, pt_price=pt_price,
                                       cost_bike=cost_bike, parking_fee=parking_fee, dep_cost=dep_cost,
                                       tolerance=tolerance, quiet=quiet,
                                       nodefile_dir=nodefile_dir, threads=threads,
                                       time_limit=time_limit_eval)
        
        #acceptance tolerances
        self.q_prune_tol        = 1e-8
        # caps and patience
        self.max_trial_add   = 100      # hard cap on trial-add solves
        self.max_trial_drop  = 100      # hard cap on trial-drop solves
        self.patience_add    = 10       # stop forward after this many non-improving trials
        self.patience_drop   = 10       # stop prune after this many non-improving trials
        self.trial_time_limit = 20      # seconds per trial LP copy
        self.rel_impr_tol_add  = 1e-4   # relax thresholds
        self.rel_impr_tol_drop = 1e-4
        
        # Search strategy: "first_improvement" (default) or "lns"
        self.search_method = search_method

        # inventory-aware scoring knobs
        self.inv_lambda   = 5.0     # weight of inventory penalty in the score
        self.alpha_pos    = 1.0     # coefficient for +delta (capacity consumption)
        self.alpha_neg    = 1.0     # coefficient for -delta (inventory drain)
        self.slack_cutoff = 0.0     # forbid if slack_up <= this
        self.inv_cutoff   = 0.0     # forbid if inv <= this


        #LNS Knobs
        self.lns_iters = lns_iters             # max lns iterations
        self.lns_destroy_k = lns_destroy_k         # how many A1 arcs to drop per iteration (global)
        self.lns_add_m = lns_add_m             # how many new candidates to allow per iteration (global)
        self.lns_impr_tol = lns_impr_tol        # accept if relative improvement exceeds this
        self.lns_rand_frac = lns_rand_frac       # random fraction of destroy set (diversification)




        t0 = time.perf_counter()

        self.sel = make_initial_selection_enhanced(parsed_data, L, K_PT, mult_A1)
        #self.sel = make_selections_together_pt_car(parsed_data, L=self.L, K_PT=self.K_PT, mult_A1=self.mult_A1, P_bar=P_bar, pt_price=pt_price, dep_cost=dep_cost, parking_fee=parking_fee,)


        #self.sel = make_initial_selection_A2_only(parsed_data, K_PT)
        '''
        # (b) run capacity-aware greedy packing for A1 only
        packed_A1 = pack_A1_capacity_aware(
            parsed=self.parsed,
            lp_like=self.lp,
            L=self.L,
            mult_A1=self.mult_A1,
            inv_lambda=self.inv_lambda,
            alpha_pos=self.alpha_pos,
            alpha_neg=self.alpha_neg,
            slack_cutoff=self.slack_cutoff,
            inv_cutoff=self.inv_cutoff,
            qhat_lambda=0.75,      # tune if you like
        )
        
        # (c) overwrite A1 selections per-OD with the packed, capacity-feasible set
        for (o, d) in self.parsed["OD_pairs"]:
            self.sel[(o, d)]["A1"] = packed_A1.get((o, d), [])
            '''
        t1 = time.perf_counter()

        self.heap = build_candidate_heap(
            parsed_data, self.sel,
            H_PT=3, H_A1=5,
            P_bar=P_bar, pt_price=pt_price,
            dep_cost=dep_cost, parking_fee=parking_fee
        )

        t2 = time.perf_counter()

        print(F"[init] selection = {t1-t0:.3f}s heap = {t2-t1:.3f}s total = {t2-t0:.3f}s")




    #---build initial model---

    def _build_initial(self):
        for (o,d), grp in self.sel.items():
            for aid in grp["A2"]:
                self.lp.add_pt_only(o,d,aid)
            for aid in grp["A1"]:
                self.lp.add_pt_bike(o,d,aid)


    # --- helpers to count present per OD and caps ---
    def _od_cap(self, kind: str) -> int:
        return self.K_PT if kind == "A2" else max(self.L, self.mult_A1 * self.L)

    def _present_by_od(self, kind: str) -> dict[tuple[int,int], list[str]]:
        bucket = {}
        pool = self.lp._present_A2 if kind == "A2" else self.lp._present_A1
        for (o, d, a) in pool:
            bucket.setdefault((o, d), []).append(a)
        return bucket


    # --- minimal live deactivation for PT-only (A2), mirroring your A1 drop technique ---
    def _deactivate_pt_only_live(self, o: int, d: int, a: str) -> None:
        """
        Fix q_{od,a} = 0 and relax its PT dual row in the LIVE model (no deletions).
        Also update lp bookkeeping set for A2.
        """
        m = self.lp.m
        q = m.getVarByName(f"q_{o}_{d}_{a}")
        if q is not None:
            q.LB = 0.0; q.UB = 0.0
        crow = m.getConstrByName(f"gammaPT_{o}_{d}_{a}")
        if crow is not None:
            try:
                crow.RHS = 1e9  # big-M relaxation
            except:
                pass
        # keep the set consistent
        if (o, d, a) in self.lp._present_A2:
            self.lp._present_A2.remove((o, d, a))

    # --- ranking (weakest first) re-used for trimming ---
    def _rank_A1_weak(self) -> list[tuple[float, float, tuple[int,int,str]]]:
        ranked = []
        for (o, d, a) in list(self.lp._present_A1):
            qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
            zv = self.lp.z[(o, d, a)].X if (o, d, a) in self.lp.z else 0.0
            q_coeff = 2 * self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o, d, a), 0.0)
            contrib = zv + q_coeff * qv
            ranked.append((qv, contrib, (o, d, a)))
        ranked.sort(key=lambda t: (t[0], t[1]))  # small q, then small contrib
        return ranked

    def _rank_A2_weak(self) -> list[tuple[float, tuple[int,int,str]]]:
        ranked = []
        for (o, d, a) in list(self.lp._present_A2):
            qv = self.lp.q[(o, d, a)].X if (o, d, a) in self.lp.q else 0.0
            ranked.append((qv, (o, d, a)))
        ranked.sort(key=lambda t: t[0])  # smallest flow first
        return ranked

    # --- reconciliation pass: enforce per-OD caps on the LIVE model ---
    def _enforce_od_caps_live(self) -> None:
        """
        Ensure that, for each OD, number of offered A1 and A2 does not exceed caps.
        Uses live-model deactivation (fix to zero + relax gamma row), no deletions.
        Re-optimizes once if any change was made.
        """
        changed = False

        # A1 trim
        by_od_A1 = self._present_by_od("A1")
        if by_od_A1:
            # build weakness order once, then pick per OD
            weakA1 = self._rank_A1_weak()
            # map for quick position
            pos = {t[2]: i for i, t in enumerate(weakA1)}
            for (o, d), lst in by_od_A1.items():
                cap = self._od_cap("A1")
                if len(lst) > cap:
                    # pick the weakest ones among this OD
                    lst_sorted = sorted(lst, key=lambda a: pos.get((o, d, a), 10**9))
                    to_drop = lst_sorted[cap:]
                    for a in to_drop:
                        # your existing A1 deactivation (already safe & consistent)
                        if (o, d, a) in self.lp._present_A1:
                            self.lp.deactivate_pt_bike(o, d, a)
                            changed = True

        # A2 trim
        by_od_A2 = self._present_by_od("A2")
        if by_od_A2:
            weakA2 = self._rank_A2_weak()
            pos2 = {t[1]: i for i, t in enumerate(weakA2)}
            for (o, d), lst in by_od_A2.items():
                cap = self._od_cap("A2")
                if len(lst) > cap:
                    lst_sorted = sorted(lst, key=lambda a: pos2.get((o, d, a), 10**9))
                    to_drop = lst_sorted[cap:]
                    for a in to_drop:
                        self._deactivate_pt_only_live(o, d, a)
                        changed = True

        if changed:
            self.lp.optimize()  # one reopt after all fixes

            

    #---forward phase---

    def run_forward(self,max_add: int = 1000):
        
        # Build the initial restricted model
        self._build_initial()

        # --- BASE SOLVE: let Gurobi choose (concurrent) and no timelimit ---
        # Save current settings to restore later
        old_method = self.lp.m.Params.Method
        old_timelimit = getattr(self.lp.m.Params, "TimeLimit", 0)  # 0 means no limit

        try:
            # Free method choice (concurrent) for the big initial solve
            #self.lp.m.Params.Method = -1      # concurrent/free
            #self.lp.m.Params.TimeLimit = 0    # no limit for base solve
            base = self.lp.optimize()
        finally:
            # For all subsequent incremental re-optimizations, use Dual Simplex
            self.lp.m.Params.Method = 1       # Dual Simplex reopt is fastest for small changes
            # Keep no TimeLimit for reopt (0) unless you want one; restore otherwise
            #self.lp.m.Params.TimeLimit = 0 if old_timelimit == 0 else old_timelimit

        if base is None:
            print("[forward] base failed to produce a feasible solution.")
            return None

        print(f"[forward] base objective = {base}")
        self.lp.debug_after_opt("forward_base")
        self.lp.debug_check_strong_duality()

        added = 0
        trials = 0
        non_improve_streak = 0

        while self.heap and added < max_add:
            if trials >= self.max_trial_add or non_improve_streak >= self.patience_add:
                break

            _, (o,d,a), kind = heapq.heappop(self.heap)
            trial = self._trial_add_value(o,d,a,kind)

            trials += 1
            if trial is None:
                non_improve_streak += 1
                continue

            if trial > base * (1 + self.rel_impr_tol_add):
                # accept
                if kind == "A2":
                    self.lp.add_pt_only(o,d,a)
                else:
                    self.lp.add_pt_bike(o,d,a)
                base = self.lp.optimize()
                added += 1
                non_improve_streak = 0
                self.lp.debug_after_opt(f"forward_add_{added}")
            else:
                non_improve_streak += 1
        
        self._enforce_od_caps_live()
        base = self.lp.objective_value()  # or re-read after reopt in the function

        return base

    
    def _trial_add_value(self,o,d,a, kind) -> Optional[float]:
        """Evaluate objective of adding a candidate using a model COPY (cheap, safe)."""

        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 1
            mcopy.Params.Method = 1 #Dual Simplex

            Qod = self.lp.demands[(o,d)]
            gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
            sd_c = mcopy.getConstrByName("StrongDuality")
            dem_c = mcopy.getConstrByName(f"demand_{o}_{d}")

            if kind == "A2":
                q = mcopy.addVar(lb=0, ub=Qod, vtype= GRB.CONTINUOUS, name = f"trial_q_{o}_{d}_{a}")
                    
                    #dual feasibility KKT for pt only

                rhs = (-0.756
                        + 0.779 * self.lp.pt_price
                        + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                        + 0.208 * self.parsed["transfer_time_min"][(o, d, a)] )
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaPT_{o}_{d}_{a}")

                    #demand
                mcopy.chgCoeff(dem_c, q, +1)

                #Strong Duality for pt only

                coeff_q = (-0.756
                        + 0.779 * self.lp.pt_price
                        + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                        + 0.208 * self.parsed["transfer_time_min"][(o, d, a)] )
                mcopy.chgCoeff(sd_c, q, coeff_q)

                q.Obj = 0
                
            else: #pt+bike constraints
                
                p = mcopy.addVar(lb=self.lp.P_bar, ub = self.lp.P_up, vtype=GRB.CONTINUOUS, name = f"trial_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0,ub = Qod, vtype=GRB.CONTINUOUS, name = f"trial_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-GRB.INFINITY, ub = GRB.INFINITY, vtype=GRB.CONTINUOUS, name = f"trial_z_{o}_{d}_{a}")
                
                # McCormick
                mcopy.addConstr(z >= self.lp.P_bar*q,                              name=f"trial_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= self.lp.P_up  * q,                            name=f"trial_z_max1_{o}_{d}_{a}")
                mcopy.addConstr(z >= self.lp.P_up*q + p*Qod - self.lp.P_up*Qod,    name=f"trial_z_min2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod,  name=f"trial_z_max2_{o}_{d}_{a}")

                #Dual feasibility for pt+bike

                rhs = ( 0.0 + (-0.756)
                        + 0.779 * self.lp.pt_price
                        + 0.689 * p
                        + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                        + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                        + 0.199 * self.parsed["transfer_time_min"][(o, d, a)] )
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaA_{o}_{d}_{a}")

                #demand 

                mcopy.chgCoeff(dem_c, q, +1)

                #capacity

                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),       q, delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)
                # SD
                coeff_q = ( 0.779 * self.lp.pt_price
                            + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                            + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                            + 0.199 * self.parsed["transfer_time_min"][(o, d, a)]
                            + (0.0 + -0.756) )
                mcopy.chgCoeff(sd_c, q, coeff_q)
                mcopy.chgCoeff(sd_c, z, 0.689)
                # objective
                z.Obj += 1.0
                ridership = 2.0 * self.lp.P_up
                resource  = self.lp._resource_coeff.get((o, d, a), 0.0)
                q.Obj += (ridership - self.lp.cost_bike + resource)

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None
        
        except Exception:
            return None

    # --- backward phase (prune)

    def prune(self, max_drops: int = 200):
        """Backward elimination of weak A1 arcs."""

        base = self.lp.objective_value()
        if base is None:
            return None

        #Rank A1 by small q then contribution

        cand = []

        m = self.lp.m

        if m.SolCount == 0:
            return base
        
        for (o,d,a) in list(self.lp._present_A1):

            qv = self.lp.q[(o,d,a)].X
            zv = self.lp.z[(o,d,a)].X
            q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o,d,a),0)
            contrib = zv + q_coeff*qv
            cand.append((qv,contrib,(o,d,a)))
        cand.sort(key = lambda t: (t[0], t[1])) #smallest q/contrib first

        drops = 0
        trials = 0
        non_improve_streak = 0

        for qv, contrib, (o,d,a) in cand:
            if drops >= max_drops or trials >= self.max_trial_drop or non_improve_streak >= self.patience_drop:
                break

            trial = self._trial_drop_value(o,d,a)
            trials += 1

            if trial is None:
                non_improve_streak += 1
                continue

            improve = trial - base
            if improve >= abs(base)*self.rel_impr_tol_drop or (qv <= self.q_prune_tol and improve > -abs(base)*self.rel_impr_tol_drop):
                self.lp.deactivate_pt_bike(o,d,a)
                base = self.lp.optimize()
                drops += 1
                non_improve_streak = 0
            else:
                non_improve_streak += 1
        self.lp.debug_after_opt("prune_end")
        self.lp.debug_check_strong_duality()

        return base

    

    def _trial_drop_value(self, o,d,a) -> Optional[float]:
        """Evaluate objective after dropping (o,d,a) using a model copy."""

        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 1
            mcopy.Params.Method = 1 #dual simplex

            

            q = mcopy.getVarByName(f"q_{o}_{d}_{a}")
            p = mcopy.getVarByName(f"p_{o}_{d}_{a}")
            z = mcopy.getVarByName(f"z_{o}_{d}_{a}")
            
            if q is None:
                return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None
            q.LB = 0.0; q.UB = 0.0
            if p is not None: p.LB = 0.0; p.UB = 0.0
            if z is not None: z.LB = 0.0; z.UB = 0.0

            crow = mcopy.getConstrByName(f"gammaA_{o}_{d}_{a}")
            
            if crow is None:
                crow = mcopy.getConstrByName(f"gammaPT_{o}_{d}_{a}")
            if crow is not None:
                try:
                    crow.RHS = 1e9
                except:
                    pass

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None
        except Exception:
            return None
        
    # --- run both phases and write JSON ---

    def run(self, max_add: int = 1000, max_drops: int = 200):
        t0=time.time()

        if getattr(self, "search_method", "first_improvement") == "lns":
            best_final = self.run_lns()
        else:
                
            best_forward = self.run_forward(max_add=max_add)
            #best_forward = self.run_forward_with_fresh_trials(max_add=50)
            best_final = self.prune(max_drops=max_drops)
        t1=time.time()
        return best_final, (t1-t0)
    

    def write_json(self, json_file_path: str, save_folder: str, P_bar: float, capacity, inventory_level, q_tol: float = 0):
        
        # Build suffix for naming
        
        import os
        
        os.makedirs(save_folder, exist_ok=True)
        json_filename = os.path.basename(json_file_path)
        base_name = os.path.basename(json_file_path).replace(".json", "")
        if inventory_level is not None:
            low, high = inventory_level
            suffix = f"_{P_bar}_{capacity}_{low}_{high}"
        else:
            suffix = f"_{P_bar}_{capacity}"

        sol_name = f"{base_name}{suffix}_solution.json"
        sol_path = os.path.join(save_folder, sol_name)

        # Extract rows
        rows = self.lp.extract_solution_df(q_tol=q_tol)
        # LP → no MIP gap; report 0.0 if optimal, else None
        status = self.lp.m.Status
        if status == GRB.OPTIMAL:
            gap_pct = 0.0
        else:
            try:
                gap_pct = float(self.lp.m.MIPGap) * 100.0
            except Exception:
                gap_pct = None

        sol_obj = {
            "Solution Time (s)": None,  # fill by caller
            "Objective Value":  self.lp.objective_value(),
            "Gap (%)":          gap_pct,
            "instances":        rows
        }
        
        # Write
        with open(sol_path, "w", encoding="utf-8") as f:
            json.dump(sol_obj, f, indent=4, ensure_ascii=False)

        return sol_path


    #------ Alternative forward phase with fresh model building for trials ------
    def _trial_add_value_fresh_build(self, o, d, a, kind) -> Optional[float]:
        """
        Alternative trial method: build a completely fresh IncrementalBilevelLP
        with the candidate added. More expensive but eliminates basis/state issues.
        """
        try:
            # Create fresh LP instance with same parameters
            trial_lp = IncrementalBilevelLP(
                self.parsed,
                P_bar=self.lp.P_bar, P_up=self.lp.P_up, theta=self.lp.theta,
                pt_price=self.lp.pt_price, cost_bike=self.lp.cost_bike,
                parking_fee=self.lp.parking_fee, dep_cost=self.lp.dep_cost,
                tolerance=self.lp.tolerance, quiet=True,
                time_limit=self.trial_time_limit
            )
            
            # Add all currently present alternatives
            for (o2, d2), grp in self.sel.items():
                for aid in grp["A2"]:
                    if (o2, d2, aid) in self.lp._present_A2:
                        trial_lp.add_pt_only(o2, d2, aid)
                for aid in grp["A1"]:
                    if (o2, d2, aid) in self.lp._present_A1:
                        trial_lp.add_pt_bike(o2, d2, aid)
            
            # Add the trial candidate
            if kind == "A2":
                trial_lp.add_pt_only(o, d, a)
            else:
                trial_lp.add_pt_bike(o, d, a)
            
            # Optimize and return objective
            obj_val = trial_lp.optimize()
            return obj_val
            
        except Exception as e:
            print(f"Exception in fresh trial for {kind} arc {o}->{d}->{a}: {e}")
            return None

    def run_forward_with_fresh_trials(self, max_add: int = 1000):
        """
        Modified forward phase using fresh model rebuilding for trials.
        Use this instead of run_forward() to test if the issue is basis-related.
        """
        
        self._build_initial()
        base = self.lp.optimize()
        if base is None:
            base = -1e100
        
        print(f"[forward_fresh] base objective = {base}")
        self.lp.debug_after_opt("forward_base")
        
        added = 0
        trials = 0
        non_improve_streak = 0
        
        while self.heap and added < max_add:
            if trials >= self.max_trial_add or non_improve_streak >= self.patience_add:
                break
            
            _, (o, d, a), kind = heapq.heappop(self.heap)
            
            # Use fresh model building for trial
            trial = self._trial_add_value_fresh_build(o, d, a, kind)
            
            trials += 1
            if trial is None:
                non_improve_streak += 1
                continue
            
            improvement = trial - base
            rel_improvement = improvement / abs(base) if abs(base) > 1e-10 else improvement
            
            print(f"  Trial {trials}: {kind} {o}->{d}->{a}, obj={trial:.3f}, base={base:.3f}, "
                f"abs_impr={improvement:.3f}, rel_impr={rel_improvement:.6f}")
            
            if improvement > abs(base) * self.rel_impr_tol_add:
                # Accept
                if kind == "A2":
                    self.lp.add_pt_only(o, d, a)
                else:
                    self.lp.add_pt_bike(o, d, a)
                
                base = self.lp.optimize()
                added += 1
                non_improve_streak = 0
                print(f"    ✓ ACCEPTED! New objective: {base:.3f}")
                self.lp.debug_after_opt(f"forward_add_{added}")
            else:
                non_improve_streak += 1
                print(f"    ✗ Rejected (insufficient improvement)")
        
        print(f"[forward_fresh] Final: added {added} alternatives, base objective = {base}")
        return base

    #------ Large Neigborhood Search ------

    def _snapshot_present_sets(self):
        """Return shallow snapshots of currently present A1/A1 arc triplets"""
        present_A1 = set(self.lp._present_A1)
        present_A2 = set(self.lp._present_A2)
        return present_A1, present_A2
    
    def _trial_batch_fresh_build(self, drops_A1: set[tuple[int,int,str]], adds_A1: set[tuple[int,int,str]], adds_A2: set[tuple[int,int,str]]):
        '''
        Builds a fresh IncrementalBilevelLP that mirro the current live selection but applies a batch destroy/repair move:
            - Remove all (o,d,a) in drops_A1 from A1
            - Add all in adds_A1 / adds_A2 
        return the objective value or None on failure        
        '''
        try: 
            trial_lp = IncrementalBilevelLP(self.parsed, P_bar = self.lp.P_bar, P_up=self.lp.P_up, theta=self.lp.theta,
                pt_price=self.lp.pt_price, cost_bike=self.lp.cost_bike,
                parking_fee=self.lp.parking_fee, dep_cost=self.lp.dep_cost,
                tolerance=self.lp.tolerance, quiet=True,
                time_limit=self.trial_time_limit
            )
            present_A1, present_A2 = self._snapshot_present_sets()

            #Re-add all live arcs except those in the drop set (for A1)

            for (o,d,a) in present_A2:
                trial_lp.add_pt_only(o,d,a)
            for (o,d,a) in present_A1:
                if (o,d,a) not in drops_A1:
                    trial_lp.add_pt_bike(o,d,a)
            
            # Add proposed new arcs

            for (o,d,a) in adds_A2:
                trial_lp.add_pt_only(o,d,a)
            for (o,d,a) in adds_A1:
                trial_lp.add_pt_bike(o,d,a)
            
            return trial_lp.optimize()
        
        except Exception:
            return None

        # LNS Core #
    
    def run_lns(self) -> Optional[float]:
        '''
        Start from incumbent built by _build_initial() + base_optimize()
        For a fixed number of iterations:
            - Destroy: drop k weak A1 arcs (mix of worst and random)
            - Repair: allow m new candidates from the heap
            - Trial: Solve a new LP, if improved, accept in Live LP       
        '''

        #Build and solve the initial model
        self._build_initial()
        base = self.lp.optimize()

        if base is None:
            print("[LNS] Base solve failed")
            return None
        print(f"[LNS] base objective = {base}")

        for it in range(1, self.lns_iters + 1):
            present_A1, present_A2 = self._snapshot_present_sets()

            if not present_A1:
                print(f"[LNS {it}] No A1 arcs to destroy, stopping")
                break
            
            # ---- Rank A1 by (q, contribution)
            ranked = []
            for (o,d,a) in present_A1:
                qv = self.lp.q[(o,d,a)].X
                zv = self.lp.z[(o,d,a)].X if (o,d,a) in self.lp.z else 0
                q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o, d, a), 0.0)
                contrib = zv + q_coeff * qv
                ranked.append((qv, contrib, (o,d,a)))
            ranked.sort(key = lambda t: (t[0]-t[1])) #weakest first
            
            
            # ---- Destroy set: mostly weakest + some random
            k = min(self.lns_destroy_k, len(ranked))
            base_cut = int((1 - self.lns_rand_frac)*k)
            deterministic = [t[2] for t in ranked[:base_cut]]

            remaining = [t[2] for t in ranked[base_cut:]]
            random_add = random.sample(remaining, k-base_cut) if remaining and k-base_cut>0 else []
            drop_set = set(deterministic + random_add)

            
            # ---- Repair candidates: take top-m from heap that are not present

            adds_A1, adds_A2 = set(), set()
            m = self.lns_add_m
            tmp = []

            while self.heap and len(adds_A1) + len(adds_A2) < m:
                score, key, kind = heapq.heappop(self.heap)
                tmp.append((score, key, kind))

                o,d,a = key

                if kind == "A1" and (o,d,a) not in present_A1 and (o,d,a) not in drop_set:
                    adds_A1.add((o,d,a))
                elif kind == "A2" and (o,d,a) not in present_A2:
                    adds_A2.add((o,d,a))
            
            for item in tmp:
                heapq.heappush(self.heap, item)

            #Trial on fresh LP

            #trial_val = self._trial_batch_fresh_build(drop_set, adds_A1, adds_A2)
            trial_val = self._trial_batch_on_copy(drop_set, adds_A1, adds_A2)

            if trial_val is None:
                print(f"[LNS {it}] Trial failed, continue.")
                continue

            rel_impr = (trial_val - base) / abs(base) if abs(base) > 1e-10 else (trial_val - base)
            print(f"[LNS {it}] trial={trial_val:.6f} base={base:.6f} rel_impr={rel_impr:.3e}")
            print(f"(drop {len(drop_set)}, add {len(adds_A1) + len(adds_A2)})")

            if rel_impr > self.lns_impr_tol:
                #Accept to live model

                for (o,d,a) in drop_set:
                    if (o,d,a) in self.lp._present_A1:
                        self.lp.deactivate_pt_bike(o,d,a)
                for (o,d,a) in adds_A2:
                    self.lp.add_pt_only(o,d,a)
                for (o,d,a) in adds_A1:
                    self.lp.add_pt_bike(o,d,a)
                base = self.lp.optimize()
                print(f"[LNS {it}] ✓ accepted, new base={base:.6f}")
            else:
                print(f"[LNS {it}] ✗ rejected")
        
        self._enforce_od_caps_live()
        base = self.lp.objective_value()
        
        return base
    
    def _trial_batch_on_copy(
        self,
        drops_A1: set[tuple[int,int,str]],
        adds_A1: set[tuple[int,int,str]],
        adds_A2: set[tuple[int,int,str]]
    ) -> Optional[float]:
        """
        Evaluate a batch destroy/repair move by copying the live model,
        applying (drops, adds), and re-optimizing with dual simplex.

        Returns objective value on success, else None.
        """
        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 1
            mcopy.Params.Method = 1  # Dual Simplex for fast reopt

            # Convenience handles to global rows used in trial add
            sd_c = mcopy.getConstrByName("StrongDuality")

            # --- 1) APPLY DROPS: fix present A1 arc vars to zero + relax their gamma row ---
            for (o, d, a) in drops_A1:
                q = mcopy.getVarByName(f"q_{o}_{d}_{a}")
                p = mcopy.getVarByName(f"p_{o}_{d}_{a}")
                z = mcopy.getVarByName(f"z_{o}_{d}_{a}")

                if q is not None:
                    q.LB = 0.0; q.UB = 0.0
                if p is not None:
                    p.LB = 0.0; p.UB = 0.0
                if z is not None:
                    z.LB = 0.0; z.UB = 0.0

                # Relax original gamma row for this arc if it exists
                crow = mcopy.getConstrByName(f"gammaA_{o}_{d}_{a}")
                if crow is None:
                    crow = mcopy.getConstrByName(f"gammaPT_{o}_{d}_{a}")
                if crow is not None:
                    try:
                        crow.RHS = 1e9
                    except:
                        pass

            # --- 2) APPLY ADDS: add PT-only and PT+bike blocks (same as _trial_add_value) ---
            # We need gamma_{o}_{d}, demand_{o}_{d}, and station rows by name
            # (this mirrors your single-arc trial construction).

            for (o, d, a) in adds_A2:
                Qod = self.lp.demands[(o, d)]
                gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
                dem_c   = mcopy.getConstrByName(f"demand_{o}_{d}")

                # variables
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"batch_q_{o}_{d}_{a}")

                # dual feasibility for PT-only
                rhs = (-0.756
                       + 0.779 * self.lp.pt_price
                       + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                       + 0.208 * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"batch_gammaPT_{o}_{d}_{a}")

                # demand + SD coefficients
                mcopy.chgCoeff(dem_c, q, +1.0)

                coeff_q = (-0.756
                           + 0.779 * self.lp.pt_price
                           + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                           + 0.208 * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.chgCoeff(sd_c, q, coeff_q)

                # objective: PT-only trial contributes via dual side; q has no direct coef
                q.Obj = 0.0

            for (o, d, a) in adds_A1:
                Qod = self.lp.demands[(o, d)]
                gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
                dem_c   = mcopy.getConstrByName(f"demand_{o}_{d}")

                # variables
                p = mcopy.addVar(lb=self.lp.P_bar, ub=self.lp.P_up, vtype=GRB.CONTINUOUS, name=f"batch_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"batch_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"batch_z_{o}_{d}_{a}")

                # McCormick for z = p*q (same as trial)
                mcopy.addConstr(z >= self.lp.P_bar * q,                               name=f"batch_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= self.lp.P_up  * q,                               name=f"batch_zmax1_{o}_{d}_{a}")
                mcopy.addConstr(z >= self.lp.P_up*q + p*Qod - self.lp.P_up*Qod,       name=f"batch_zmin2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod,     name=f"batch_zmax2_{o}_{d}_{a}")

                # dual feasibility for PT+bike
                rhs = ((0.0 + -0.756)
                       + 0.779 * self.lp.pt_price
                       + 0.689 * p
                       + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                       + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                       + 0.199 * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"batch_gammaA_{o}_{d}_{a}")

                # demand balance
                mcopy.chgCoeff(dem_c, q, +1.0)

                # station capacity & nonnegativity rows
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if not delta:
                        continue
                    mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),        q, delta)
                    mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)

                # Strong duality row
                coeff_q = (0.779 * self.lp.pt_price
                           + 0.101 * self.parsed["pt_time_min"][(o, d, a)]
                           + 0.108 * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                           + 0.199 * self.parsed["transfer_time_min"][(o, d, a)]
                           + (0.0 + -0.756))
                mcopy.chgCoeff(sd_c, q, coeff_q)
                mcopy.chgCoeff(sd_c, z, 0.689)

                # objective contributions
                z.Obj += 1.0
                ridership = 2.0 * self.lp.P_up
                resource  = self.lp._resource_coeff.get((o, d, a), 0.0)
                q.Obj += (ridership - self.lp.cost_bike + resource)

            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None

        except Exception:
            return None





        

