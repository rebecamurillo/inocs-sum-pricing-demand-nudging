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
import heapq
from concurrent.futures import ThreadPoolExecutor
from incremental_lp import IncrementalBilevelLP
from collections import defaultdict
import math


# -------- Scoring functions (lower = better) --------

def _score_pt_only(parsed, o, d, a, ASC_PT = -0.756,    
                   BETA_Cost_PT   = 0.779,
                   BETA_Time_PT   = 0.101,
                   BETA_TR_PT     = 0.208,) -> float:
    return (ASC_PT
            + BETA_Time_PT * parsed["pt_time_min"][(o, d, a)]
            + BETA_TR_PT   * parsed["transfer_time_min"][(o, d, a)])

def _score_a1_pricefree(parsed, o, d, a,
    ASC_PT=-0.756, ASC_BIKE=0.0, 
    BETA_Cost_BIKE = 0.689,
    BETA_Time_BIKE = 0.108,
    BETA_TR_BIKE   = 0.199,
    BETA_Cost_PT   = 0.779,
    BETA_Time_PT   = 0.101,
    BETA_TR_PT     = 0.208) -> float:

    return (ASC_PT + ASC_BIKE
            + BETA_Time_PT   * parsed["pt_time_min"][(o, d, a)]
            + BETA_Time_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
            + BETA_TR_BIKE  * parsed["transfer_time_min"][(o, d, a)])


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

