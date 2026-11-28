from pricing_demo.application.ports.step_executor import StepExecutor, StepKeeper
from pricing_demo.domain.runs import StepName


class StepRegistry:
    """The executor of each step, and the keeper of those that can be kept. The worker's
    composition root fills it."""

    def __init__(self) -> None:
        self._executors: dict[StepName, StepExecutor] = {}
        self._keepers: dict[StepName, StepKeeper] = {}

    def register(
        self, step: StepName, executor: StepExecutor, keeper: StepKeeper | None = None
    ) -> None:
        self._executors[step] = executor
        if keeper is not None:
            self._keepers[step] = keeper

    def executor_for(self, step: StepName) -> StepExecutor | None:
        return self._executors.get(step)

    def keeper_for(self, step: StepName) -> StepKeeper | None:
        return self._keepers.get(step)
