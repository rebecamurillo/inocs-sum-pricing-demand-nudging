import threading
from pathlib import Path

import pytest

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.domain.failure_codes import (
    SOLVER_NO_SOLUTION,
    SOLVER_SIZE_LIMITED,
)
from pricing_demo.domain.pricing_keys import KEPT_SOLVE_REASON
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import RunState, StepName, StepState
from pricing_demo.domain.solves import Solve
from pricing_demo.domain.system_status import ComponentName, ComponentState
from pricing_demo.infrastructure.fakes.solves import InMemorySolves
from tests.support.pricing_runs import PERIOD, PricingRig


@pytest.fixture
def rig(tmp_path: Path) -> PricingRig:
    return PricingRig(tmp_path)


def solve_key(rig: PricingRig, version: str) -> str:
    found = rig.rig.solves.solve_key_of(version, PERIOD)
    assert found is not None
    return found


def test_a_first_run_solves_stores_the_solve_and_writes_its_key_on_the_step(
    rig: PricingRig,
) -> None:
    version = rig.version()

    run = rig.run(version)

    first = run.steps[0]
    assert first.state is StepState.DONE
    assert first.input_key == solve_key(rig, version)
    assert first.counts["solver_status_name"] == "OPTIMAL"
    assert first.counts["options_offered"] > 0
    assert first.counts["hub_pairs_priced"] > 0
    assert rig.rig.solves.is_stored(solve_key(rig, version))
    assert rig.rig.solves.rows(solve_key(rig, version))
    stored = rig.rig.artifacts.get(solve_key(rig, version))
    assert stored is not None
    assert stored.step is StepName.PRICING_MODEL
    assert stored.run_id == run.id
    assert [item.name for item in stored.files] == ["solution.json"]


def test_the_solve_provenance_says_it_is_fake(rig: PricingRig) -> None:
    version = rig.version()
    rig.run(version)

    record = rig.rig.solves.solve_of(version, PERIOD)

    assert record is not None
    assert record.provenance.gurobi_version == "fake"
    assert record.provenance.licence_kind == "full"


def test_the_working_directory_goes_when_the_step_succeeds(rig: PricingRig, tmp_path: Path) -> None:
    run = rig.run(rig.version())

    assert not (tmp_path / "runs" / run.id / "pricing_model").exists()


def test_a_version_that_differs_only_in_its_flat_price_keeps_the_step_and_shares_the_solve(
    rig: PricingRig,
) -> None:
    first = rig.version()
    second = rig.version(flat_price_per_ride_chf=2.5)
    rig.run(first)

    run = rig.run(second)

    step = run.steps[0]
    assert step.state is StepState.KEPT
    assert step.reason == KEPT_SOLVE_REASON
    assert step.input_key == solve_key(rig, first)
    assert solve_key(rig, second) == solve_key(rig, first)
    assert step.counts["options_offered"] > 0
    pricing_artifacts = [
        item for item in rig.rig.artifacts.unreferenced() if item.step is StepName.PRICING_MODEL
    ]
    assert pricing_artifacts == []
    own = rig.rig.solves.solve_of(second, PERIOD)
    assert own is not None
    assert own.created_at >= rig.rig.solves.solve_of(first, PERIOD).created_at  # type: ignore[union-attr]


def test_goals_that_differ_in_a_solver_input_solve_again(rig: PricingRig) -> None:
    first = rig.version()
    second = rig.version(cost_bike_chf=1.2)
    rig.run(first)

    run = rig.run(second)

    assert run.steps[0].state is StepState.DONE
    assert solve_key(rig, second) != solve_key(rig, first)


@pytest.mark.parametrize(
    ("state", "reason", "code"),
    [
        (ComponentState.LIMITED, "Size-limited Gurobi licence.", SOLVER_SIZE_LIMITED),
        (ComponentState.UNAVAILABLE, "Gurobi did not start: no licence.", STAGE_ERROR),
    ],
)
def test_the_solver_is_probed_again_before_the_step_and_a_solver_that_cannot_solve_fails_it(
    rig: PricingRig, state: ComponentState, reason: str, code: str
) -> None:
    rig.settings.set_component("solver", state.value, reason)
    version = rig.version()

    run = rig.run(version)

    assert run.state is RunState.FAILED
    assert run.failure is not None
    assert (run.failure.step, run.failure.code) == ("pricing_model", code)
    if state is ComponentState.UNAVAILABLE:
        assert reason in run.failure.reason
    assert run.steps[1].state is StepState.PENDING
    assert rig.rig.solves.solve_key_of(version, PERIOD) is None
    report = rig.reports.read().reports
    assert [(item.status.name, item.status.state) for item in report] == [
        (ComponentName.SOLVER, state)
    ]


