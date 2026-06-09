# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/Codes/
from pathlib import Path
from typing import Any

from .metrics import summarize_experiment_solutions
from .p_off import compute_p_off
from .parser import parse_json_instance
from .solver import solve_bilevel_model__margarita_choice_params_pertrip_surge_curation_poff


def parse_instance(instance_path: str | Path) -> dict[str, Any]:
	return parse_json_instance(str(instance_path))


def solve(
	instance_path: str | Path,
	output_dir: str | Path,
	*,
	max_displayed_alternatives: int = 10,
	mult_A1: int = 1,
	capacity: int | None = None,
	inventory_level: tuple[float, float] | None = None,
	dep_cost: float = 0.0,
	cost_bike: float = 0.6,
	parking_fee: float = 2.8,
	P_bar: float = 0.6,
	pt_price: float = 2.0,
	theta: float = 0.5,
	ridership_weight: float = 8.0,
	sol_method: int = -1,
	verbose: bool = False,
	verbose2: bool = False,
) -> tuple[dict[str, Any], Path]:
	instance_path = Path(instance_path)
	output_dir = Path(output_dir)
	output_dir.mkdir(parents=True, exist_ok=True)

	parsed_data = parse_json_instance(str(instance_path))
	pinfo = compute_p_off(
		parsed_data,
		P_bar=P_bar,
		pt_price=pt_price,
		parking_fee=parking_fee,
		dep_cost=dep_cost,
		tol=0.2,
	)

	_, solution_dict, sol_path = solve_bilevel_model__margarita_choice_params_pertrip_surge_curation_poff(
		parsed_data,
		json_file_path=str(instance_path),
		save_folder=str(output_dir),
		max_displayed_alternatives=max_displayed_alternatives,
		mult_A1=mult_A1,
		capacity=capacity,
		inventory_level=inventory_level,
		dep_cost=dep_cost,
		cost_bike=cost_bike,
		parking_fee=parking_fee,
		P_bar=P_bar,
		pt_price=pt_price,
		theta=theta,
		ridership_weight=ridership_weight,
		sol_method=sol_method,
		verbose=verbose,
		verbose2=verbose2,
		p_off_map=pinfo["p_off"],
		disable_set=pinfo["disable"],
		global_p_off=pinfo["global_p_off"],
	)

	canonical_path = output_dir / "optimization_instance_results.json"
	import json

	with canonical_path.open("w", encoding="utf-8") as file_obj:
		json.dump(solution_dict, file_obj, ensure_ascii=False, indent=2)

	return solution_dict, canonical_path


def summarize(solution_input: str | Path):
	return summarize_experiment_solutions(str(solution_input), show=False)


__all__ = [
	"parse_instance",
	"solve",
	"summarize",
	"compute_p_off",
	"parse_json_instance",
	"solve_bilevel_model__margarita_choice_params_pertrip_surge_curation_poff",
	"summarize_experiment_solutions",
]
