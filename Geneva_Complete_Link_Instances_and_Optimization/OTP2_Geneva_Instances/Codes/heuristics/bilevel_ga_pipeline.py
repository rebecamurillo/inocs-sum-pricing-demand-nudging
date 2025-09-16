# bilevel_ga_pipeline.py

# pipeline.py
from __future__ import annotations
from typing import Dict, Tuple, List, Callable, Any
from ga_core import run_ga, GAParams
from inner_lp_reusable import ReusableInnerLP

class Bilevel_GA_Pipeline:

    """
    Lu, R., Correia, G. H. D. A., Zhao, X., Liang, X., & Lv, Y. (2021).
    Performance of one-way carsharing systems under combined strategy of pricing and relocations. Transportmetrica B, 9(1), 134–152.

     - Chromosome: Design bits nu over selected (o,d,arc_id)
     - Fitness: calls single level optimizer with fixed nu, without outputs if suppress_io=True

    """

    def __init__(
            self,
            parsed_data: dict,
            solver: Callable[..., Tuple[Any,dict | None, str | None]],
            nu_keys: List[Tuple],               # ordered list of (o,d,arc_id)
            time_limit_eval: int = 60,          # per-evaluation timelimit (s)
            seed: int = 42  
            ):
        self.parsed_data = parsed_data
        self.solver = solver
        self.nu_keys = nu_keys
        self.m = len(nu_keys)
        self.time_limit_eval = time_limit_eval
        self.seed = seed


        # Build reusable inner LP once (quiet)
        self.inner = ReusableInnerLP(parsed_data, output_flag=0, method=1)
        self._cache = {}


    @staticmethod

    def build_nu_keys(parsed_data:dict) -> List[Tuple]:
        
        keys = []

        for (o,d) in parsed_data["OD_pairs"]:
            od = f"{o}_{d}"
            for arc in parsed_data["arcs_pt_bike"].get(od, []):
                keys.append((o,d,arc["arc_id"]))
            for arc in parsed_data["arcs_pt_only"].get(od, []):
                keys.append((o,d,arc["arc_id"]))     
        return keys
    
    def bits_to_fixed_nu(self, bits: List[int]) -> Dict [Tuple, int]:
        return {k: int(bits[i]) for i, k in enumerate(self.nu_keys)}
    

    def _fitness(self, bits):
        key = tuple(bits)
        if key in self._cache:
            return self._cache[key]
        val = self.inner.evaluate(bits, self.nu_keys, time_limit=self.time_limit_eval)
        self._cache[key] = val
        return val

    def run(self, params: GAParams):
        return run_ga(self._fitness, self.m, params=params)
    
    def finalize(
            self,
            best_bits: List[int],
            json_path: str,
            save_folder: str,
            final_time_limit: int = 600
            ) -> dict | None:
        fixed_nu = self.bits_to_fixed_nu(best_bits)

        _, sol, _ = self.solver(            
            self.parsed_data,
            json_file_path=json_path,
            save_folder=save_folder,
            fixed_nu=fixed_nu,
            suppress_io=False,          # write logs/JSON/DF now
            time_limit=final_time_limit,
            verbose=True, verbose2=True)
        return sol
    
