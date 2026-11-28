from collections.abc import Callable

from pricing_demo.domain.system_status import ComponentName, ComponentStatus

# The size-limited (restricted) Gurobi licence refuses a model above 2000 variables; a full
# licence solves this one. The probe tells the two apart by that, not by reading the licence.
PROBE_VARIABLES = 2001
SIZE_LIMIT_ERRNO = 10010


def solver_status_from(error: BaseException | None) -> ComponentStatus:
    """What the outcome of solving the probe model says about the solver."""
    if error is None:
        return ComponentStatus.ready(ComponentName.SOLVER)
    if getattr(error, "errno", None) == SIZE_LIMIT_ERRNO:
        return ComponentStatus.limited(
            ComponentName.SOLVER,
            f"Size-limited Gurobi licence: a model of {PROBE_VARIABLES} variables "
            f"is refused ({error}).",
        )
    return ComponentStatus.unavailable(ComponentName.SOLVER, f"Gurobi did not start: {error}")


def solve_probe_model() -> None:
    """Start a Gurobi environment and optimise a model of `PROBE_VARIABLES` continuous
    variables with output off."""
    import gurobipy

    with gurobipy.Env(empty=True) as environment:
        environment.setParam("OutputFlag", 0)
        environment.start()
        with gurobipy.Model(env=environment) as model:
            model.addVars(PROBE_VARIABLES, vtype=gurobipy.GRB.CONTINUOUS, name="x")
            model.optimize()


class SolverProbe:
    """Gurobi starts and solves a model larger than the size-limited licence allows."""

    component = ComponentName.SOLVER

    def __init__(self, solve: Callable[[], None] = solve_probe_model) -> None:
        self._solve = solve

    def check(self) -> ComponentStatus:
        try:
            self._solve()
        except Exception as error:
            return solver_status_from(error)
        return solver_status_from(None)
