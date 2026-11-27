"""How a fake step is held: it waits until its run is released or the worker asks it to stop."""

import threading

from pricing_demo.application.ports.step_executor import StepExecutor, StepOutcome, StopSignal
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.domain.runs import Run, RunStep, StepName
from pricing_demo.infrastructure.fakes.component_probe import FakeSettingsSource

# How often a held step looks for its release.
HOLD_POLL_S = 0.05


def hold_until_released(
    settings: FakeSettingsSource, waiter: Waiter, run_id: str, stop: StopSignal
) -> bool:
    """Wait until the run is released; False when the step was stopped first."""
    never = threading.Event()
    while not stop.is_set():
        released = settings.read().get("released_runs")
        if isinstance(released, list) and run_id in released:
            return True
        waiter.wait(HOLD_POLL_S, never)
    return False


class HoldingStepExecutor:
    """The traveller simulation's executor with the test hold of step 5b: while the settings
    hold `traveller_simulation`, the step waits for its run's release. Wired in fake mode only;
    the real worker runs the inner executor."""

    def __init__(self, inner: StepExecutor, settings: FakeSettingsSource, waiter: Waiter) -> None:
        self._inner = inner
        self._settings = settings
        self._waiter = waiter

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        config = self._settings.read().get("pricing_model")
        held = (
            isinstance(config, dict)
            and config.get("hold_at") == StepName.TRAVELLER_SIMULATION.value
        )
        if held and not hold_until_released(self._settings, self._waiter, run.id, stop):
            return StepOutcome.stopped_on_signal()
        return self._inner.execute(run, step, stop)
