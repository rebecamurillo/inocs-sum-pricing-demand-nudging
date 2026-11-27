"""How a fake step is held: it waits until its run is released or the worker asks it to stop."""

import threading

from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.application.ports.waiter import Waiter
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