# -------- Pipeline driver --------
class GreedyFixAndOptimize:
    """
    Greedy add–drop matheuristic:
      - Make an initial selection of arcs per OD based on disutility. A1 arcs are selected based on competitiveness with car and PT. PT arcs selected based on their disutility. 
      - We select K_PT PT-only arcs and up to mult_A1*L PT+bike arcs per OD.
      - Build restricted LP with initial selection and solve LP.
      - Build a heap of candidates (PT-only and PT+bike) scored by utility and per OD. Then create a global priority queue with min scores. Per OD we keep H_PT PT-only and H_A1 PT+bike candidates.
      - Forward add: try best-scored candidates from priority queue; accept only if they improve objective
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
                H_PT: int = 3, H_A1: int = 5,
                P_bar = 0.5, P_up = 4, pt_price = 2,
                cost_bike = 0.6, parking_fee = 2.8, dep_cost = 0,
                tolerance = 1e-3,
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
                quiet = True, nodefile_dir = None, threads=4,
                time_limit_eval: Optional[int] = None,
                patience_add: int = 100,
                max_trial_add: int = 100,
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

        self.H_PT = H_PT
        self.H_A1 = H_A1


        self.lp = IncrementalBilevelLP(parsed_data,
                                       P_bar=P_bar, P_up=P_up, pt_price=pt_price,
                                       cost_bike=cost_bike, parking_fee=parking_fee, dep_cost=dep_cost,
                                       tolerance=tolerance, quiet=quiet,
                                       nodefile_dir=nodefile_dir, threads=threads,
                                       time_limit=time_limit_eval)
        
        #acceptance tolerances
        self.q_prune_tol        = 1e-8
        # caps and patience
        self.max_trial_add   = max_trial_add      # hard cap on trial-add solves
        self.max_trial_drop  = 100      # hard cap on trial-drop solves
        self.patience_add    = patience_add       # stop forward after this many non-improving trials
        self.patience_drop   = 100      # stop prune after this many non-improving trials
        self.trial_time_limit = 20      # seconds per trial LP copy
        self.rel_impr_tol_add  = 1e-4   # relative improvement tolerance for additions 
        self.rel_impr_tol_drop = 1e-4   # relative improvement tolerance for drops
        
        # Search strategy: "first_improvement" (default) or "lns"
        self.search_method = search_method

        #LNS Knobs
        self.lns_iters = lns_iters             # max lns iterations
        self.lns_destroy_k = lns_destroy_k         # how many A1 arcs to drop per iteration (global)
        self.lns_add_m = lns_add_m             # how many new candidates to allow per iteration (global)
        self.lns_impr_tol = lns_impr_tol        # accept if relative improvement exceeds this
        self.lns_rand_frac = lns_rand_frac       # random fraction of destroy set (diversification)

        t0 = time.perf_counter()

        self.sel = self.make_initial_selection_enhanced()

        t1 = time.perf_counter()

        #self.heap = self.build_candidate_heap()

        #t2 = time.perf_counter()

        #print(F"[init] selection = {t1-t0:.3f}s heap = {t2-t1:.3f}s total = {t2-t0:.3f}s")
        print(F"[init] selection = {t1-t0:.3f}s ")


# -------- Initial selection & candidate heap --------

    def make_initial_selection_enhanced(self):
        """
        Enhanced initial selection that ensures PT+bike gets a fair chance:
        1. For each OD, identify if ANY PT+bike arc is competitive with car at P_bar
        2. If so, select the most promising PT+bike arcs even if PT-only exists
        3. Use a more balanced selection between PT-only and PT+bike
        Uses ASCs/Betas from self (class init) and prices from self.lp.
        """
        parsed = self.parsed

        # environment/pricing from the LP that was built in __init__
        P_bar       = self.lp.P_bar
        pt_price    = self.lp.pt_price
        dep_cost    = self.lp.dep_cost
        parking_fee = self.lp.parking_fee

        # short-hands for choice parameters from class init
        ASC_PT, ASC_BIKE, ASC_CAR = self.ASC_PT, self.ASC_BIKE, self.ASC_CAR

        BETA_Cost_BIKE = self.BETA_Cost_BIKE
        BETA_Time_BIKE = self.BETA_Time_BIKE
        BETA_TR_BIKE   = self.BETA_TR_BIKE

        BETA_Cost_PT   = self.BETA_Cost_PT
        BETA_Time_PT   = self.BETA_Time_PT
        BETA_TR_PT     = self.BETA_TR_PT

        BETA_Cost_Car  = self.BETA_Cost_Car
        BETA_Cost_park = self.BETA_Cost_park
        BETA_Time_Car  = self.BETA_Time_Car

        L, K_PT, mult_A1 = self.L, self.K_PT, self.mult_A1

        sel = {}
        stats = {'total_ods': 0, 'pt_bike_competitive': 0, 'pt_bike_selected': 0}
        surge_applied = 0  # Track surge applications

        for (o, d) in parsed["OD_pairs"]:
            od = f"{o}_{d}"
            stats['total_ods'] += 1

            # --- best Car utility ---
            best_car_util = float('inf')
            for arc in parsed["car_paths"].get(od, []):
                a = arc["arc_id"]
                F  = parsed["total_cost_car"][(o, d, a)]
                Tt = parsed["travel_time_min"][(o, d, a)]
                car_util = (ASC_CAR
                            + BETA_Cost_Car * (F - dep_cost)
                            + BETA_Cost_park * parking_fee
                            + BETA_Time_Car * Tt)
                if car_util < best_car_util:
                    best_car_util = car_util

            # --- score PT+bike at P_bar ---
            pt_bike_scored = []
            competitive_pt_bike = 0
            for arc in parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                pt_bike_util = (ASC_PT + ASC_BIKE
                                + BETA_Cost_PT * pt_price
                                + BETA_Cost_BIKE * P_bar
                                + BETA_Time_PT * parsed["pt_time_min"][(o, d, a)]
                                + BETA_Time_BIKE * parsed["bike_time_min"].get((o, d, a), 0.0)
                                + BETA_TR_BIKE * parsed["transfer_time_min"][(o, d, a)])
                pt_bike_scored.append((pt_bike_util, a))
                if pt_bike_util < best_car_util:
                    competitive_pt_bike += 1

            # --- score PT-only ---
            pt_only_scored = []
            for arc in parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                pt_only_util = (ASC_PT
                                + BETA_Cost_PT * pt_price
                                + BETA_Time_PT * parsed["pt_time_min"][(o, d, a)]
                                + BETA_TR_PT * parsed["transfer_time_min"][(o, d, a)])
                pt_only_scored.append((pt_only_util, a))

            # sort (lower utility better)
            pt_bike_scored.sort(key=lambda x: x[0])
            pt_only_scored.sort(key=lambda x: x[0])
            
            '''
            # selection policy
            if competitive_pt_bike > 0:
                stats['pt_bike_competitive'] += 1
                A1_cap = max(mult_A1 * L, competitive_pt_bike)
                A2_cap = max(1, K_PT)
                kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
                kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]
                if kept_A1:
                    stats['pt_bike_selected'] += 1
                if not getattr(self, "quiet", True):
                    print(f"OD {o}->{d}: {competitive_pt_bike} competitive PT+bike, "
                        f"selecting {len(kept_A1)} PT+bike + {len(kept_A2)} PT-only")
            else:
                A1_cap = max(L, mult_A1 * L)
                A2_cap = K_PT
                kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
                kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]

            sel[(o, d)] = {"A1": kept_A1, "A2": kept_A2}
            
        if not getattr(self, "quiet", True):
            print("\nInitial selection stats:")
            print(f"  Total ODs: {stats['total_ods']}")
            print(f"  ODs with competitive PT+bike: {stats['pt_bike_competitive']}")
            print(f"  ODs with PT+bike selected: {stats['pt_bike_selected']}")
        '''
        # selection policy

            if competitive_pt_bike > 0:
                stats['pt_bike_competitive'] += 1
                base_A1_cap = math.ceil(mult_A1 * L)  # Round up to integer
                
                if competitive_pt_bike > L:
                    # Surge case: limit to L but track surge
                    A1_cap = L
                    surge_applied += 1
                    if not getattr(self, "quiet", True):
                        print(f"OD {o}->{d}: {competitive_pt_bike} competitive PT+bike (surge), "
                            f"selecting {L} PT+bike (capped)")
                else:
                    # Normal case: use the higher of base cap or competitive count
                    A1_cap = max(base_A1_cap, competitive_pt_bike)
                    if not getattr(self, "quiet", True):
                        print(f"OD {o}->{d}: {competitive_pt_bike} competitive PT+bike, "
                            f"selecting {A1_cap} PT+bike + {K_PT} PT-only")
                
                A2_cap = K_PT
                kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
                kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]
                if kept_A1:
                    stats['pt_bike_selected'] += 1
                    
            else:
                # No competitive PT+bike
                A1_cap = math.ceil(mult_A1 * L)
                A2_cap = K_PT
                kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
                kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]

            sel[(o, d)] = {"A1": kept_A1, "A2": kept_A2}

        # Add surge tracking to stats
        stats['surge_applied'] = surge_applied

        # Update final stats reporting
        if not getattr(self, "quiet", True):
            print("\nInitial selection stats:")
            print(f"  Total ODs: {stats['total_ods']}")
            print(f"  ODs with competitive PT+bike: {stats['pt_bike_competitive']}")
            print(f"  ODs with PT+bike selected: {stats['pt_bike_selected']}")
            if stats['surge_applied'] > 0:
                print(f"  Competitive PT+bike arc surge applied in {{{stats['surge_applied']}}} OD pairs")
        return sel

    def build_candidate_heap(self) -> list[tuple[float, tuple[int, int, str], str]]:
        """
        Build global min-heap of candidates (score, (o,d,a), kind).
        - PT-only (A2): score = standard PT disutility.
        - PT+Bike (A1): score = 'gap' vs the best of PT-only & Car at p = P_bar.
        (No hard domination filter; we still trial top H_A1 per OD.)
        Uses H_PT/H_A1 and ASCs/Betas from class init; prices from self.lp.
        """
        import heapq
        from concurrent.futures import ThreadPoolExecutor

        parsed = self.parsed
        H_PT, H_A1 = self.H_PT, self.H_A1

        # environment/pricing from LP
        P_bar       = self.lp.P_bar
        pt_price    = self.lp.pt_price
        dep_cost    = self.lp.dep_cost
        parking_fee = self.lp.parking_fee

        # choice params
        ASC_PT, ASC_BIKE, ASC_CAR = self.ASC_PT, self.ASC_BIKE, self.ASC_CAR

        BETA_Cost_BIKE = self.BETA_Cost_BIKE
        BETA_Time_BIKE = self.BETA_Time_BIKE
        BETA_TR_BIKE   = self.BETA_TR_BIKE

        BETA_Cost_PT   = self.BETA_Cost_PT
        BETA_Time_PT   = self.BETA_Time_PT
        BETA_TR_PT     = self.BETA_TR_PT

        BETA_Cost_Car  = self.BETA_Cost_Car
        BETA_Cost_park = self.BETA_Cost_park
        BETA_Time_Car  = self.BETA_Time_Car

        heap: list[tuple[float, tuple[int, int, str], str]] = []

        # what's already selected
        present = {(o, d, aid, "A1") for (o, d), grp in self.sel.items() for aid in grp["A1"]}
        present |= {(o, d, aid, "A2") for (o, d), grp in self.sel.items() for aid in grp["A2"]}

        def work(od_pair):
            o, d = od_pair
            od = f"{o}_{d}"
            out = []

            # best PT-only disutility
            best_PT = float("inf")
            for arc in parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                s = (ASC_PT + BETA_Cost_PT*pt_price
                    + BETA_Time_PT*parsed["pt_time_min"][(o, d, a)]
                    + BETA_TR_PT*parsed["transfer_time_min"][(o, d, a)])
                if s < best_PT:
                    best_PT = s

            # best Car disutility
            best_Car = float("inf")
            for arc in parsed["car_paths"].get(od, []):
                a = arc["arc_id"]
                F  = parsed["total_cost_car"][(o, d, a)]
                Tt = parsed["travel_time_min"][(o, d, a)]
                s  = (ASC_CAR
                    + BETA_Cost_Car*(F - dep_cost)
                    + BETA_Cost_park*parking_fee
                    + BETA_Time_Car*Tt)
                if s < best_Car:
                    best_Car = s

            benchmark = min(best_PT, best_Car)

            # PT-only pool (A2): keep top H_PT by PT score
            pool_A2 = []
            for arc in parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a, "A2") in present:
                    continue
                s = (ASC_PT + BETA_Cost_PT*pt_price
                    + BETA_Time_PT*parsed["pt_time_min"][(o, d, a)]
                    + BETA_TR_PT*parsed["transfer_time_min"][(o, d, a)])
                pool_A2.append((s, (o, d, a)))
            pool_A2.sort(key=lambda t: t[0])
            out.extend([(score, key, "A2") for score, key in pool_A2[:H_PT]])

            # PT+Bike pool (A1): 'gap' vs benchmark at p = P_bar
            pool_A1 = []
            for arc in parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a, "A1") in present:
                    continue
                s_a1 = (ASC_PT + ASC_BIKE
                        + BETA_Cost_PT*pt_price
                        + BETA_Cost_BIKE*P_bar
                        + BETA_Time_PT*parsed["pt_time_min"][(o, d, a)]
                        + BETA_Time_BIKE*parsed["bike_time_min"].get((o, d, a), 0.0)
                        + BETA_TR_BIKE*parsed["transfer_time_min"][(o, d, a)])
                gap = s_a1 - benchmark
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


    def build_candidate_heap_dual_aware_gamma(self, mu_station: float = 1.0):
        import heapq
        heap = []
        gamma = { (o,d): self.lp.gamma[(o,d)].X for (o,d) in self.parsed["OD_pairs"] }
        lambda_eff = self.lp.get_station_lambdas()  # keep your sign convention

        present = {(o,d,a,"A1") for (o,d,a) in self.lp._present_A1}
        present |= {(o,d,a,"A2") for (o,d,a) in self.lp._present_A2}

        def score_A2(o,d,a):
            base = (self.ASC_PT
                    + self.BETA_Cost_PT * self.lp.pt_price
                    + self.BETA_Time_PT * self.parsed["pt_time_min"][(o,d,a)]
                    + self.BETA_TR_PT   * self.parsed["transfer_time_min"][(o,d,a)])
            return base - gamma[(o,d)]

        def score_A1(o,d,a):
            base = (self.ASC_PT + self.ASC_BIKE
                    + self.BETA_Cost_PT   * self.lp.pt_price
                    + self.BETA_Cost_BIKE * self.lp.P_bar     # use P_bar for ranking
                    + self.BETA_Time_PT   * self.parsed["pt_time_min"][(o,d,a)]
                    + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o,d,a), 0.0)
                    + self.BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o,d,a)])
            pen = sum(lambda_eff.get(i,0.0) * delta for i, delta in self.lp.delta_ia.get(a, {}).items() if delta)
            return (base + mu_station * pen) - gamma[(o,d)]

        for (o,d) in self.parsed["OD_pairs"]:
            od = f"{o}_{d}"
            # A2
            pool = [(score_A2(o,d,arc["arc_id"]), (o,d,arc["arc_id"])) 
                    for arc in self.parsed["arcs_pt_only"].get(od, []) 
                    if (o,d,arc["arc_id"],"A2") not in present]
            pool.sort(key=lambda t: t[0])
            for g,key in pool[:self.H_PT]:
                heapq.heappush(heap, (g, key, "A2"))
            # A1
            pool = [(score_A1(o,d,arc["arc_id"]), (o,d,arc["arc_id"])) 
                    for arc in self.parsed["arcs_pt_bike"].get(od, []) 
                    if (o,d,arc["arc_id"],"A1") not in present]
            pool.sort(key=lambda t: t[0])
            for g,key in pool[:self.H_A1]:
                heapq.heappush(heap, (g, key, "A1"))

        return heap


    def build_candidate_heap_dual_aware(self, mu_station: float = 1.0):
        import heapq
        from concurrent.futures import ThreadPoolExecutor

        # must be called AFTER a solve so Pis exist
        lambda_eff = self.lp.get_station_lambdas()

        parsed = self.parsed
        H_PT, H_A1 = self.H_PT, self.H_A1
        P_bar, pt_price = self.lp.P_bar, self.lp.pt_price
        dep_cost, parking_fee = self.lp.dep_cost, self.lp.parking_fee

        # short-hands
        ASC_PT, ASC_BIKE, ASC_CAR = self.ASC_PT, self.ASC_BIKE, self.ASC_CAR
        BcB, BtB, BrB = self.BETA_Cost_BIKE, self.BETA_Time_BIKE, self.BETA_TR_BIKE
        BcP, BtP, BrP = self.BETA_Cost_PT,   self.BETA_Time_PT,   self.BETA_TR_PT
        BcC, BpC, BtC = self.BETA_Cost_Car,  self.BETA_Cost_park, self.BETA_Time_Car

        heap: list[tuple[float, tuple[int,int,str], str]] = []

        # exclude anything already in the live LP (authoritative)
        present = {(o, d, a, "A1") for (o, d, a) in self.lp._present_A1}
        present |= {(o, d, a, "A2") for (o, d, a) in self.lp._present_A2}

        def work(od_pair):
            o, d = od_pair
            od = f"{o}_{d}"
            out = []

            # ---- best PT-only disutility
            best_PT = float("inf")
            for arc in parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                s = (ASC_PT + BcP*pt_price
                    + BtP*parsed["pt_time_min"][(o, d, a)]
                    + BrP*parsed["transfer_time_min"][(o, d, a)])
                if s < best_PT:
                    best_PT = s

            # ---- best Car disutility
            best_Car = float("inf")
            for arc in parsed["car_paths"].get(od, []):
                a = arc["arc_id"]
                F  = parsed["total_cost_car"][(o, d, a)]
                Tt = parsed["travel_time_min"][(o, d, a)]
                s  = (ASC_CAR + BcC*(F - dep_cost) + BpC*parking_fee + BtC*Tt)
                if s < best_Car:
                    best_Car = s

            benchmark = min(best_PT, best_Car)
            if benchmark == float("inf"):
                # no sensible benchmark; skip this OD entirely
                return out

            # ---- PT-only pool (A2): keep top H_PT
            pool_A2 = []
            for arc in parsed["arcs_pt_only"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a, "A2") in present:
                    continue
                s = (ASC_PT + BcP*pt_price
                    + BtP*parsed["pt_time_min"][(o, d, a)]
                    + BrP*parsed["transfer_time_min"][(o, d, a)])
                pool_A2.append((s, (o, d, a)))
            pool_A2.sort(key=lambda t: t[0])
            out.extend([(score, key, "A2") for score, key in pool_A2[:H_PT]])

            # ---- PT+Bike pool (A1): base utility + dual-aware station penalty
            pool_A1 = []
            for arc in parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                if (o, d, a, "A1") in present:
                    continue

                base = (ASC_PT + ASC_BIKE
                        + BcP*pt_price
                        + BcB*P_bar
                        + BtP*parsed["pt_time_min"][(o, d, a)]
                        + BtB*parsed["bike_time_min"].get((o, d, a), 0.0)
                        + BrB*parsed["transfer_time_min"][(o, d, a)])

                # dual-aware station penalty
                pen = 0.0
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        pen += lambda_eff.get(i_str, 0.0) * delta

                s_a1 = base + mu_station * pen
                gap = s_a1 - benchmark
                pool_A1.append((gap, s_a1, (o, d, a)))

            pool_A1.sort(key=lambda t: (t[0], t[1]))
            out.extend([(gap, key, "A1") for gap, _s, key in pool_A1[:H_A1]])
            return out

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            for items in ex.map(work, parsed["OD_pairs"]):
                for tup in items:
                    heapq.heappush(heap, tup)

        return heap



    #---build initial model---

    def _build_initial(self):
        for (o,d), grp in self.sel.items():
            for aid in grp["A2"]:
                self.lp.add_pt_only(o,d,aid)
            for aid in grp["A1"]:
                self.lp.add_pt_bike(o,d,aid)

    #---forward phase---

    def run_forward(self,max_add: int = 1000, refresh_every = 10, mu_station = 0.5):
        
        # Build the initial restricted model
        self._build_initial()

        # --- BASE SOLVE: let Gurobi choose (concurrent) and no timelimit ---
        # Save current settings to restore later
        old_method = self.lp.m.Params.Method
        old_timelimit = getattr(self.lp.m.Params, "TimeLimit", 0)  # 0 means no limit

        try:
            # Free method choice (concurrent) for the big initial solve
            self.lp.m.Params.Method = -1      # concurrent/free
            #self.lp.m.Params.TimeLimit = 0    # no limit for base solve
            base = self.lp.optimize()
        finally:
            # For all subsequent incremental re-optimizations, use Dual Simplex
            self.lp.m.Params.Method = 1       # Dual Simplex reopt is fastest for small changes
            # Keep no TimeLimit for reopt (0) unless you want one; restore otherwise
            #self.lp.m.Params.TimeLimit = 0 if old_timelimit == 0 else old_timelimit
        t_iheap_start = time.perf_counter()
        #self.heap = self.build_candidate_heap_dual_aware(mu_station)
        self.heap = self.build_candidate_heap_dual_aware_gamma(mu_station)
        t_iheap_end = time.perf_counter()
        t_iheap = t_iheap_end - t_iheap_start
        print(f"initial heap built in {t_iheap:.3f}s")

        if base is None:
            print("[forward] base failed to produce a feasible solution.")
            self.forward_trials_attemted = 0
            self.forward_adds_accepted = 0
            self.forward.avg_trial_sec = None
            return None

        print(f"[forward] base objective = {base}")
        self.lp.debug_after_opt("forward_base")
        self.lp.debug_check_strong_duality()

        added = 0
        trials = 0
        non_improve_streak = 0
        since_refresh = 0
        total_trial_time = 0
        trials_attempted = 0
        while self.heap and added < max_add:
            if trials >= self.max_trial_add or non_improve_streak >= self.patience_add:
                break

            _, (o,d,a), kind = heapq.heappop(self.heap)
            t0 = time.perf_counter()
            trial = self._trial_add_value(o,d,a,kind)
            t1=time.perf_counter()
            total_trial_time += (t1 - t0)
            trials_attempted += 1
            trials += 1
            print(f"[forward] trial {trials}: add {kind} arc {a} to OD {o}->{d} ... ", end="")
            print(f"trial time = {total_trial_time}")
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
                since_refresh+=1
                self.lp.debug_after_opt(f"forward_add_{added}")
                if since_refresh >= refresh_every:
                    t_rheap_start = time.perf_counter()
                    self.heap = self.build_candidate_heap_dual_aware(mu_station)
                    since_refresh = 0
                    t_rheap_end= time.perf_counter()
                    t_rheap = t_rheap_end - t_rheap_start
                    print(f"heap refreshed in {t_rheap:.3f}s")
            else:
                non_improve_streak += 1
        #finalize metrics
        avg_trial_sec = (total_trial_time/trials_attempted) if trials_attempted > 0 else None
        self.forwards_trials_attempted = trials_attempted
        self.forward_adds_accepted = added
        self.forward_avg_trial_sec = avg_trial_sec

        #print summary
        print(f"[forward] trials={trials_attempted}, accepted={added}, "
              f"avg_trial_time={avg_trial_sec:.4f}s" if avg_trial_sec is not None else
              f"[forward] trials={trials_attempted}, accepted={added}, avg_trial_time=N/A")
        
        return base

    
    def _trial_add_value(self, o, d, a, kind) -> Optional[float]:
        """Evaluate objective of adding a candidate using a model COPY (cheap, safe)."""
        try:
            mcopy = self.lp.m.copy()
            #mcopy.Params.OutputFlag = 1
            mcopy.Params.Method = 1  # Dual Simplex

            # ASCs/Betas from class init
            ASC_PT, ASC_BIKE = self.ASC_PT, self.ASC_BIKE
            BETA_Cost_PT   = self.BETA_Cost_PT
            BETA_Time_PT   = self.BETA_Time_PT
            BETA_TR_PT     = self.BETA_TR_PT
            BETA_Cost_BIKE = self.BETA_Cost_BIKE
            BETA_Time_BIKE = self.BETA_Time_BIKE
            BETA_TR_BIKE   = self.BETA_TR_BIKE

            Qod = self.lp.demands[(o, d)]
            gamma_c = mcopy.getVarByName(f"gamma_{o}_{d}")
            sd_c = mcopy.getConstrByName("StrongDuality")
            dem_c = mcopy.getConstrByName(f"demand_{o}_{d}")

            if kind == "A2":
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")

                # dual feasibility KKT for PT-only
                rhs = (ASC_PT
                    + BETA_Cost_PT * self.lp.pt_price
                    + BETA_Time_PT * self.parsed["pt_time_min"][(o, d, a)]
                    + BETA_TR_PT   * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaPT_{o}_{d}_{a}")

                # demand
                mcopy.chgCoeff(dem_c, q, +1)

                # Strong Duality for PT-only
                coeff_q = rhs  # identical expression
                mcopy.chgCoeff(sd_c, q, coeff_q)

                q.Obj = 0.0

            else:  # PT+bike constraints
                p = mcopy.addVar(lb=self.lp.P_bar, ub=self.lp.P_up, vtype=GRB.CONTINUOUS, name=f"trial_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0, ub=Qod, vtype=GRB.CONTINUOUS, name=f"trial_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-GRB.INFINITY, ub=GRB.INFINITY, vtype=GRB.CONTINUOUS, name=f"trial_z_{o}_{d}_{a}")

                # McCormick
                mcopy.addConstr(z >= self.lp.P_bar*q,                              name=f"trial_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= self.lp.P_up*q,                               name=f"trial_z_max1_{o}_{d}_{a}")
                mcopy.addConstr(z >= self.lp.P_up*q + p*Qod - self.lp.P_up*Qod,    name=f"trial_z_min2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod,  name=f"trial_z_max2_{o}_{d}_{a}")

                # dual feasibility for PT+bike
                rhs = (ASC_BIKE + ASC_PT
                    + BETA_Cost_PT   * self.lp.pt_price
                    + BETA_Cost_BIKE * p
                    + BETA_Time_PT   * self.parsed["pt_time_min"][(o, d, a)]
                    + BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                    + BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o, d, a)])
                mcopy.addConstr(gamma_c <= rhs, name=f"trial_gammaA_{o}_{d}_{a}")

                # demand
                mcopy.chgCoeff(dem_c, q, +1)

                # capacity
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        print(delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),        q, delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)

                # Strong Duality terms
                coeff_q = (BETA_Cost_PT * self.lp.pt_price
                        + BETA_Time_PT * self.parsed["pt_time_min"][(o, d, a)]
                        + BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                        + BETA_TR_BIKE * self.parsed["transfer_time_min"][(o, d, a)]
                        + (ASC_BIKE + ASC_PT))
                mcopy.chgCoeff(sd_c, q, coeff_q)
                mcopy.chgCoeff(sd_c, z, BETA_Cost_BIKE)

                # objective
                ridership = 2.0 * self.lp.P_up                   # if you keep this proxy; see §3.4
                resource  = self.lp._resource_coeff.get((o,d,a), 0.0)
                q.Obj += (ridership - self.lp.cost_bike + self.lp.theta * resource)
                z.Obj += 1.0


            mcopy.optimize()
            return float(mcopy.ObjVal) if mcopy.SolCount > 0 else None

        except Exception:
            return None


    # --- backward phase (prune)

    def prune(self, max_drops: int = 200, *, enforce_total_cap: bool = False):
        """Backward elimination of weak A1 arcs."""
        base = self.lp.objective_value()
        if base is None:
            return None

        #Rank A1 by small q then contribution


        m = self.lp.m

        if m.SolCount == 0:
            return base
        
        #Build cap counters per od
        
        count_A1 = defaultdict(int)
        count_A2 = defaultdict(int)

        for (o,d,a) in self.lp._present_A1:
            count_A1[(o,d)] += 1
        for (o,d,a) in self.lp._present_A2:
            count_A2[(o,d)] += 1
        
        #caps for arcs
        cap_A1 = max(self.L, self.mult_A1*self.L)
        total_cap = self.L
        
        cand = []

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

            # Per OD cap
            if enforce_total_cap:
                #keep atleast total_cap arcs (A1+A2) for each OD
                if (count_A1[(o,d)] + count_A2[(o,d)] <= total_cap):
                    continue
            else:
                #keep at least cap_A1 A1 arcs per OD
                if count_A1[(o,d)] <= cap_A1:
                    continue

            #trial, trial_lp = self._trial_drop_value_fresh_solve(o,d,a)
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
                '''
                self.lp = trial_lp
                base    = trial
                drops  += 1
                non_improve_streak = 0

                # Rebuild OD counts from the accepted model (simple & safe)
                count_A1.clear(); count_A2.clear()
                for (oo, dd, aa) in self.lp._present_A1: count_A1[(oo, dd)] += 1
                for (oo, dd, aa) in self.lp._present_A2: count_A2[(oo, dd)] += 1
                '''
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
    
    def _trial_drop_value_fresh_solve(self, o: int, d: int, a: str) -> Optional[float]:
        """
        Rebuild a fresh IncrementalBilevelLP mirroring the current *live* selection
        but with (o,d,a) removed from A1. Return the objective on success; else None.
        """
        try:
            trial_lp = IncrementalBilevelLP(
                self.parsed,
                P_bar=self.lp.P_bar, P_up=self.lp.P_up, theta=getattr(self.lp, "theta", None),
                pt_price=self.lp.pt_price, cost_bike=self.lp.cost_bike,
                parking_fee=self.lp.parking_fee, dep_cost=self.lp.dep_cost,
                tolerance=self.lp.tolerance, quiet=True,
                time_limit=self.trial_time_limit
            )

            # Recreate the current live selection except the candidate to drop
            for (o2, d2, a2) in self.lp._present_A2:
                trial_lp.add_pt_only(o2, d2, a2)

            for (o2, d2, a2) in self.lp._present_A1:
                if not (o2 == o and d2 == d and a2 == a):
                    trial_lp.add_pt_bike(o2, d2, a2)

            obj = trial_lp.optimize()
            if obj is None:
                return None, None
            return float(obj), trial_lp
        except Exception:
            return None, None



    # --- run both phases and write JSON ---

    def run(self, max_add: int = 1000, max_drops: int = 200):
        t0=time.time()

        if getattr(self, "search_method", "first_improvement") == "lns":
            best_final = self.run_lns()
        else:
                
            best_forward = self.run_forward(max_add=max_add)
            #best_forward = self.run_forward_with_fresh_trials(max_add=50)
            #best_final = self.prune(max_drops=max_drops)
            #best_final = self.prune_with_cap(enforce_A2_cap=False,enforce_A1_cap=True) # total_cap=self.L,  # <- set this if you want a single total cap per OD
            
        t1=time.time()
        return best_forward, (t1-t0)
    

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

        f_trials = getattr(self, "forwards_trials_attempted", None )
        f_adds  = getattr(self, "forward_adds_accepted", None )
        f_avgsec   = getattr(self, "forward_avg_trial_sec", None )
        # Also include which search path we used and caps for reproducibility
        forward_metrics = {
            "Search Method": getattr(self, "search_method", "first_improvement"),
            "Trials Attempted": f_trials,
            "Adds Accepted": f_adds,
            "Avg Trial Time (s)": f_avgsec,
            "Max Add (arg)": getattr(self, "max_trial_add", None),  # your class knob (optional)
            "Patience Add": getattr(self, "patience_add", None),     # optional
            "Rel Improve Tol (add)": getattr(self, "rel_impr_tol_add", None),
        }

        sol_obj = {
            "Solution Time (s)": None,  # fill by caller
            "Objective Value":  self.lp.objective_value(),
            "Gap (%)":          gap_pct,
            "forward_metrics": forward_metrics,
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



    # Pruneing with Cap

    # --- inside class GreedyFixAndOptimize -------------------------------------

    def _present_by_od(self, kind: str) -> dict[tuple[int,int], list[tuple[int,int,str]]]:
        """Group present A1/A2 arcs by OD."""
        if kind == "A1":
            pool = list(self.lp._present_A1)
        elif kind == "A2":
            pool = list(self.lp._present_A2)
        else:
            return {}
        by_od = {}
        for (o,d,a) in pool:
            by_od.setdefault((o,d), []).append((o,d,a))
        return by_od

    def _rank_A1_weak_by_od(self, items):
        m = self.lp.m
        has_sol = getattr(m, "SolCount", 0) > 0
        out = []
        for (o,d,a) in items:
            qv = self.lp.q[(o,d,a)].X if has_sol and (o,d,a) in self.lp.q else 0.0
            zv = self.lp.z[(o,d,a)].X if has_sol and (o,d,a) in self.lp.z else 0.0
            q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o,d,a), 0.0)
            contrib = zv + q_coeff*qv
            out.append((qv, contrib, (o,d,a)))
        out.sort(key=lambda t: (t[0], t[1]))
        return out

    def _rank_A2_weak_by_od(self, items):
        m = self.lp.m
        has_sol = getattr(m, "SolCount", 0) > 0
        out = []
        for (o,d,a) in items:
            qv = self.lp.q[(o,d,a)].X if has_sol and (o,d,a) in self.lp.q else 0.0
            out.append((qv, (o,d,a)))
        out.sort(key=lambda t: t[0])
        return out


    def _soft_deactivate_A2_live(self, o: int, d: int, a: str) -> None:
        """
        Soft-deactivate PT-only arc (o,d,a) in the live model:
        - q_{od,a} fixed to 0
        - relax gammaPT row with big-M RHS
        - zero SD coefficient of q
        - remove q from demand row
        - update presence set
        """
        m = self.lp.m
        q = m.getVarByName(f"q_{o}_{d}_{a}")
        if q is None:
            return

        # fix q to 0
        q.LB = 0.0; q.UB = 0.0

        # relax its dual feasibility row
        crow = m.getConstrByName(f"gammaPT_{o}_{d}_{a}")
        if crow is not None:
            try:
                crow.RHS = 1e9
            except Exception:
                pass

        # zero SD coefficient
        sd_c = m.getConstrByName("StrongDuality")
        if sd_c is not None:
            try:
                m.chgCoeff(sd_c, q, 0.0)
            except Exception:
                pass

        # remove from demand balance
        dem_c = m.getConstrByName(f"demand_{o}_{d}")
        if dem_c is not None:
            try:
                m.chgCoeff(dem_c, q, 0.0)
            except Exception:
                pass

        # book-keeping
        if (o,d,a) in self.lp._present_A2:
            self.lp._present_A2.remove((o,d,a))

    def _trial_fix_to_zero_on_copy(self, drop_A1: set[tuple[int,int,str]], drop_A2: set[tuple[int,int,str]]):
        """
        Copy the live model, fix q/p/z of listed arcs to zero and relax their dual rows,
        then optimize with Dual Simplex. Returns (is_feasible, obj_val_or_None).
        """
        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.OutputFlag = 1
            mcopy.Params.Method = 1  # Dual Simplex

            def _fix_block_zero(o, d, a, kind: str):
                q = mcopy.getVarByName(f"q_{o}_{d}_{a}")
                p = mcopy.getVarByName(f"p_{o}_{d}_{a}") if kind == "A1" else None
                z = mcopy.getVarByName(f"z_{o}_{d}_{a}") if kind == "A1" else None
                if q is not None:
                    q.LB = 0.0; q.UB = 0.0
                if p is not None:
                    p.LB = 0.0; p.UB = 0.0
                if z is not None:
                    z.LB = 0.0; z.UB = 0.0
                # relax gamma row so it cannot bind on a removed alt
                crow = mcopy.getConstrByName(f"gammaA_{o}_{d}_{a}") if kind == "A1" else mcopy.getConstrByName(f"gammaPT_{o}_{d}_{a}")
                if crow is not None:
                    try:
                        crow.RHS = 1e9
                    except:
                        pass

            for (o,d,a) in drop_A1:
                _fix_block_zero(o,d,a,"A1")
            for (o,d,a) in drop_A2:
                _fix_block_zero(o,d,a,"A2")

            mcopy.optimize()
            status = mcopy.Status
            feasible = (status in (GRB.OPTIMAL, GRB.SUBOPTIMAL)) and (mcopy.SolCount and mcopy.SolCount > 0)
            return feasible, (float(mcopy.ObjVal) if feasible else None)
        except Exception:
            return False, None



    def prune_with_cap(self, *, enforce_A2_cap=True, enforce_A1_cap=True, total_cap=None):
        """
        Enforce per-OD soft caps by attempting weakest-first drops, but
        trial each drop on a model copy. If the trial is infeasible, skip that arc.
        Commit accepted drops to the live model and reopt after each commit.
        """
        # Ensure we have a valid incumbent to rank by
        if getattr(self.lp.m, "SolCount", 0) == 0:
            self.lp.m.Params.Method = 1
            base = self.lp.optimize()
            if base is None or getattr(self.lp.m, "SolCount", 0) == 0:
                return None
        base = self.lp.objective_value()

        # Build per-OD lists of present arcs
        from collections import defaultdict
        A1_by_od = defaultdict(list)
        A2_by_od = defaultdict(list)
        for (o,d,a) in list(self.lp._present_A1):
            A1_by_od[(o,d)].append((o,d,a))
        for (o,d,a) in list(getattr(self.lp, "_present_A2", [])):
            A2_by_od[(o,d)].append((o,d,a))

        # Helper rankers that don’t crash if no solution
        def rank_A1(items):
            m = self.lp.m; has_sol = getattr(m, "SolCount", 0) > 0
            rows = []
            for (o,d,a) in items:
                qv = self.lp.q[(o,d,a)].X if has_sol and (o,d,a) in self.lp.q else 0.0
                zv = self.lp.z[(o,d,a)].X if has_sol and (o,d,a) in self.lp.z else 0.0
                q_coeff = 2*self.lp.P_up - self.lp.cost_bike + self.lp._resource_coeff.get((o,d,a),0.0)
                contrib = zv + q_coeff*qv
                rows.append((qv, contrib, (o,d,a)))
            rows.sort(key=lambda t: (t[0], t[1]))  # smallest flow, then smallest contrib
            return rows

        def rank_A2(items):
            m = self.lp.m; has_sol = getattr(m, "SolCount", 0) > 0
            rows = []
            for (o,d,a) in items:
                qv = self.lp.q[(o,d,a)].X if has_sol and (o,d,a) in self.lp.q else 0.0
                rows.append((qv, (o,d,a)))
            rows.sort(key=lambda t: t[0])
            return rows

        # Iterate ODs independently; try to meet caps with feasibility checks
        for (o,d) in self.parsed["OD_pairs"]:
            A1_list = A1_by_od.get((o,d), [])
            A2_list = A2_by_od.get((o,d), [])
            n1, n2 = len(A1_list), len(A2_list)

            cap_A1 = max(self.L, self.mult_A1*self.L) if enforce_A1_cap else n1
            cap_A2 = self.K_PT if enforce_A2_cap else n2
            cap_T  = total_cap if (total_cap is not None) else (n1+n2)

            # First, per-type caps (A1 then A2), with feasibility filter
            if enforce_A1_cap and n1 > cap_A1:
                needed = n1 - cap_A1
                ranked = rank_A1(A1_list)
                protected = set()
                for _, _, key in ranked:
                    if needed <= 0: break
                    drop_A1 = {key}
                    ok, trial_obj = self._trial_fix_to_zero_on_copy(drop_A1, set())
                    if ok:
                        # commit to live model
                        od, _, a = key[1], key[2], key[2]  # (o,d,a)
                        self.lp.deactivate_pt_bike(*key)
                        base = self.lp.optimize()
                        needed -= 1
                    else:
                        protected.add(key)

            if enforce_A2_cap and n2 > cap_A2:
                needed = n2 - cap_A2
                ranked = rank_A2(A2_list)
                protected = set()
                for _, key in ranked:
                    if needed <= 0: break
                    drop_A2 = {key}
                    ok, trial_obj = self._trial_fix_to_zero_on_copy(set(), drop_A2)
                    if ok:
                        # commit (requires a deactivation for PT-only)
                        if hasattr(self, "deactivate_pt_only"):
                            self.deactivate_pt_only(*key)
                        else:
                            # soft deactivate inline
                            q = self.lp.q.get(key); 
                            if q is not None: q.LB = 0.0; q.UB = 0.0
                            crow = self.lp.m.getConstrByName(f"gammaPT_{key[0]}_{key[1]}_{key[2]}")
                            if crow is not None:
                                try: crow.RHS = 1e9
                                except: pass
                            if hasattr(self.lp, "_present_A2") and key in self.lp._present_A2:
                                self.lp._present_A2.remove(key)
                        base = self.lp.optimize()
                        needed -= 1
                    else:
                        protected.add(key)

            # Optional: total cap across A1+A2
            if total_cap is not None:
                # Re-read counts
                A1_list = [t for t in self.lp._present_A1 if (t[0],t[1])==(o,d)]
                A2_list = [t for t in getattr(self.lp, "_present_A2", []) if (t[0],t[1])==(o,d)]
                nt = len(A1_list) + len(A2_list)
                if nt > total_cap:
                    need = nt - total_cap
                    # Build a unified weakness list: A1 then A2
                    pool = []
                    for (qv, contrib, key) in rank_A1(A1_list):
                        pool.append(("A1", qv, contrib, key))
                    for (qv, key) in rank_A2(A2_list):
                        pool.append(("A2", qv, 0.0, key))
                    pool.sort(key=lambda r: (r[1], r[2]))  # same order
                    for kind, _, _, key in pool:
                        if need <= 0: break
                        drop_A1 = {key} if kind=="A1" else set()
                        drop_A2 = {key} if kind=="A2" else set()
                        ok, _ = self._trial_fix_to_zero_on_copy(drop_A1, drop_A2)
                        if ok:
                            if kind=="A1":
                                self.lp.deactivate_pt_bike(*key)
                            else:
                                if hasattr(self, "deactivate_pt_only"):
                                    self.deactivate_pt_only(*key)
                                else:
                                    q = self.lp.q.get(key); 
                                    if q is not None: q.LB = 0.0; q.UB = 0.0
                                    crow = self.lp.m.getConstrByName(f"gammaPT_{key[0]}_{key[1]}_{key[2]}")
                                    if crow is not None:
                                        try: crow.RHS = 1e9
                                        except: pass
                                    if hasattr(self.lp, "_present_A2") and key in self.lp._present_A2:
                                        self.lp._present_A2.remove(key)
                            base = self.lp.optimize()
                            need -= 1
                        # else infeasible: skip and try next

        # Return final objective after cap enforcement
        return self.lp.objective_value()


            

