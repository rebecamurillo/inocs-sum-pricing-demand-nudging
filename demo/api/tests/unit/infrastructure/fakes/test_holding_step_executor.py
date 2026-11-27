import threading

from pricing_demo.domain.runs import RunKind
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.hold import HoldingStepExecutor
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from tests.support.runs import T0, RecordingExecutor, make_run


def _holding(
    hold_at: str | None,
) -> tuple[HoldingStepExecutor, InMemoryFakeSettings, FakeWaiter, list[str]]:
    log: list[str] = []
    settings = InMemoryFakeSettings()
    settings.set_pricing_model({"hold_at": hold_at} if hold_at else None)
    waiter = FakeWaiter(FixedClock(T0))
    return HoldingStepExecutor(RecordingExecutor(log), settings, waiter), settings, waiter, log


def test_the_simulation_waits_for_its_run_to_be_released_then_runs() -> None:
    executor, settings, waiter, log = _holding("traveller_simulation")
    run = make_run("run-1", kind=RunKind.SIMULATION)

    def release_on_the_third_look(_: object) -> None:
        if waiter.calls == 3:
            settings.release_run("run-1")

    waiter.on_wait = release_on_the_third_look

    outcome = executor.execute(run, run.steps[0], threading.Event())

    assert waiter.calls == 3
    assert log == ["run-1:traveller_simulation"]
    assert not outcome.stopped


def test_a_stop_while_held_returns_stopped_without_running() -> None:
    executor, _, waiter, log = _holding("traveller_simulation")
    run = make_run("run-1", kind=RunKind.SIMULATION)
    stop = threading.Event()
    waiter.on_wait = lambda _: stop.set()

    outcome = executor.execute(run, run.steps[0], stop)

    assert outcome.stopped
    assert log == []


def test_any_other_hold_or_none_delegates_at_once() -> None:
    for hold_at in (None, "pricing_model"):
        executor, _, waiter, log = _holding(hold_at)
        run = make_run("run-1", kind=RunKind.SIMULATION)

        outcome = executor.execute(run, run.steps[0], threading.Event())

        assert waiter.calls == 0
        assert log == ["run-1:traveller_simulation"]
        assert not outcome.stopped
