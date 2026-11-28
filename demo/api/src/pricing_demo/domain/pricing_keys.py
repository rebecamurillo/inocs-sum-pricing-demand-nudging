"""The content keys of a pricing run: what a solve reads and what a simulation reads
(ARCHITECTURE.md § 4.1, § 4.3, § 5.2, § 6.3).

A key is the sha256 of a canonical JSON, as the build steps' keys are, so an unchanged input
finds the stored result again whichever pricing version asks for it. Pure: no I/O.
"""

from collections.abc import Mapping
from typing import Any

from pricing_demo.domain.build_plan import input_key
from pricing_demo.domain.pricing_versions import PricingGoals
from pricing_demo.domain.runs import StepName

# The goals the solver reads: the flat price is read by the traveller simulation only.
SOLVER_GOALS = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
)

# The version's goals under the package's `OptimizerParams` field names (`config.py:40-54`).
PACKAGE_GOAL_NAMES: Mapping[str, str] = {
    "cost_bike_chf": "cost_bike",
    "lowest_price_chf": "P_bar",
    "ridership_weight": "ridership_weight",
    "station_balance_weight": "theta",
    "pt_fare_chf": "pt_price",
    "car_parking_fee_chf": "parking_fee",
    "max_displayed_options": "max_displayed_alternatives",
}

# What the demonstrator always passes the solver, the same way (ARCHITECTURE.md § 4.1).
FIXED_SOLVER_INPUTS: Mapping[str, object] = {
    "capacity": None,
    "inventory_level": None,
    "dep_cost": 0.0,
    "mult_A1": 1,
    "sol_method": -1,
    "verbose": False,
}

KEPT_SOLVE_REASON = "kept: these goals were already solved on this instance"
KEPT_SIMULATION_REASON = "kept: already simulated with the same prices and rule"


def _normal(value: Any) -> Any:
    """20 and 20.0 are the same value: both hash as 20."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def solve_inputs(
    goals: PricingGoals, instance_key: str, package_fingerprint: str
) -> dict[str, Any]:
    """What the solve of a period reads: the goals except the flat price, the fixed solver
    inputs, the period's step-4 artefact and the package."""
    values = goals.as_dict()
    return {
        "step": StepName.PRICING_MODEL.value,
        "goals": {name: _normal(values[name]) for name in SOLVER_GOALS},
        "fixed": {name: _normal(value) for name, value in FIXED_SOLVER_INPUTS.items()},
        "upstream": {StepName.TRAVELLERS_AND_BIKES.value: instance_key},
        "package_fingerprint": package_fingerprint,
    }


def solve_key(goals: PricingGoals, instance_key: str, package_fingerprint: str) -> str:
    return input_key(solve_inputs(goals, instance_key, package_fingerprint))


def solve_id(pricing_version_id: str, period_key: str) -> str:
    return f"{pricing_version_id}.{period_key}"


def simulation_inputs(
    instance_key: str,
    period_id: str,
    rule_id: str,
    rule_version: int,
    rule_parameters: Mapping[str, float],
    scheme_kind: str,
    solve_key: str | None,
    flat_price_kind: str | None,
    flat_price_amount_chf: float | None,
    pt_fare_chf: float,
    car_parking_fee_chf: float,
) -> dict[str, Any]:
    """What a simulation reads. The scheme names the solve (model prices) or the flat price,
    never both: pricing versions of one period with the same flat price, fare and parking fee
    share one flat simulation."""
    scheme: dict[str, Any] = {"kind": scheme_kind}
    if scheme_kind == "model_prices":
        scheme["solve_key"] = solve_key
    else:
        scheme["flat"] = {"kind": flat_price_kind, "amount_chf": _normal(flat_price_amount_chf)}
    return {
        "instance_key": instance_key,
        "period_id": period_id,
        "rule": {
            "id": rule_id,
            "version": rule_version,
            "parameters": {name: _normal(value) for name, value in rule_parameters.items()},
        },
        "scheme": scheme,
        "pt_fare_chf": _normal(pt_fare_chf),
        "car_parking_fee_chf": _normal(car_parking_fee_chf),
    }


def simulation_key(
    instance_key: str,
    period_id: str,
    rule_id: str,
    rule_version: int,
    rule_parameters: Mapping[str, float],
    scheme_kind: str,
    solve_key: str | None,
    flat_price_kind: str | None,
    flat_price_amount_chf: float | None,
    pt_fare_chf: float,
    car_parking_fee_chf: float,
) -> str:
    return input_key(
        simulation_inputs(
            instance_key,
            period_id,
            rule_id,
            rule_version,
            rule_parameters,
            scheme_kind,
            solve_key,
            flat_price_kind,
            flat_price_amount_chf,
            pt_fare_chf,
            car_parking_fee_chf,
        )
    )
