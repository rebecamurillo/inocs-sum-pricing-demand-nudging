from pathlib import Path
from typing import Any

import pytest

from pricing_demo.domain.failure_codes import SOLVER_NO_SOLUTION, SOLVER_SIZE_LIMITED
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.solves import Solve
from pricing_demo.infrastructure.pricing_model.solve_reading import (
    PACKAGE_GOAL_NAMES,
    ProvenanceBase,
    licence_kind,
    optimizer_fields,
    read_solve,
    rows_from,
    size_limited,
    sol_count,
    solver_parameters,
    solver_status,
)

RECORDED = (Path(__file__).parent / "fixtures" / "stdout_size_limited.txt").read_text("utf-8")
BASE = ProvenanceBase("f" * 64, "0.1.0", "a" * 64)
FACTS = {"gurobi_version": "14.0.0", "platform": "Linux-test"}
OPTIMAL_LOG = (
    "Restricted license - for non-production use only\n"
    "Set parameter Threads to value 4\n"
    "Solver ended Instance_1 with status 2. Best objective found: 3.5\n"
    "Total feasible solutions found: 2\n"
)


def result(*items: dict[str, Any]) -> dict[str, Any]:
    return {
        "Solution Time (s)": 0.5,
        "Objective Value": 3.5,
        "Gap (%)": 0.0,
        "Solution Method": -1,
        "instances": list(items),
    }


def log(status: int, count: int) -> str:
    return (
        f"Solver ended Instance_1 with status {status}. Best objective found: 1\n"
        f"Total feasible solutions found: {count}\n"
    )


def test_each_goal_goes_to_the_name_the_package_gives_it() -> None:
    goals = {name: new_draft_goals(None).as_dict()[name] for name in SOLVER_GOALS}

    fields = optimizer_fields(goals, FIXED_SOLVER_INPUTS)

    assert PACKAGE_GOAL_NAMES == {
        "cost_bike_chf": "cost_bike",
        "lowest_price_chf": "P_bar",
        "ridership_weight": "ridership_weight",
        "station_balance_weight": "theta",
        "pt_fare_chf": "pt_price",
        "car_parking_fee_chf": "parking_fee",
        "max_displayed_options": "max_displayed_alternatives",
    }
    for goal, package_name in PACKAGE_GOAL_NAMES.items():
        assert fields[package_name] == goals[goal]
    assert {name: fields[name] for name in FIXED_SOLVER_INPUTS} == dict(FIXED_SOLVER_INPUTS)
    assert set(fields) == set(PACKAGE_GOAL_NAMES.values()) | set(FIXED_SOLVER_INPUTS)


def test_the_two_integer_fields_are_integers_even_when_given_as_floats() -> None:
    fields = optimizer_fields({"max_displayed_options": 10.0}, {"mult_A1": 1.0, "dep_cost": 0.0})

    assert type(fields["max_displayed_alternatives"]) is int
    assert type(fields["mult_A1"]) is int
    assert type(fields["dep_cost"]) is float


def test_the_recorded_size_limited_stdout_is_read_as_size_limited() -> None:
    assert "Model too large for size-limited license" in RECORDED
    assert "10010" not in RECORDED
    assert size_limited(RECORDED) is True
    assert solver_status(RECORDED) == 1
    assert licence_kind(RECORDED) == "limited"


def test_an_error_line_with_the_code_is_size_limited_and_another_error_is_not() -> None:
    assert size_limited("Gurobi error during optimization: Error code 10010\n") is True
    assert size_limited("Gurobi error during optimization: Out of memory\n") is False
    assert size_limited("a Gurobi error during optimization: 10010\n") is False
    assert size_limited(OPTIMAL_LOG) is False


def test_the_status_is_the_last_solver_ended_line_in_either_form() -> None:
    assert solver_status("Solver ended Instance_1 with status 2. Best objective found: 1\n") == 2
    assert solver_status("Solver ended with status 3\n") == 3
    assert solver_status("Solver ended with status 3\nSolver ended X with status 9. Best\n") == 9
    assert solver_status("nothing\n") is None


def test_the_solution_count_is_read_and_absent_means_zero() -> None:
    assert sol_count("Total feasible solutions found: 7\n") == 7
    assert sol_count("Solver ended with status 3\n") == 0


def test_the_parameters_are_typed_and_the_last_report_of_a_name_wins() -> None:
    stdout = (
        "Set parameter Threads to value 4\n"
        "Set parameter TimeLimit to value 7200.5\n"
        'Set parameter NodefileDir to value "C:\\b_b_gurobi"\n'
        "Set parameter Threads to value 2\n"
    )

    assert solver_parameters(stdout) == {
        "Threads": 2,
        "TimeLimit": 7200.5,
        "NodefileDir": '"C:\\b_b_gurobi"',
    }


