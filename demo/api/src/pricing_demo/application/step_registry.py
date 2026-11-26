from pricing_demo.application.ports.step_executor import StepExecutor
from pricing_demo.domain.runs import StepName


class StepRegistry:
    """The executor of each step. The worker's composition root fills it."""

    def __init__(self) -> None:
        self._executors: dict[StepName, StepExecutor] = {}

    def register(self, step: StepName, executor: StepExecutor) -> None:
        self._executors[step] = executor

    def executor_for(self, step: StepName) -> StepExecutor | None:
        return self._executors.get(step)
