"""The failure codes of a step and the readable reason of each (ARCHITECTURE.md § 4.7).

`interrupted` lives in `run_recovery` and `cancelled` in the run's own state; the others are
here. A reason is the `{reason}` of the screen's "{Step} failed: {reason}.".
"""

from collections.abc import Mapping

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.run_recovery import STAGE_ERROR

TRIP_PLANNER_UNREACHABLE = "trip_planner_unreachable"
NO_PUBLIC_TRANSPORT = "no_public_transport"
TIMETABLE_MISMATCH = "timetable_mismatch"
INSTANCE_UNBALANCED = "instance_unbalanced"
SOLVER_SIZE_LIMITED = "solver_size_limited"
SOLVER_NO_SOLUTION = "solver_no_solution"
SIMULATION_CHECK_FAILED = "simulation_check_failed"
KILLED = "killed"

# The pattern of each code; `{name}` marks a value the failure supplies.
REASON_PATTERNS: Mapping[str, str] = {
    TRIP_PLANNER_UNREACHABLE: "the trip planner is not reachable at {url}",
    NO_PUBLIC_TRANSPORT: (
        "the trip planner found no public transport route; "
        "the routing date {d} may be outside its timetable"
    ),
    TIMETABLE_MISMATCH: "the trip planner's timetable is not the city data's timetable",
    INSTANCE_UNBALANCED: ("the instance still has unbalanced bike options after the package's fix"),
    SOLVER_SIZE_LIMITED: "the Gurobi licence is size-limited and cannot solve this instance",
    SOLVER_NO_SOLUTION: "the solver found no solution (status {name})",
    SIMULATION_CHECK_FAILED: "the traveller simulation broke its check: {check}",
    STAGE_ERROR: "{exception_type}: {message}",
    KILLED: (
        "the process was stopped by the system (signal {n}); the machine may be out of memory"
    ),
}

FAILURE_CODES = tuple(REASON_PATTERNS)


class UnknownFailureCode(DomainError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"{code} is not a failure code of a step.")


def failure_reason(code: str, **values: object) -> str:
    """The reason of `code` with its values filled in; a value the pattern names and the call
    left out raises `KeyError`."""
    pattern = REASON_PATTERNS.get(code)
    if pattern is None:
        raise UnknownFailureCode(code)
    return pattern.format(**values)