def test_a_restricted_banner_means_a_limited_licence_else_full() -> None:
    assert licence_kind(OPTIMAL_LOG) == "limited"
    assert licence_kind("Academic license - for non-commercial use only\n") == "full"


def test_a_size_limited_log_wins_over_everything_else() -> None:
    read = read_solve(result(), RECORDED + log(2, 1), FACTS, BASE)

    assert isinstance(read, tuple)
    assert read[0] == SOLVER_SIZE_LIMITED


@pytest.mark.parametrize(
    ("results", "stdout", "name"),
    [
        (None, log(1, 0), "LOADED"),
        (None, "", "UNKNOWN"),
        (result(), log(3, 0), "INFEASIBLE"),
        (result(), log(4, 0), "INF_OR_UNBD"),
        (result(), log(9, 0), "TIME_LIMIT"),
        ({"Status": "PARTIAL_RECOVERY_WITH_METRICS", "SolCount": 1}, log(2, 1), "OPTIMAL"),
    ],
)
def test_a_solve_without_a_usable_solution_is_no_solution_naming_its_status(
    results: object, stdout: str, name: str
) -> None:
    read = read_solve(results, stdout, FACTS, BASE)

    assert isinstance(read, tuple)
    assert read[0] == SOLVER_NO_SOLUTION
    assert f"status {name})" in read[1]


def test_a_time_limit_with_a_solution_is_a_result_that_says_so() -> None:
    read = read_solve(result(), log(9, 3), FACTS, BASE)

    assert isinstance(read, Solve)
    assert read.quality.time_limit_reached is True
    assert (read.quality.solver_status, read.quality.solver_status_name) == (9, "TIME_LIMIT")
    assert read.quality.sol_count == 3


def test_an_optimal_solve_carries_its_quality_and_provenance() -> None:
    read = read_solve(result(), OPTIMAL_LOG, FACTS, BASE)

    assert isinstance(read, Solve)
    assert read.quality.time_limit_reached is False
    assert (read.quality.objective_value, read.quality.gap_pct) == (3.5, 0.0)
    assert (read.quality.solution_time_s, read.quality.sol_count) == (0.5, 2)
    assert read.provenance.gurobi_version == "14.0.0"
    assert read.provenance.platform == "Linux-test"
    assert read.provenance.licence_kind == "limited"
    assert read.provenance.solver_parameters == {"Threads": 4}
    assert read.provenance.package_fingerprint == "f" * 64
    assert read.provenance.demonstrator_version == "0.1.0"
    assert read.provenance.dependency_lock_sha256 == "a" * 64


def test_a_result_without_a_status_line_is_unknown_but_kept() -> None:
    read = read_solve(result(), "", FACTS, BASE)

    assert isinstance(read, Solve)
    assert (read.quality.solver_status, read.quality.solver_status_name) == (0, "UNKNOWN")


def test_the_rows_are_split_into_options_and_gammas_and_sorted() -> None:
    rows, ods = rows_from(
        [
            {"Instance OD": "2->1", "OD": "2->1", "gamma": 1.5},
            {"Instance OD": "1->2", "OD": "1->2", "gamma": 0.5},
            {
                "OD": "1->2",
                "Arc ID": "b",
                "Type": "Car",
                "nu": 0,
                "Flow (q)": 2.0,
                "Bike Price": 0.0,
                "Total Price": 3.4,
            },
            {
                "OD": "1->2",
                "Arc ID": "a",
                "Type": "PT+Bike",
                "nu": 1.0,
                "Flow (q)": 1.0,
                "Bike Price": 0.8,
                "Total Price": 2.8,
                "z value": 0.8,
                "Relaxation Difference": 0.0,
            },
        ]
    )

    assert [(od.origin_hub, od.destination_hub, od.gamma) for od in ods] == [
        ("1", "2", 0.5),
        ("2", "1", 1.5),
    ]
    assert [row.arc_id for row in rows] == ["a", "b"]
    bike, car = rows
    assert (bike.type, bike.origin_hub, bike.destination_hub) == ("PT+Bike", "1", "2")
    assert (bike.nu, bike.flow, bike.bike_price, bike.total_price) == (1.0, 1.0, 0.8, 2.8)
    assert (bike.z_value, bike.relaxation_difference) == (0.8, 0.0)
    assert car.type == "Car"
    assert (car.z_value, car.relaxation_difference) == (None, None)
    assert car.total_price == 3.4


def test_an_unknown_option_type_is_refused() -> None:
    with pytest.raises(ValueError, match="Bus"):
        rows_from([{"OD": "1->2", "Arc ID": "a", "Type": "Bus", "nu": 1, "Flow (q)": 1}])
