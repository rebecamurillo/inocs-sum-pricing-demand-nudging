from pricing_demo.domain.system_status import ComponentName, ComponentStatus


class SolverProbe:
    """A Gurobi environment starts, which needs a licence it accepts."""

    component = ComponentName.SOLVER

    def check(self) -> ComponentStatus:
        try:
            import gurobipy

            with gurobipy.Env(empty=True) as environment:
                environment.setParam("OutputFlag", 0)
                environment.start()
        except Exception as error:
            return ComponentStatus.unavailable(self.component, f"Gurobi did not start: {error}")
        return ComponentStatus.ready(self.component)
