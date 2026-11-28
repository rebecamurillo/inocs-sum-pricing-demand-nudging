import pytest

from pricing_demo.domain.pricing_keys import (
    FIXED_SOLVER_INPUTS,
    KEPT_SIMULATION_REASON,
    KEPT_SOLVE_REASON,
    SOLVER_GOALS,
    simulation_inputs,
    simulation_key,
    solve_id,
    solve_inputs,
    solve_key,
)
from pricing_demo.domain.pricing_versions import PricingGoals, new_draft_goals

GOALS = new_draft_goals(None)
INSTANCE = "i" * 64
FINGERPRINT = "f" * 64


def a_solve_key(
    goals: PricingGoals = GOALS, instance: str = INSTANCE, fp: str = FINGERPRINT
) -> str:
    return solve_key(goals, instance, fp)


def a_simulation_key(**changes: object) -> str:
    values: dict[str, object] = {
        "instance_key": INSTANCE,
        "period_id": "geneva-3km.v1.mon-08",
        "rule_id": "balanced-score",
        "rule_version": 1,
        "rule_parameters": {"price_weight": 0.5, "time_weight": 0.5},
        "scheme_kind": "model_prices",
        "solve_key": a_solve_key(),
        "flat_price_kind": None,
        "flat_price_amount_chf": None,
        "pt_fare_chf": 2.0,
        "car_parking_fee_chf": 2.8,
    }
    values.update(changes)
    return simulation_key(**values)  # type: ignore[arg-type]


def test_the_solver_goals_are_the_goals_except_the_flat_price() -> None:
    assert SOLVER_GOALS == (
        "cost_bike_chf",
        "lowest_price_chf",
        "ridership_weight",
        "station_balance_weight",
        "pt_fare_chf",
        "car_parking_fee_chf",
        "max_displayed_options",
    )
    assert "flat_price_per_ride_chf" not in SOLVER_GOALS


def test_the_fixed_solver_inputs_are_those_of_the_architecture() -> None:
    assert dict(FIXED_SOLVER_INPUTS) == {
        "capacity": None,
        "inventory_level": None,
        "dep_cost": 0.0,
        "mult_A1": 1,
        "sol_method": -1,
        "verbose": False,
    }


def test_the_solve_inputs_hold_the_goals_the_fixed_inputs_the_instance_and_the_package() -> None:
    inputs = solve_inputs(GOALS, INSTANCE, FINGERPRINT)

    assert inputs["step"] == "pricing_model"
    assert set(inputs["goals"]) == set(SOLVER_GOALS)
    assert inputs["fixed"] == {
        "capacity": None,
        "inventory_level": None,
        "dep_cost": 0,
        "mult_A1": 1,
        "sol_method": -1,
        "verbose": False,
    }
    assert inputs["upstream"] == {"travellers_and_bikes": INSTANCE}
    assert inputs["package_fingerprint"] == FINGERPRINT


def test_two_versions_that_differ_only_in_their_flat_price_have_the_same_solve_key() -> None:
    other = GOALS.replacing({"flat_price_per_ride_chf": 3.5})

    assert a_solve_key(other) == a_solve_key()


@pytest.mark.parametrize("name", SOLVER_GOALS)
def test_each_solver_goal_changes_the_solve_key(name: str) -> None:
    other = GOALS.replacing({name: float(GOALS.as_dict()[name]) + 1})

    assert a_solve_key(other) != a_solve_key()


def test_the_instance_and_the_package_change_the_solve_key() -> None:
    assert a_solve_key(instance="j" * 64) != a_solve_key()
    assert a_solve_key(fp="e" * 64) != a_solve_key()


def test_a_whole_number_is_the_same_value_whatever_its_type() -> None:
    assert a_solve_key(GOALS.replacing({"max_displayed_options": 10.0})) == a_solve_key(
        GOALS.replacing({"max_displayed_options": 10})
    )


def test_the_solve_id_names_the_version_and_the_period() -> None:
    assert solve_id("geneva-3km.v1.A", "mon-08") == "geneva-3km.v1.A.mon-08"


def test_the_kept_reasons_say_what_was_reused() -> None:
    assert KEPT_SOLVE_REASON == "kept: these goals were already solved on this instance"
    assert KEPT_SIMULATION_REASON == "kept: already simulated with the same prices and rule"


def test_the_simulation_inputs_name_the_period_the_rule_the_scheme_and_the_prices() -> None:
    inputs = simulation_inputs(
        INSTANCE,
        "p",
        "balanced-score",
        1,
        {"price_weight": 0.5, "time_weight": 0.5},
        "flat",
        None,
        "per_ride",
        1.0,
        2.0,
        2.8,
    )

    assert inputs["instance_key"] == INSTANCE
    assert inputs["period_id"] == "p"
    assert inputs["rule"] == {
        "id": "balanced-score",
        "version": 1,
        "parameters": {"price_weight": 0.5, "time_weight": 0.5},
    }
    assert inputs["scheme"] == {"kind": "flat", "flat": {"kind": "per_ride", "amount_chf": 1}}
    assert (inputs["pt_fare_chf"], inputs["car_parking_fee_chf"]) == (2, 2.8)


def test_the_model_prices_scheme_is_named_by_the_solve_key() -> None:
    inputs = simulation_inputs(
        INSTANCE, "p", "r", 1, {}, "model_prices", "solve", None, None, 2.0, 2.8
    )

    assert inputs["scheme"] == {"kind": "model_prices", "solve_key": "solve"}


def test_the_same_inputs_give_the_same_simulation_key() -> None:
    assert a_simulation_key() == a_simulation_key()


@pytest.mark.parametrize(
    "changes",
    [
        {"instance_key": "j" * 64},
        {"period_id": "geneva-3km.v1.tue-08"},
        {"rule_id": "other"},
        {"rule_version": 2},
        {"rule_parameters": {"price_weight": 0.7, "time_weight": 0.3}},
        {
            "scheme_kind": "flat",
            "solve_key": None,
            "flat_price_kind": "per_ride",
            "flat_price_amount_chf": 1.0,
        },
        {"solve_key": "other-solve"},
        {"pt_fare_chf": 2.5},
        {"car_parking_fee_chf": 3.0},
    ],
)
def test_each_input_changes_the_simulation_key(changes: dict[str, object]) -> None:
    assert a_simulation_key(**changes) != a_simulation_key()


def test_the_flat_amount_changes_the_flat_simulation_key_and_a_goal_does_not() -> None:
    flat = {
        "scheme_kind": "flat",
        "solve_key": None,
        "flat_price_kind": "per_ride",
        "flat_price_amount_chf": 1.0,
    }

    assert a_simulation_key(**{**flat, "flat_price_amount_chf": 1.5}) != a_simulation_key(**flat)
    # A flat simulation does not read the solve: two versions of other goals share it.
    assert a_simulation_key(**{**flat, "solve_key": "x"}) == a_simulation_key(**flat)