@pytest.mark.parametrize("code", [SOLVER_SIZE_LIMITED, SOLVER_NO_SOLUTION, STAGE_ERROR])
def test_a_failure_of_the_solver_fails_the_step_with_its_code_and_stores_nothing(
    rig: PricingRig, tmp_path: Path, code: str
) -> None:
    rig.settings.set_pricing_model({"fail_at": {"step": "pricing_model", "code": code}})
    version = rig.version()

    run = rig.run(version)

    assert (run.state, run.steps[0].state) == (RunState.FAILED, StepState.FAILED)
    assert run.failure is not None
    assert (run.failure.step, run.failure.code) == ("pricing_model", code)
    assert run.steps[0].reason == run.failure.reason
    assert rig.rig.solves.solve_key_of(version, PERIOD) is None
    assert rig.rig.artifacts.stored_keys([run.steps[0].input_key or ""]) == set()
    # The working directory stays until the step succeeds or the run is deleted.
    assert (tmp_path / "runs" / run.id / "pricing_model" / "Instance_1.json").exists()


def test_run_again_after_a_failure_solves_and_the_run_succeeds(rig: PricingRig) -> None:
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "pricing_model", "code": SOLVER_NO_SOLUTION}}
    )
    version = rig.version()
    failed = rig.run(version)
    rig.settings.set_pricing_model(None)

    again = rig.run(version)

    assert (failed.state, again.state) == (RunState.FAILED, RunState.SUCCEEDED)
    assert [item.state for item in again.steps] == [StepState.DONE, StepState.DONE]


def test_a_stopped_step_writes_nothing_and_leaves_no_working_directory(
    rig: PricingRig, tmp_path: Path
) -> None:
    version = rig.version()
    queued = rig.rig.run_pricing.execute(version)
    stop = threading.Event()
    stop.set()

    outcome = rig.model.execute(queued, queued.steps[0], stop)

    assert outcome.stopped is True
    assert rig.rig.solves.solve_key_of(version, PERIOD) is None
    assert not (tmp_path / "runs" / queued.id / "pricing_model").exists()
    assert not (tmp_path / "artifacts" / "pricing_model").exists()


class FailingStore(InMemorySolves):
    def store(self, artifact: Artifact, solve: Solve, *rest: object) -> None:
        raise RuntimeError("the database went away")


def test_a_failed_store_fails_the_step_as_a_stage_error(rig: PricingRig) -> None:
    rig.model._solves = FailingStore(rig.rig.artifacts)
    version = rig.version()

    run = rig.run(version)

    assert run.failure is not None
    assert (run.failure.code, run.failure.reason) == (
        STAGE_ERROR,
        "RuntimeError: the database went away",
    )
    assert rig.rig.solves.solve_key_of(version, PERIOD) is None


def test_a_solve_no_version_points_to_any_more_is_solved_again_not_kept(rig: PricingRig) -> None:
    first, second = rig.version(), rig.version(flat_price_per_ride_chf=2.5)
    rig.run(first)
    rig.rig.pricing.delete(first)

    run = rig.run(second)

    assert run.steps[0].state is StepState.DONE
    assert run.state is RunState.SUCCEEDED


def test_a_version_of_an_instance_that_was_never_built_fails_the_step_with_its_reason(
    rig: PricingRig,
) -> None:
    goals = new_draft_goals(None)
    other = rig.rig.pricing.create_draft(
        "other.v1", None, goals, "other.v1.mon-08", None, rig.rig.clock.now()
    ).id
    queued = rig.rig.run_pricing.execute(other)

    outcome = rig.model.execute(queued, queued.steps[0], threading.Event())

    assert outcome.failure_code == STAGE_ERROR
    assert "no stored build" in (outcome.failure_reason or "")
    assert rig.model.keep(queued, queued.steps[0]) is False
