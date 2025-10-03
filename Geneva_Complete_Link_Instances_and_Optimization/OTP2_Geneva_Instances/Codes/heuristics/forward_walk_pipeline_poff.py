# greedy_pipeline.py
import json
import time
from typing import Dict, List, Tuple, Optional
import time
import gurobipy as gp
from gurobipy import GRB
from incremental_lp_poff import IncrementalBilevelLP
import math
import os


# -------- Pipeline driver --------
class DualAwareForwardSelection:
    """
    Greedy add–drop matheuristic:
      - Make an initial selection of arcs per OD based on disutility. A1 arcs are selected based on competitiveness with car and PT. PT arcs selected based on their disutility. 
      - We select K_PT PT-only arcs and up to mult_A1*L PT+bike arcs per OD.
      - Build restricted LP with initial selection and solve LP.
      - Build a batch of candidates (PT+bike) scored by utility and station duals reduced cost per OD.
      - Forward add: try best-scored candidates; accept only if they improve objective, flow or reduce car flow
      - Extract results and write JSON in your original format
    """

    def __init__(self,
                parsed_data, *,
                L: int, K_PT: int = 2, mult_A1: int = 4,theta =0.5,
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
                lns_rand_frac: float = 0.25,
                p_off_map: dict | None = None,
                global_p_off: float | None = None,
                disable_arcs: set[tuple[int,int,str]] | None = None,):
        
        self.parsed = parsed_data
        self.L = L
        self.K_PT = K_PT
        self.mult_A1 = mult_A1
        self.theta = theta
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

        self.cost_bike = cost_bike
        self.parking_fee = parking_fee
        self.dep_cost = dep_cost
        

        self.lp = IncrementalBilevelLP(parsed_data,
                                       P_bar=P_bar, P_up=P_up, pt_price=pt_price, theta = theta,
                                       cost_bike=cost_bike, parking_fee=parking_fee, dep_cost=dep_cost,
                                       tolerance=tolerance, quiet=quiet,
                                       nodefile_dir=nodefile_dir, threads=threads,
                                       time_limit=time_limit_eval,
                                       p_off_map=p_off_map,
                                       global_p_off=global_p_off,
                                       disable_arcs=disable_arcs)
        
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

        self.sel = self.make_initial_selection_enhanced_2()
        t1 = time.perf_counter()
        self._t_init_select = t1 - t0

        print(F"[init] selection = {self._t_init_select:.3f}s ")


    # Dual Aware Batch Addition
    
    # 0. helpers: A1 candidate list, station budgets, and batch trial ===

    ## 0.1 Get remaining capacity from stations

    def _station_budgets(self):
        """
        Return (U, L) where:
        U[i] = slack of cap row  (how much more +δ we can add at station i),
        L[i] = slack of nonneg row (how much more -δ we can add at station i).
        """
        U, L = {}, {}
        for i in self.lp.stations_list:
            i_str = str(i)
            U[i_str] = float(self.lp.cap_constr[i_str].Slack)          # ≥ 0
            L[i_str] = float(self.lp.cap_nonneg[i_str].Slack)           # ≥ 0
        return U, L

    ## 0.2 Check remaining flow budget for arcs

    def _qhat_max_for_arc(self, o, d, a, U, L):
        """
        Conservative per-arc flow proxy:
        Returns maximum flow an arc can have for OD after initial sovle
        min( Q_od, min_{δ>0} U_i, min_{δ<0} L_i ).
        """
        Qod = float(self.lp.demands[(o, d)])
        up = [U[i] for i, delta in self.lp.delta_ia.get(a, {}).items() if delta > 0]
        lo = [L[i] for i, delta in self.lp.delta_ia.get(a, {}).items() if delta < 0]
        cap_pos = min(up) if up else Qod
        cap_neg = min(lo) if lo else Qod
        return max(0.0, min(Qod, cap_pos, cap_neg))


    ## 0.3 Accept new arcs Rule. 

    def accept_neutral_or_better(self, trial_obj, base_obj, net_flow_change, net_car_flow_change,
                                rel=1e-4, abs_eps=1e-6):
        """
        Accept a trial if:
        1. It strictly improves objective by rel tolerance, OR
        2. Objective ties (within tolerance) AND one of:
        a) There is strictly positive A1 flow (net_flow_change >= min_modal_shift)
        b) There is modal shift from car to bike (net_car_flow_change < -min_modal_shift)
        
        Parameters:
        - net_flow_change: change in A1 (bike) arc flows (positive = more bikes)
        - net_car_flow_change: change in car arc flows (negative = fewer cars)
        - min_modal_shift: minimum flow change to consider significant (default 1.0)
        """
        if trial_obj is None:
            return False
        tol = max(abs_eps, rel * max(1.0, abs(base_obj)))
        if trial_obj >= base_obj + tol:
            return True
        
        # neutral acceptance
        if (abs(trial_obj - base_obj) <= tol):
           
            #accept if bike flow increased:
            
            has_bike_flow = (net_flow_change is not None) and (net_flow_change >= 1)
            
            # Accept if car usage decreased (modal shift to sustainable transport)
            
            has_modal_shift = (net_car_flow_change is not None) and (net_car_flow_change <= -1)
        
            return has_bike_flow or has_modal_shift
        return False

    ## 0.4 helpers to check number of arcs per-OD  

    def _present_A1_count_by_od(self) -> dict[tuple[int,int], int]:
        """Count present A1 per OD from the live LP."""
        cnt = {(o,d): 0 for (o,d) in self.parsed["OD_pairs"]}
        for (o,d,a) in self.lp._present_A1:
            cnt[(o,d)] = cnt.get((o,d), 0) + 1
        return cnt
    def _present_A2_count_by_od(self) -> dict[tuple[int,int], int]:
        cnt = {(o,d): 0 for (o,d) in self.parsed["OD_pairs"]}
        for (o,d,a) in self.lp._present_A2:
            cnt[(o,d)] = cnt.get((o,d), 0) + 1
        return cnt

    ## 0.5 Find remaining slots per OD for arc addition
        
    def _remaining_A1_cap_by_od(self, cap_L: int | None = None) -> dict[tuple[int,int], int]:
        """Remaining A1 slots per OD given current live model and global cap L."""
        if cap_L is None:
            cap_L = self.L
        present_A1 = self._present_A1_count_by_od()
        present_A2 = self._present_A2_count_by_od()

        rem = {}
        for (o,d) in self.parsed["OD_pairs"]:
            total_cap = self.L_total_cap_od.get((o,d), self.L_base)
            a1_eff    = self.A1_eff_cap_od.get((o,d), self.L_base)
            # A1 cannot exceed remaining total after A2, nor exceed its effective A1 cap
            a1_max_now = min(a1_eff, total_cap - present_A2.get((o,d),0))
            rem[(o,d)] = max(0, int(a1_max_now) - int(present_A1.get((o,d),0)))
        return rem


    ## 0.6 Sort list of A1 candidates, dual aware

    def _list_A1_candidates_dual_aware(self, mu_station: float = 0.5, screen_price: bool = True):
        '''
        Returns sorted [(gap, (o,d,a))], lower gap is better, closer to gamma
        If screen_price = True, discard A1 arcs that cannot bind at any feasible price compared to car
        '''
        gamma = { (o,d): float(self.lp.gamma[(o,d)].X) for (o,d) in self.parsed["OD_pairs"]}
        lambda_eff = self.lp.get_station_lambdas()
        present = {(o,d,a) for (o,d,a) in self.lp._present_A1}
        out = []

        # Local views to cut dict lookups in loops
        pt_time     = self.parsed["pt_time_min"]
        bike_time   = self.parsed["bike_time_min"]
        transfers   = self.parsed["transfer_time_min"]
        k_legs      = self.parsed["k_bike_legs"]
        Pbar        = float(self.lp.P_bar)
        pt_price    = float(self.lp.pt_price)

        for (o,d) in self.parsed["OD_pairs"]:
            g = gamma[(o,d)]
            od = f"{o}_{d}"
            for arc in self.parsed["arcs_pt_bike"].get(od,[]):
                a = arc["arc_id"]
                if (o,d,a) in present:
                    continue
                if screen_price and (not self._is_gamma_compatible(o,d,a)):
                    continue
                k = k_legs.get((o, d, a), 1)
                base = ( self.ASC_PT + self.ASC_BIKE
                    + self.BETA_Cost_PT   * pt_price
                    + self.BETA_Cost_BIKE * k * Pbar     # price proxy at P_bar
                    + self.BETA_Time_PT   * pt_time[(o, d, a)]
                    + self.BETA_Time_BIKE * bike_time.get((o, d, a), 0.0)
                    + self.BETA_TR_BIKE   * transfers[(o, d, a)] )

                pen = 0.0
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        pen += lambda_eff.get(i_str, 0.0) * delta

                gap = (base + mu_station * pen) - g
                out.append((gap, (o, d, a)))

        out.sort(key=lambda t: t[0])
        return out
    
    ## 0.7 Write to Json
    def write_json(self, json_file_path: str, save_folder: str, P_bar: float,
               capacity, inventory_level, q_tol: float = 0):


        os.makedirs(save_folder, exist_ok=True)
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

        # Pull forward telemetry (may be None if no forward run)
        forward_metrics = {
            "Method": getattr(self, "forward_method_name", None),
            "Trials Attempted": getattr(self, "forward_trials_attempted", None),
            "Batches Accepted": getattr(self, "forward_batches_accepted", None),

            "Avg Trial Time (s, accepted)": getattr(self, "forward_avg_trial_sec", None),
            "Avg Reopt Time (s, accepted)": getattr(self, "forward_avg_reopt_sec", None),

            "Total Batch Build Time (s)": getattr(self, "forward_total_build_sec", None),
            "Total Trial Time (s)": getattr(self, "forward_total_trial_sec", None),  # overall (all attempts)
            "Total Trial Time (s, accepted)": getattr(self, "forward_total_trial_sec_accepted", None),  # optional
            "Total Reopt Time (s)": getattr(self, "forward_total_reopt_sec", None),
            "Overall Forward Time (s)": getattr(self, "forward_overall_forward_sec", None),  # build+trial+reopt

            # knobs for reproducibility
            "L": getattr(self, "L", None),
            "K_PT": getattr(self, "K_PT", None),
            "mult_A1": getattr(self, "mult_A1", None),
            "theta": getattr(self, "theta", None),
            "Batch M (last run)": getattr(self, "forward_last_M", None),
            "mu_station (last run)": getattr(self, "forward_last_mu_station", None),
        }


        # Accepted batches (optional but useful)
        accepted_batches = getattr(self, "forward_accepted_batches", None)

        sol_obj = {
            "Solution Time (s)": None,  # fill by caller if you time end-to-end
            "Objective Value":  self.lp.objective_value(),
            "Gap (%)":          gap_pct,
            "forward_metrics":  forward_metrics,
            "accepted_batches": accepted_batches,   # may be None
            "instances":        rows
        }

        with open(sol_path, "w", encoding="utf-8") as f:
            json.dump(sol_obj, f, indent=4, ensure_ascii=False)

        return sol_path

 
    ## 0.8 Model Builder 
    
    def _build_initial(self):
        for (o,d), grp in self.sel.items():
            for aid in grp["A2"]:
                self.lp.add_pt_only(o,d,aid)
            for aid in grp["A1"]:
                self.lp.add_pt_bike(o,d,aid)

    
    ## 0.9 helper price guidance

    def _is_gamma_compatible(self, o,d,a, eps = 1e-6):
        k = int(self.parsed["k_bike_legs"].get((o,d,a),1))
        if k <= 0:
            return False
        g = float(self.lp.gamma[(o,d)].X)

        det_util = ( self.ASC_BIKE + self.ASC_PT
            + self.BETA_Cost_PT * self.lp.pt_price
            + self.BETA_Time_PT * self.parsed["pt_time_min"][(o,d,a)]
            + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o,d,a), 0.0)
            + self.BETA_TR_BIKE * self.parsed["transfer_time_min"][(o,d,a)] )
        beta = float(self.BETA_Cost_BIKE)
        p_req = (g - det_util) / (beta * k)
        # per-arc cap (fallback to global if not provided)
        Pup_arc = self.lp.P_up_arc.get((o,d,a), self.lp.P_up) if hasattr(self.lp, "P_up_arc") else self.lp.P_up
        return (p_req <= Pup_arc + eps) and (p_req >= self.lp.P_bar - eps)
    
    
    # 1. Initial Model

    ## 1.1 Make initial selection
    def make_initial_selection_enhanced_2(self):
            """
            Enhanced initial selection that favors competitive PT+bike (A1) while being robust to fractional mult_A1.
            - Computes per-OD car best utility and scores all PT+bike/PT-only at P_bar.
            - A1 cap per-OD = base_cap := ceil(mult_A1 * L), integer.
            If many competitive A1 exist, allow a 'surge' up to min(L, #competitive),
            but never below base_cap. (All caps are integers.)
            - A2 cap per-OD = K_PT (clipped to available).
            Returns: sel[(o,d)] = {"A1": [arc_ids], "A2": [arc_ids]}
            """

            parsed = self.parsed

            # environment/pricing from the LP
            P_bar       = float(self.lp.P_bar)
            pt_price    = float(self.lp.pt_price)
            dep_cost    = float(self.lp.dep_cost)
            parking_fee = float(self.lp.parking_fee)

            # choice parameters
            ASC_PT, ASC_BIKE, ASC_CAR = self.ASC_PT, self.ASC_BIKE, self.ASC_CAR
            BcB, BtB, BrB = self.BETA_Cost_BIKE, self.BETA_Time_BIKE, self.BETA_TR_BIKE
            BcP, BtP, BrP = self.BETA_Cost_PT,   self.BETA_Time_PT,   self.BETA_TR_PT
            BcC, BpC, BtC = self.BETA_Cost_Car,  self.BETA_Cost_park, self.BETA_Time_Car

            # caps (sanitize types)
            
            self.L_base = int(self.L)
            self.A1_base_per_od   = {}
            self.A1_eff_cap_od    = {}   # max A1 allowed after surge
            self.L_total_cap_od   = {}   # max (A1 + A2)
            L        = int(self.L)
            K_PT     = max(0, int(self.K_PT))
            mult_A1  = float(self.mult_A1)
            if mult_A1 < 0:
                raise ValueError("mult_A1 must be >= 0")

            sel = {}
            stats = {'total_ods': 0, 'pt_bike_competitive': 0, 'pt_bike_selected': 0, 'surge_applied': 0}

            for (o, d) in parsed["OD_pairs"]:
                od = f"{o}_{d}"
                stats['total_ods'] += 1

                # --- best Car utility ---
                best_car_util = float('inf')
                for arc in parsed["car_paths"].get(od, []):
                    a = arc["arc_id"]
                    F  = parsed["total_cost_car"][(o, d, a)]
                    Tt = parsed["travel_time_min"][(o, d, a)]
                    u  = (ASC_CAR + BcC * (F - dep_cost) + BpC * parking_fee + BtC * Tt)
                    if u < best_car_util:
                        best_car_util = u

                # --- score PT+bike at P_bar ---
                pt_bike_scored = []  # [(util, arc_id)]
                for arc in parsed["arcs_pt_bike"].get(od, []):
                    a = arc["arc_id"]
                    k = self.parsed["k_bike_legs"].get((o,d,a), 0)
                    u = (ASC_PT + ASC_BIKE
                        + BcP * pt_price
                        + BcB * k * P_bar
                        + BtP * parsed["pt_time_min"][(o, d, a)]
                        + BtB * parsed["bike_time_min"].get((o, d, a), 0.0)
                        + BrB * parsed["transfer_time_min"][(o, d, a)])
                    pt_bike_scored.append((u, a))
                    #print(a,k)
                pt_bike_scored.sort(key=lambda x: x[0])

                # competitive vs non-competitive (w.r.t. best car)
                comp = [(u, a) for (u, a) in pt_bike_scored if u < best_car_util]
                comp_count = len(comp)
                if comp_count > 0:
                    stats['pt_bike_competitive'] += 1

                # --- score PT-only (top K_PT)
                pt_only_scored = []
                for arc in parsed["arcs_pt_only"].get(od, []):
                    a = arc["arc_id"]
                    u = (ASC_PT
                        + BcP * pt_price
                        + BtP * parsed["pt_time_min"][(o, d, a)]
                        + BrP * parsed["transfer_time_min"][(o, d, a)])
                    pt_only_scored.append((u, a))
                pt_only_scored.sort(key=lambda x: x[0])

                # --- A1 capacity logic (INTEGER, robust to mult_A1 in (0,∞)) ---
                base_A1_cap = max(0, math.ceil(mult_A1*L))
                comp_count = len([1 for (u, _) in pt_bike_scored if u < best_car_util])
                A1_cap = int(min(base_A1_cap, len(pt_bike_scored)))
                # surge the caps if A1 arcs are competitive
                extra = max(0, min(L, comp_count) - base_A1_cap)
                A1_eff_cap = base_A1_cap + extra
                #store caps
                self.A1_base_per_od[(o,d)] = int(base_A1_cap)
                self.A1_eff_cap_od[(o,d)]  = int(min(A1_eff_cap, len(pt_bike_scored)))   # can’t exceed available A1 arcs
                self.L_total_cap_od[(o,d)] = int(L + extra)                               # total (A1 + A2) cap
                # at init, keep only base A1 (leave surge for forward)
                A1_cap = int(min(base_A1_cap, len(pt_bike_scored)))


                # A2 cap is just K_PT clipped to available arcs
                A2_cap = int(min(K_PT, len(pt_only_scored)))

                kept_A1 = [a for _, a in pt_bike_scored[:A1_cap]]
                kept_A2 = [a for _, a in pt_only_scored[:A2_cap]]
                if kept_A1:
                    stats['pt_bike_selected'] += 1

                sel[(o, d)] = {"A1": kept_A1, "A2": kept_A2}

                # Save holdouts (extras up to min(L, comp_count)) for telemetry/debug
                holdout_start = A1_cap
                holdout_end  = self.A1_eff_cap_od[(o,d)]
                holdouts = [a for _, a in pt_bike_scored[holdout_start:holdout_end]]
                if holdouts:
                    stats['surge_applied'] += 1
                    self.initial_holdout_A1 = getattr(self, "initial_holdout_A1", {})
                    self.initial_holdout_A1[(o, d)] = holdouts
            # report
            print("\nInitial selection stats:")
            print(f"  Total ODs: {stats['total_ods']}")
            print(f"  ODs with competitive PT+bike: {stats['pt_bike_competitive']}")
            print(f"  ODs with PT+bike selected: {stats['pt_bike_selected']}")
            if stats['surge_applied'] > 0:
                print(f"  Surge applied in {stats['surge_applied']} OD pairs "
                    f"(comp_count > ceil(mult_A1*L), A1_cap raised up to min(L, comp_count))")
            return sel


    # 2. Batch Builders

    ## 2.1 D1 Token-budget greedy (default uses D1)

    def build_batch_D1_tokens(self, M: int = 20, mu_station: float = 0.5, 
                              lookahead: int = 80, safety: float = 1.25):
        # pre-rank after screening
        cand = self._list_A1_candidates_dual_aware(mu_station, screen_price=True)
        U, L = self._station_budgets()
        sel, used = [], set()
        rem = self._remaining_A1_cap_by_od()

        #build value list once
        pos_list, zero_list = [], []

        for gap, (o,d,a) in cand:
            if rem.get((o,d),0.0) <=0:
                continue
            qhat = self._qhat_max_for_arc(o,d,a,U,L)
            value = (-gap) * max(qhat, 1.0) # rewards small gap and large feasible flow proxy
            rec = (value, gap, qhat, o,d,a)
            (pos_list if qhat > 0 else zero_list).append(rec)
        pos_list.sort(reverse=True)
        zero_list.sort(reverse=True)

        def fits_single(o,d,a,q,Ucur, Lcur):
            for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                if delta > 0 and Ucur[i_str] < safety * q: return False
                if delta < 0 and Lcur[i_str] < safety * q: return False
            return True
        
        def fits_pair(a1, q1, a2, q2, Ucur, Lcur):
            agg={}
            for i_str, delta in self.lp.delta_ia.get(a1, {}).items():
                if delta: agg[i_str] = agg.get(i_str,0.0) + safety*q1*delta
            for i_str, delta in self.lp.delta_ia.get(a2, {}).items():
                if delta: agg[i_str] = agg.get(i_str,0.0) + safety*q2*delta           
            for i_str, s in agg.items():
                if s > Ucur[i_str] + 1e-12: return False
                if -s > Lcur[i_str] + 1e-12: return False
            return True
        
        Ucur, Lcur = dict(U), dict(L)
        k = 0
        idx = 0
        while k < M and (idx < len(pos_list) or zero_list):
            rec = pos_list[idx] if idx < len(pos_list) else zero_list.pop(0)
            if idx < len(pos_list): idx += 1
            value, gap, qhat, o, d, a = rec
            key = (o,d,a)
            if key in used:
                continue
            if rem.get((o,d), 0.0) <= 0:
                continue
            # solo placement
            if qhat > 0 and fits_single(o, d, a, qhat, Ucur, Lcur) and rem[(o,d)] >=1:
                sel.append(key); used.add(key); k += 1
                rem[(o,d)] -= 1
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta > 0: Ucur[i_str] -= safety*qhat
                    elif delta < 0: Lcur[i_str] -= safety*qhat
                continue

            #pair placement
            best = None
            pool = pos_list[idx:idx + lookahead] + zero_list[:lookahead]
            for v2,g2,q2,o2,d2,b in pool:
                key2 = (o2,d2,b)
                if key2 in used or key2 == key:
                    continue
                if (o2,d2) == (o,d):
                    if rem.get((o,d),0.0) < 2:
                        continue
                    else:
                        if rem.get((o,d), 0.0) <1 or rem.get((o2,d2), 0.0)<1:
                            continue
                q1_use = qhat if qhat > 0 else 1.0
                q2_use = q2 if q2 > 0 else 1.0
                if fits_pair(a,q1_use, b, q2_use, Ucur, Lcur):
                    best = (o,d,a,q1_use, o2, d2, b, q2_use)
                    break
            
            if best is not None:
                o1,d1,a1,q1,o2,d2,a2,q2 = best
                sel.append((o1,d1,a1)); used.add((o1,d1,a1)); k+=1
                rem[(o1,d1)] -= 1
                if k < M and rem.get((o2,d2), 0) >= 1:
                    sel.append((o2,d2,a2)); used.add((o2,d2,a2)); k +=1
                    rem[(o2,d2)] -=1
                agg = {}
                for i_str, delta in self.lp.delta_ia.get(a1, {}).items():
                    if delta: agg[i_str] = agg.get(i_str, 0.0) + safety*q1*delta
                for i_str, delta in self.lp.delta_ia.get(a2, {}).items():
                    if delta: agg[i_str] = agg.get(i_str, 0.0) + safety*q2*delta
                for i_str, s in agg.items():
                    if s > 0: Ucur[i_str] -= s
                    if -s > 0: Lcur[i_str] -= -s
                continue
            
            continue
        return sel[:M]


    # 3. Trial Add arcs with dual aware

    
    def trial_add_batch_value_tiebreak_fast(self, batch, time_limit=120, eps_scale=1e-6,
                                        accept_only_positive=False, q_min_accept=1e-9):
        """
        Faster trial:
        - Copies live LP
        - Copies simplex basis (VBasis/CBasis) from live -> trial
        - Adds batch arcs
        - Applies ε to new q's
        - Solves with Dual Simplex (Method=1) under a tight time limit
        - Optionally filters acceptance to only arcs with q > q_min_accept

        OR simply:
        
        Trial on a model COPY:
      - add the batch of A1 arcs,
      - set objective coefficients explicitly,
      - add a tiny epsilon to new q's (tie-break),
      - optimize.

        Returns: (status, obj, q_new_sum, pos_flow_keys)
        """
        try:
            mcopy = self.lp.m.copy()
            mcopy.Params.Method = 1
            if time_limit is not None:
                mcopy.Params.TimeLimit = int(time_limit)

            # ---- warm-start basis on the existing columns/rows ----
            try:
                vb = self.lp.m.getAttr(gp.GRB.Attr.VBasis, self.lp.m.getVars())
                cb = self.lp.m.getAttr(gp.GRB.Attr.CBasis, self.lp.m.getConstrs())
                mcopy.setAttr(gp.GRB.Attr.VBasis, mcopy.getVars(), vb)
                mcopy.setAttr(gp.GRB.Attr.CBasis, mcopy.getConstrs(), cb)
            except Exception as e:
                # basis might be unavailable if previous solve wasn't simplex-optimal; safe to ignore
                if not getattr(self, "quiet", True):
                    print(f"[trial-fast] basis transfer skipped: {e!r}")

            trial_q_pairs = []
            base_obj = float(self.lp.objective_value() or 0.0)

            for (o, d, a) in batch:
                k = int(self.parsed["k_bike_legs"].get((o,d,a), 1))  # default 1 for A1
                Qod = self.lp.demands[(o, d)]
                Pup = self.lp.P_up_arc.get((o,d,a), self.lp.P_up)
                p = mcopy.addVar(lb=self.lp.P_bar, ub=Pup, vtype=gp.GRB.CONTINUOUS, name=f"t_p_{o}_{d}_{a}")
                q = mcopy.addVar(lb=0.0,         ub=Qod,              vtype=gp.GRB.CONTINUOUS, name=f"t_q_{o}_{d}_{a}")
                z = mcopy.addVar(lb=-gp.GRB.INFINITY,                  vtype=gp.GRB.CONTINUOUS, name=f"t_z_{o}_{d}_{a}")

                # McCormick
                mcopy.addConstr(z >= self.lp.P_bar * q,                                name=f"t_zmin1_{o}_{d}_{a}")
                mcopy.addConstr(z <= Pup  * q,                                name=f"t_zmax1_{o}_{d}_{a}")
                mcopy.addConstr(z >= Pup * q + p*Qod - Pup * Qod,    name=f"t_zmin2_{o}_{d}_{a}")
                mcopy.addConstr(z <= p*Qod + self.lp.P_bar*q - self.lp.P_bar*Qod,      name=f"t_zmax2_{o}_{d}_{a}")

                # γ-row
                rhs = ( self.ASC_BIKE + self.ASC_PT
                    + self.BETA_Cost_PT   * self.lp.pt_price
                    + self.BETA_Cost_BIKE * k * p
                    + self.BETA_Time_PT   * self.parsed["pt_time_min"][(o, d, a)]
                    + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                    + self.BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o, d, a)] )
                mcopy.addConstr(mcopy.getVarByName(f"gamma_{o}_{d}") <= rhs, name=f"t_gammaA_{o}_{d}_{a}")

                # demand
                dem = mcopy.getConstrByName(f"demand_{o}_{d}")
                mcopy.chgCoeff(dem, q, +1.0)

                # capacity rows
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta:
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_{i_str}"),        q, delta)
                        mcopy.chgCoeff(mcopy.getConstrByName(f"StationCap_nonneg_{i_str}"), q, delta)

                # strong duality (LHS)
                sd = mcopy.getConstrByName("StrongDuality")
                coeff_q = ( self.ASC_BIKE + self.ASC_PT
                        + self.BETA_Cost_PT * self.lp.pt_price
                        + self.BETA_Time_PT * self.parsed["pt_time_min"][(o, d, a)]
                        + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                        + self.BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o, d, a)] )
                mcopy.chgCoeff(sd, q, coeff_q)
                mcopy.chgCoeff(sd, z, self.BETA_Cost_BIKE * k)

                # objective
                ridership_coeff = 2 * self.lp.P_up
                resource_coeff  = self.lp._resource_coeff.get((o, d, a), 0.0)
                z.setAttr(gp.GRB.Attr.Obj, float(k))
                q_base = (ridership_coeff - self.lp.cost_bike*float(k) + self.lp.theta * resource_coeff)
                q.setAttr(gp.GRB.Attr.Obj, q_base)
                trial_q_pairs.append(((o, d, a), q, q_base))

            # ε tie-breaker
            if trial_q_pairs:
                eps = eps_scale * max(1.0, abs(base_obj)) / max(1, len(trial_q_pairs))
                for _, q, q_base in trial_q_pairs:
                    q.setAttr(gp.GRB.Attr.Obj, q_base + eps)

            mcopy.optimize()
            status = int(mcopy.Status)
            if (mcopy.SolCount or 0) == 0:
                return (status, None, None, None, eps, None, None)

            # collect positive-flow newcomers to filter acceptance
            pos_flow = [key for (key, q, _) in trial_q_pairs if float(q.X) > q_min_accept]
            q_new_sum = float(sum(q.X for (_key, q, _base) in trial_q_pairs))

            #net total flow computation
            base_A1_flow = 0.0
            for (o,d,a) in self.lp._present_A1:
                base_A1_flow += float(self.lp.q[(o,d,a)].X)
            trial_A1_existing_flow = 0.0
            for (o,d,a) in self.lp._present_A1:
                v=mcopy.getVarByName(f"q_{o}_{d}_{a}")
                if v is not None:
                    trial_A1_existing_flow += float(v.X)
            net_A1_flow_change = (trial_A1_existing_flow + q_new_sum) - base_A1_flow
            if net_A1_flow_change < 1:
                net_A1_flow_change = 0.0

            base_car_flow = 0.0
            for (o,d) in self.lp.W:
                    od = f"{o}_{d}"
                    for arc in self.lp.car_paths.get(od, []):
                        a = arc["arc_id"]
                        base_car_flow += float(self.lp.q[(o,d,a)].X)


            trial_car_flow =0.0
            missing_car_vars = []
            for (o,d) in self.lp.W:
                od = f"{o}_{d}"
                for arc in self.lp.car_paths.get(od, []):
                    a = arc["arc_id"]
                    v=mcopy.getVarByName(f"q_{o}_{d}_{a}")
                    if v is not None:
                        trial_car_flow += float(v.X)
                    else:
                        missing_car_vars.append((o,d,a))
            net_car_flow_change = trial_car_flow - base_car_flow


            # Optional strict filter: only accept the subset that actually carried flow
            if accept_only_positive and not pos_flow:
                # no new flow -> behave as "no-improvement"
                return (status, float(mcopy.ObjVal), 0.0, [])

            return (status, float(mcopy.ObjVal), q_new_sum, pos_flow, eps, net_A1_flow_change, net_car_flow_change  )

        except Exception as e:
            print(f"[trial-fast] exception: {e!r}")
            return (None, None, None, None, None, None, None)

    #====================================================================================================
    
    # 4. Run Forward with batches (use the first one)
    def clean_run_forward_with_batch(
    self,
    batch_builder,
    *,
    max_batches: int = 30,
    M: int = 20,
    mu_station: float = 0.5,
    refresh_every: int = 1,
    time_limit_eval: int = 20):
        """
        Clean batch-based forward pass with neutral-acceptance and ε tie-break trials.
        Enforces per-OD cap L when assembling batches.
        Records timing/telemetry for JSON export.
        """
        """
                It must return a list of (o, d, a) A1 candidates of length <= M.

        - Uses:
            * self._build_initial()     -> builds the restricted LP from current self.sel
            * self.trial_add_batch_value_tiebreak(...) -> trial on a model copy, returns (status, obj, q_new_sum)
            * self.accept_neutral_or_better(...)       -> neutral acceptance (ε-tie-break aware)
            * self.lp.add_pt_bike(o,d,a)               -> applies accepted arcs to the live LP
            * self.lp.optimize()                        -> re-optimizes live LP (Dual Simplex)

        - Diagnostics kept:
            * self.lp.debug_after_opt("...")           -> counts, totals by mode, station activity
            * self.cg_reduced_cost_scan(top_report=10) -> reports positive-RC candidates
            * self.diagnose_gamma_compatibility()      -> checks γ-compatibility at P_up
            * self._check_station_balance(batch)       -> prints precheck balance of the batch

        Returns:
            final live objective value (float) or None if base solve failed.
        """

        """
        Clean batch-based forward pass with neutral-acceptance and ε tie-break trials.
        Enforces per-OD cap L when assembling batches.
        """

        import time

        # ---------- reset forward telemetry ----------
        self.forward_method_name     = getattr(batch_builder, "__name__", str(batch_builder))
        self.forward_trials_attempted = 0         # all trial solves attempted (accepted or not)
        self.forward_batches_accepted = 0
        self.forward_total_build_sec  = 0.0       # batch construction time
        self.forward_total_trial_sec  = 0.0       # sum over all trials
        self.forward_total_reopt_sec  = 0.0       # sum over accepted batch re-optimizations
        self.forward_avg_trial_sec    = None      # averages are accepted-only
        self.forward_avg_reopt_sec    = None
        self.forward_accepted_batches = []        # list of dicts (one per accepted batch)

        accepted_trial_times = []   # to compute accepted-only avg
        accepted_reopt_times = []

        # Optional: held-out accounting (from "worse" selection)
        holdout_map = getattr(self, "initial_holdout_A1", {}) or {}
        heldout_set = {(o, d, a) for (o, d), lst in holdout_map.items() for a in lst}
        t_forward_start = time.perf_counter()
        # 1) Build initial restricted model and solve base (concurrent, then Dual)
        t_build_start = time.perf_counter()
        self._build_initial()
        t_build_finish = time.perf_counter()
        t_inital_build = t_build_finish-t_build_start 
        print(f"Model Build Time = {t_inital_build}")
        old_method = self.lp.m.Params.Method
        try:
            self.lp.m.Params.Method = -1
            t0 = time.perf_counter()
            base_val = self.lp.optimize()
            t1 = time.perf_counter()
            if base_val is None:
                print("[batch-forward] base failed.")
                return None
            print(f"[batch-forward] base objective = {base_val:.6f} | base_solve_time = {(t1 - t0):.3f}s")
        finally:
            self.lp.m.Params.Method = 1

        # Diagnostics at base
        self.lp.debug_after_opt("batch_forward_base")
        self.cg_reduced_cost_scan(top_report=10)
        self.diagnose_gamma_compatibility()

        # 2) Batch loop
        total_build_time = 0.0
        total_trial_time = 0.0
        total_reopt_time = 0.0
        accepted_batches = 0

        for it in range(max_batches):
            # Build batch and enforce per-OD cap
            tb0 = time.perf_counter()
            batch = batch_builder(M=M, mu_station=mu_station)
            batch = [(o,d,a) for (o,d,a) in batch if (o,d,a) not in self.lp._present_A1]
            tb1 = time.perf_counter()
            build_time = tb1 - tb0

            #batch = self._enforce_per_od_cap(batch, cap_L=self.L)
            if not batch:
                print("[batch-forward] no viable candidates after OD-cap filter.")
                break

            # Optional: station balance precheck
            if hasattr(self, "_check_station_balance"):
                self._check_station_balance(batch)

            # Trial on a copy with ε tie-break (returns (status, obj, q_new_sum))
            tt0 = time.perf_counter()
            #status, obj_with_eps, q_new,_, eps, q_new_cnt, delta_A1_flow, _ = self.trial_add_batch_value_tiebreak_fast(batch, time_limit=time_limit_eval)
            status, obj_with_eps, q_new,_, eps, net_bike_flow_change, net_car_flow_change = self.trial_add_batch_value_tiebreak_fast(batch, time_limit=time_limit_eval)

            tt1 = time.perf_counter()

            trial_time = tt1 - tt0
            total_build_time += build_time
            total_trial_time += trial_time
            self.forward_trials_attempted += 1
            obj_val = None if obj_with_eps is None else (obj_with_eps - (eps or 0.0) * (q_new or 0.0))
            print(
                f"[batch-forward] trial {it+1}: size={len(batch)} | "
                f"batch build_time={build_time:.3f}s | trial_time={trial_time:.3f}s | "
                f"trial_status={status} | trial_obj={obj_val} | base_obj={base_val} | flow_on_new_arcs: {q_new} | net_bike_flow_change: {net_bike_flow_change} | net_car_flow_change: {net_car_flow_change}"
            )

            if obj_val is None:
                print(f"[batch-forward] trial produced no incumbent (status={status}); stopping.")
                break

            # Neutral acceptance: objective >= base (within rel tol) OR same obj and q_new > 0
            if not self.accept_neutral_or_better(obj_val, base_val, net_bike_flow_change, net_car_flow_change, rel=self.rel_impr_tol_add):
                print("[batch-forward] no improvement; stopping.")
                break

            # Accept: add to live LP and re-opt
            prev_base = base_val
            held_added = sum(1 for (o, d, a) in batch if (o, d, a) in heldout_set)

            tr0 = time.perf_counter()
            for (o, d, a) in batch:
                self.lp.add_pt_bike(o, d, a)
            base_val = self.lp.optimize()
            tr1 = time.perf_counter()

            reopt_time = tr1 - tr0
            total_reopt_time += reopt_time
            accepted_batches += 1

            print(
                f"[batch-forward] accept {it+1}: added={len(batch)} | heldout_added={held_added} | "
                f"reopt_time={reopt_time:.3f}s | new_obj={base_val:.6f}"
            )
            self.lp.debug_after_opt(f"batch_forward_accept_{accepted_batches}")

            # record accepted-only timing & batch details
            accepted_trial_times.append(trial_time)
            accepted_reopt_times.append(reopt_time)
            self.forward_accepted_batches.append({
                "iter": it + 1,
                "size": len(batch),
                "heldout_added": int(held_added),
                "trial_status": int(status) if status is not None else None,
                "trial_obj": float(obj_val) if obj_val is not None else None,
                "base_before": float(prev_base) if prev_base is not None else None,
                "base_after": float(base_val) if base_val is not None else None,
                "trial_time_s": float(trial_time),
                "reopt_time_s": float(reopt_time),
                "batch_arcs": [(int(o), int(d), str(a)) for (o, d, a) in batch],
            })

            if (it + 1) % refresh_every == 0:
                pass  # builder will read fresh duals next loop
        t_forward_end = time.perf_counter()
        forward_wall = t_forward_end - t_forward_start
        heuristic_time = float(getattr(self, "_t_select", 0.0)) + (forward_wall - t_inital_build)

        # finalize telemetry
        self.forward_batches_accepted = accepted_batches
        self.forward_total_build_sec  = total_build_time
        self.forward_total_trial_sec  = total_trial_time
        self.forward_total_reopt_sec  = total_reopt_time
        # new (optional) extras
        self.forward_total_trial_sec_accepted = sum(accepted_trial_times) if accepted_trial_times else 0.0
        self.forward_overall_forward_sec = (
            self.forward_total_build_sec + self.forward_total_trial_sec + self.forward_total_reopt_sec
        )
        if accepted_trial_times:
            self.forward_avg_trial_sec = sum(accepted_trial_times) / len(accepted_trial_times)
        if accepted_reopt_times:
            self.forward_avg_reopt_sec = sum(accepted_reopt_times) / len(accepted_reopt_times)

        print(
            f"[batch-forward] batches accepted = {accepted_batches}, final obj = {base_val:.6f}\n"
            f"[batch-forward] totals: batch build time ={total_build_time:.3f}s | "
            f"trial time={total_trial_time:.3f}s | reopt={total_reopt_time:.3f}s "
            f"heldout_added_total={sum(b['heldout_added'] for b in self.forward_accepted_batches)}"
        )
        return base_val, heuristic_time


    #====================================================================================================

    # 5. New Run

    def new_run(self, *, max_add: int = 1000, max_drops: int = 200, method: str = "D1", **kwargs):
        """
        method in {"D1","D2","D3"} chooses the batch builder.
        kwargs are forwarded to the batch runner and/or builders (e.g., M, mu_station, time_limit_eval).
        """

        if method == "D1":
            best, heuristic_time = self.clean_run_forward_with_batch(self.build_batch_D1_tokens, **kwargs)
        elif method == "D2":
            best = self.clean_run_forward_with_batch(self.build_batch_D2_knapsack, **kwargs)
        elif method == "D3":
            best = self.clean_run_forward_with_batch(self.build_batch_D3_cycle_pairs, **kwargs)
        elif method == "D4":
            best = self.clean_run_forward_with_batch(self.build_batch_D4_exact_balance_lp, **kwargs)
        elif method == "D5":
            best = self.clean_run_forward_with_batch(self.build_batch_D5_k_cycles, **kwargs)
        else:
            raise ValueError("Unknown method. Use 'D1', 'D2', or 'D3', 'D4' or 'D5'.")

        return best, heuristic_time

    #====================================================================================================

    # 6. Diagnostics

    def _diagnose_candidate_funnel(self, mu_station=0.5, qhat_eps=1e-9):
        cand = self._list_A1_candidates_dual_aware(mu_station)    # total not-present
        n_total = sum(len(self.parsed["arcs_pt_bike"].get(f"{o}_{d}", [])) for (o,d) in self.parsed["OD_pairs"])
        n_present = len(self.lp._present_A1)
        n_cand = len(cand)
        U,L = self._station_budgets()
        n_qpos = 0
        for _,(o,d,a) in cand:
            qhat = self._qhat_max_for_arc(o,d,a,U,L)
            if qhat > qhat_eps:
                n_qpos += 1
        print(f"[diag] A1 total={n_total} present={n_present} not_present={n_total-n_present}")
        print(f"[diag] candidates(not_present)={n_cand} with_qhat>0={n_qpos}, with_qhat<=0={n_cand-n_qpos}")

    def _check_station_balance(self, batch):
        agg = {str(i): 0.0 for i in self.lp.stations_list}
        for (o,d,a) in batch:
            for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                if delta: agg[i_str] += delta
        bad = [(i,s) for i,s in agg.items() if abs(s) > 1e-9]
        if bad:
            print("[precheck] unbalanced stations:", bad[:5], "…")
        else:
            print("[precheck] batch is exactly station-balanced.")

    def cg_reduced_cost_scan(self, top_report: int = 10):
        """
        Report reduced costs (r_q, r_z) for not-present A1 arcs at current basis.
        If all r_q <= 0 and r_z <= 0, forward add cannot improve (CG fixed point).
        """
        m = self.lp.m
        # duals
        sigma = float(self.lp.sd_constr.Pi)
        alpha = { (o,d): float(self.lp.dem_eq[(o,d)].Pi) for (o,d) in self.parsed["OD_pairs"] }
        pi_up  = { str(i): float(self.lp.cap_constr[str(i)].Pi)   for i in self.lp.stations_list }
        pi_lo  = { str(i): float(self.lp.cap_nonneg[str(i)].Pi)   for i in self.lp.stations_list }  # ≤ 0 in a max model
        # obj weights
        ridership_coeff = 2.0 * self.lp.P_up
        results = []

        def coeff_sd_q(o,d,a):
            return ( self.ASC_BIKE + self.ASC_PT
                + self.BETA_Cost_PT * self.lp.pt_price
                + self.BETA_Time_PT * self.parsed["pt_time_min"][(o, d, a)]
                + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                + self.BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o, d, a)] )

        for (o,d) in self.parsed["OD_pairs"]:
            od = f"{o}_{d}"
            for arc in self.parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                if (o,d,a) in self.lp._present_A1:
                    continue
                cq = ridership_coeff - self.lp.cost_bike + self.lp.theta * self.lp._resource_coeff.get((o,d,a), 0.0)
                # station contribution
                station_term = 0.0
                for i_str, delta in self.lp.delta_ia.get(a, {}).items():
                    if delta != 0:
                        station_term += (pi_up.get(i_str,0.0) + pi_lo.get(i_str,0.0)) * float(delta)
                rq = cq - alpha[(o,d)] - sigma * coeff_sd_q(o,d,a) - station_term
                rz = 1.0 - sigma * self.BETA_Cost_BIKE
                results.append(((o,d,a), rq, rz))

        # stats
        pos = [(k,rq,rz) for (k,rq,rz) in results if rq > 1e-9 or rz > 1e-9]
        print(f"[cg] scanned not-present A1 = {len(results)} | positive RC = {len(pos)} "
            f"({100.0*len(pos)/max(1,len(results)):.1f}%)")
        # top by max(rq,rz)
        pos_sorted = sorted(pos, key=lambda t: max(t[1], t[2]), reverse=True)[:top_report]
        for (o,d,a), rq, rz in pos_sorted:
            print(f"  (o={o},d={d},a={a})  r_q={rq:.6f}  r_z={rz:.6f}")
        return results

    def diagnose_gamma_compatibility(self, eps: float = 1e-9):
        BcB = self.BETA_Cost_BIKE
        Pbar, Pup = self.lp.P_bar, self.lp.P_up
        gamma_now = { (o,d): self.lp.gamma[(o,d)].X for (o,d) in self.parsed["OD_pairs"] }

        def alpha(o,d,a):
            return ( self.ASC_BIKE + self.ASC_PT
                + self.BETA_Cost_PT * self.lp.pt_price
                + self.BETA_Time_PT * self.parsed["pt_time_min"][(o, d, a)]
                + self.BETA_Time_BIKE * self.parsed["bike_time_min"].get((o, d, a), 0.0)
                + self.BETA_TR_BIKE   * self.parsed["transfer_time_min"][(o, d, a)] )

        tot = bad = 0
        for (o,d) in self.parsed["OD_pairs"]:
            od = f"{o}_{d}"
            g = gamma_now[(o,d)]
            for arc in self.parsed["arcs_pt_bike"].get(od, []):
                a = arc["arc_id"]
                if (o,d,a) in self.lp._present_A1:
                    continue
                p_req = max(Pbar, (g - alpha(o,d,a))/BcB)
                tot += 1
                if p_req > Pup + eps:
                    bad += 1
        pct = 100.0*bad/max(1,tot)
        print(f"[gamma-compat] not-present A1: {tot}, incompatible at P_up: {bad} ({pct:.1f}%)")


   