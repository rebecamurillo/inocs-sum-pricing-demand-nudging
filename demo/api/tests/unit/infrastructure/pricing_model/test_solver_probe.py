from pricing_demo.domain.system_status import ComponentName, ComponentState
from pricing_demo.infrastructure.pricing_model.solver_probe import (
    PROBE_VARIABLES,
    SolverProbe,
    solver_status_from,
)


class RecordedGurobiError(Exception):
    """The shape of `gurobipy.GurobiError`: a message and an `errno`."""

    def __init__(self, message: str, errno: int) -> None:
        super().__init__(message)
        self.errno = errno


SIZE_LIMIT = RecordedGurobiError(
    "Model too large for size-limited license; visit https://gurobi.com/unrestricted", 10010
)


def test_the_probe_model_is_one_variable_over_the_size_limited_licence() -> None:
    assert PROBE_VARIABLES == 2001


def test_a_solved_model_reads_available() -> None:
    status = solver_status_from(None)

    assert status.name is ComponentName.SOLVER
    assert status.state is ComponentState.AVAILABLE
    assert status.reason is None


def test_the_size_limit_error_reads_limited_with_its_message() -> None:
    status = solver_status_from(SIZE_LIMIT)

    assert status.state is ComponentState.LIMITED
    assert status.reason is not None
    assert "Size-limited Gurobi licence" in status.reason
    assert "2001" in status.reason
    assert "Model too large" in status.reason


def test_an_error_without_the_size_limit_errno_reads_unavailable() -> None:
    status = solver_status_from(RecordedGurobiError("No Gurobi license found", 10009))

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason is not None
    assert status.reason.startswith("Gurobi did not start: ")
    assert "No Gurobi license found" in status.reason


def test_an_error_without_an_errno_reads_unavailable() -> None:
    status = solver_status_from(OSError("libgurobi is missing"))

    assert status.state is ComponentState.UNAVAILABLE
    assert (status.reason or "").startswith("Gurobi did not start: ")


def test_the_probe_reads_available_when_the_solve_returns() -> None:
    assert SolverProbe(solve=lambda: None).check().state is ComponentState.AVAILABLE


def test_the_probe_reads_limited_when_the_solve_raises_the_size_limit_error() -> None:
    def solve() -> None:
        raise SIZE_LIMIT

    assert SolverProbe(solve=solve).check().state is ComponentState.LIMITED


def test_the_probe_reads_unavailable_when_no_environment_starts() -> None:
    def solve() -> None:
        raise RuntimeError("no environment")

    status = SolverProbe(solve=solve).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == "Gurobi did not start: no environment"
