import threading
from pathlib import Path

from pricing_demo.application.ports.pricing_solver import SolveRequest
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from tests.support.city_files import FakeCity
from tests.support.runs import T0


def _solver(tmp_path: Path) -> tuple[FakePricingSolver, InMemoryFakeSettings, FakeWaiter, Path]:
    FakeCity(tmp_path)
    settings = InMemoryFakeSettings()
    settings.set_pricing_model({"hold_at": "pricing_model"})
    waiter = FakeWaiter(FixedClock(T0))
    return FakePricingSolver(settings, waiter), settings, waiter, tmp_path


def _request(folder: Path) -> SolveRequest:
    goals = new_draft_goals(None).as_dict()
    return SolveRequest(
        "run-1",
        folder,
        {key: goals[key] for key in SOLVER_GOALS},
        dict(FIXED_SOLVER_INPUTS),
        "fingerprint",
    )


def test_the_solve_waits_for_its_run_to_be_released(tmp_path: Path) -> None:
    solver, settings, waiter, folder = _solver(tmp_path)

    def release_on_the_third_look(_: object) -> None:
        if waiter.calls == 3:
            settings.release_run("run-1")

    waiter.on_wait = release_on_the_third_look

    outcome = solver.solve(_request(folder), threading.Event())

    assert waiter.calls == 3
    assert outcome.solve is not None
    assert not outcome.stopped


def test_a_stop_while_held_returns_stopped(tmp_path: Path) -> None:
    solver, _, waiter, folder = _solver(tmp_path)
    stop = threading.Event()
    waiter.on_wait = lambda _: stop.set()

    outcome = solver.solve(_request(folder), stop)

    assert outcome.stopped
    assert outcome.solve is None


def test_without_a_hold_the_solve_does_not_wait(tmp_path: Path) -> None:
    solver, settings, waiter, folder = _solver(tmp_path)
    settings.set_pricing_model(None)

    outcome = solver.solve(_request(folder), threading.Event())

    assert waiter.calls == 0
    assert outcome.solve is not None


def test_a_failure_set_while_the_step_is_held_applies_when_it_is_released(tmp_path: Path) -> None:
    solver, settings, waiter, folder = _solver(tmp_path)

    def fail_then_release(_: object) -> None:
        settings.set_pricing_model(
            {"fail_at": {"step": "pricing_model", "code": "solver_no_solution"}}
        )
        settings.release_run("run-1")

    waiter.on_wait = fail_then_release

    outcome = solver.solve(_request(folder), threading.Event())

    assert outcome.failure_code == "solver_no_solution"
