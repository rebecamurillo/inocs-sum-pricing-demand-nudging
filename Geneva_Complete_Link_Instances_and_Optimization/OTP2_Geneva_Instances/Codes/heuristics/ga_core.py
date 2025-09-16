# ga_core.py

from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Callable, List, Tuple

@dataclass
class GAParams:
    N: int = 30                     #Population
    K: int = 100                    #max iterations
    Pc: float = 0.90                #cross-over probability (per mating)
    Pm: float = 0.1                 #mutation probability (per child)
    elite: int = 1                  #elites to keep
    early_window: int = 10          #compare best now vs best [-10]
    early_after: int  = 20           #start early-stop after this gen
    early_tol: float  =1e-3           #relative improvement threshold
    seed: int = 42                  #RNG seed


def _roulette_pick(weights: List[float]) -> int:
    #shift weights to positive, fall back to uniform if degenerate

    valid = [(i,w) for i, w in enumerate(weights) if w is not None and w == w and abs(w) != float('inf')]
    
    if not valid:
        return random.randrange(len(weights))
    
    minw= min(w for _, w in valid)
    
    adj = [(w - minw + 1e-12) if (w is not None and w == w and abs(w) != float('inf')) else 1e-12 for w in weights]
    
    total = sum(adj)
    
    if total <= 0.0 or total != total:
        return random.randrange(len(weights))
    
    r, acc = random.random()*total, 0.0
    
    for i, wi in enumerate(adj):
        acc += wi
        if acc >= r:
            return i
    return len(weights) - 1

def _uniform_crossover(a: List[int], b:List[int]) -> List[int]:
    return [ (ai if random.random() < 0.5 else bi) for ai, bi in zip(a,b)]

def _mutate_bits(y: List[int], pflip: float) -> None:
    for i in range(len(y)):
        if random.random() < pflip:
            y[i] ^= 1 # flip bit

def run_ga(
        fitness: Callable[[List[int]], float],  #maximize
        m: int,
        params: GAParams = GAParams(),) -> Tuple[List[int], float, List[float]]:
    
    random.seed(params.seed)

    #1 random init

    pop         = [[random.randint(0,1) for _ in range(m)] for _ in range(params.N)]
    fvals       = [fitness(ind) for ind in pop]
    best_idx    = max(range(params.N), key = lambda i:fvals[i])
    best_y      = pop[best_idx][:]
    best_f      = fvals[best_idx]
    hist_best   = [best_f]

    #2 Generations

    for gen in range(1, params.K+1):
        #early stop rule from Goncalo paper: Compare to best [-10] after gen > 20

        if gen > params.early_after and len(hist_best) >= params.early_window:
            prev = hist_best[-params.early_window]
            if abs(best_f - prev) / max(1, abs(best_f)) < params.early_tol:
                break

        #elitism
        elite_idx = sorted(range(len(fvals)), key=lambda i: fvals[i], reverse=True)[:params.elite]
        elites    = [pop[i][:] for i in elite_idx]
        elites_f  = [fvals[i]  for i in elite_idx]

        #offspring
        children = []

        while len(children) < params.N - params.elite:
            i,j = _roulette_pick(fvals), _roulette_pick(fvals)

            mom, dad = pop[i], pop[j]
            child = _uniform_crossover(mom, dad) if random.random() < params.Pc else mom[:]
            if random.random() < params.Pm:
                _mutate_bits(child, pflip = 1 / float(m))
            children.append(child)

        child_f = [fitness(ind) for ind in children]

        pop = elites + children
        fvals = elites_f + child_f
        
        
        #update incumbert
        gbest_idx = max(range(len(fvals)), key = lambda i: fvals[i])
        gbest_f = fvals[gbest_idx]

        if gbest_f > best_f:
            best_f = gbest_f
            best_y = pop[gbest_idx][:]
        hist_best.append(best_f)

    return best_y, best_f, hist_best
