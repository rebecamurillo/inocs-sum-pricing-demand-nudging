import pytest

from pricing_demo.domain.failure_codes import (
    FAILURE_CODES,
    UnknownFailureCode,
    failure_reason,
)
from pricing_demo.domain.run_recovery import STAGE_ERROR


@pytest.mark.parametrize(
    ("code", "values", "reason"),
    [
        (
            "trip_planner_unreachable",
            {"url": "http://otp:8080"},
            "the trip planner is not reachable at http://otp:8080",
        ),
        (
            "no_public_transport",
            {"d": "2025-03-10"},
            "the trip planner found no public transport route; "
            "the routing date 2025-03-10 may be outside its timetable",
        ),
        (
            "instance_unbalanced",
            {},
            "the instance still has unbalanced bike options after the package's fix",
        ),
        (
            "solver_size_limited",
            {},
            "the Gurobi licence is size-limited and cannot solve this instance",
        ),
        (
            "solver_no_solution",
            {"name": "INFEASIBLE"},
            "the solver found no solution (status INFEASIBLE)",
        ),
        (
            "simulation_check_failed",
            {"check": "travellers add up"},
            "the traveller simulation broke its check: travellers add up",
        ),
        (
            "stage_error",
            {"exception_type": "ValueError", "message": "bad"},
            "ValueError: bad",
        ),
        (
            "killed",
            {"n": 9},
            "the process was stopped by the system (signal 9); the machine may be out of memory",
        ),
    ],
)
def test_each_code_has_the_reason_of_the_architecture(
    code: str, values: dict[str, object], reason: str
) -> None:
    assert failure_reason(code, **values) == reason


def test_the_codes_are_the_eight_a_step_can_fail_with() -> None:
    assert len(FAILURE_CODES) == 8
    assert STAGE_ERROR in FAILURE_CODES


def test_a_code_that_is_not_one_of_them_raises() -> None:
    with pytest.raises(UnknownFailureCode):
        failure_reason("interrupted")
