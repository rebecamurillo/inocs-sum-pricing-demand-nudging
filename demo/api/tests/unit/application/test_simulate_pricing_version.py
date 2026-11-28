from dataclasses import replace

import pytest

from pricing_demo.domain.builds import ComponentUnavailable, RunActive
from pricing_demo.domain.pricing_versions import (
    NoResult,
    PricingVersionNotFound,
    SimulationCurrent,
    new_draft_goals,
)
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, SubjectType
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus
from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule
from tests.support.builds import MemoryBuilds, unavailable
from tests.support.pricing_versions import sealed_pricing_version
from tests.support.runs import T0, later, make_run
from tests.support.simulations import simulate_under

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"
V1 = BalancedScore()
V2 = BalancedScore(0.6, 0.4, rule_version=2)


def live(status: SystemStatus, rule: BalancedScore | None) -> SystemStatus:
    return replace(status, simulation_rule=None if rule is None else SimulationRule.of(rule))


def rig_with_result(current: BalancedScore | None = V2) -> tuple[MemoryBuilds, str]:
    """A sealed version whose pricing run succeeded, simulated under rule v1."""
    rig = MemoryBuilds()
    version = rig.pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id
    sealed_pricing_version(rig, version, RunState.SUCCEEDED)
    simulate_under(rig.simulations, version, PERIOD, V1)
    rig.status.value = live(rig.status.value, current)
    return rig, version


def stored(rig: MemoryBuilds, run_id: str) -> Run:
    run = rig.runs.get(run_id)
    assert run is not None
    return run


def test_a_simulation_run_with_the_single_step_is_queued() -> None:
    rig, version = rig_with_result()

    run = rig.simulate.execute(version)

    found = stored(rig, run.id)
    assert (found.kind, found.state, found.queued_at) == (RunKind.SIMULATION, RunState.QUEUED, T0)
    assert (found.subject.type, found.subject.id) == (SubjectType.PRICING_VERSION, version)
    assert [(item.position, item.step, item.period) for item in found.steps] == [
        (1, StepName.TRAVELLER_SIMULATION, PERIOD)
    ]


def test_a_version_simulated_with_one_scheme_only_under_the_current_rule_is_queued() -> None:
    rig, version = rig_with_result()
    simulate_under(rig.simulations, version, PERIOD, V2, ("flat",))

    run = rig.simulate.execute(version)

    assert stored(rig, run.id).state is RunState.QUEUED


def test_an_unknown_version_is_refused() -> None:
    rig = MemoryBuilds()

    with pytest.raises(PricingVersionNotFound):
        rig.simulate.execute("geneva-3km.v1.Q")


@pytest.mark.parametrize("kind", [RunKind.PRICING, RunKind.SIMULATION])
@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING])
def test_a_version_with_an_active_run_of_any_kind_is_refused_with_that_run(
    kind: RunKind, state: RunState
) -> None:
    rig, version = rig_with_result()
    rig.runs.add(
        make_run("r-active", kind=kind, subject_id=version, state=state, queued_at=later(5))
    )

    with pytest.raises(RunActive) as refusal:
        rig.simulate.execute(version)

    assert refusal.value.run_id == "r-active"
    assert len(rig.runs.list_by_states(list(RunState))) == 2


@pytest.mark.parametrize(
    "state", [RunState.FAILED, RunState.CANCELLED, RunState.QUEUED, RunState.RUNNING]
)
def test_a_version_whose_pricing_run_did_not_succeed_has_no_result(state: RunState) -> None:
    rig = MemoryBuilds()
    version = rig.pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id
    sealed_pricing_version(rig, version, state)

    with pytest.raises((NoResult, RunActive)) as refusal:
        rig.simulate.execute(version)

    assert isinstance(refusal.value, RunActive) is (state in (RunState.QUEUED, RunState.RUNNING))


def test_a_draft_has_no_result() -> None:
    rig = MemoryBuilds()
    version = rig.pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id

    with pytest.raises(NoResult):
        rig.simulate.execute(version)

    assert rig.runs.list_by_states(list(RunState)) == []


def test_a_simulation_run_that_succeeded_after_the_pricing_run_does_not_hide_the_result() -> None:
    rig, version = rig_with_result()
    rig.runs.add(
        make_run(
            "r-sim",
            kind=RunKind.SIMULATION,
            subject_id=version,
            state=RunState.FAILED,
            queued_at=later(9),
        )
    )

    assert stored(rig, rig.simulate.execute(version).id).state is RunState.QUEUED


@pytest.mark.parametrize("down", [ComponentName.RUNNER, ComponentName.STORAGE])
def test_a_missing_worker_or_storage_is_refused_with_its_reason(down: ComponentName) -> None:
    rig, version = rig_with_result()
    rig.status.value = unavailable(down)

    with pytest.raises(ComponentUnavailable) as refusal:
        rig.simulate.execute(version)

    assert [item.component for item in refusal.value.reasons] == [down]
    assert len(rig.runs.list_by_states(list(RunState))) == 1


def test_neither_the_solver_nor_the_trip_planner_refuses_a_simulation() -> None:
    rig, version = rig_with_result()
    rig.status.value = live(
        unavailable(ComponentName.SOLVER, ComponentName.TRIP_PLANNER, ComponentName.PACKAGE), V2
    )

    run = rig.simulate.execute(version)

    assert stored(rig, run.id).state is RunState.QUEUED


def test_both_schemes_already_simulated_with_the_current_rule_are_refused() -> None:
    rig, version = rig_with_result()
    simulate_under(rig.simulations, version, PERIOD, V2)

    with pytest.raises(SimulationCurrent):
        rig.simulate.execute(version)

    assert len(rig.runs.list_by_states(list(RunState))) == 1


def test_the_rule_is_the_whole_triple_not_the_version_alone() -> None:
    rig, version = rig_with_result(current=BalancedScore(0.7, 0.3, rule_version=2))
    simulate_under(rig.simulations, version, PERIOD, V2)

    assert stored(rig, rig.simulate.execute(version).id).state is RunState.QUEUED


def test_the_refusals_come_in_order() -> None:
    rig, version = rig_with_result()
    simulate_under(rig.simulations, version, PERIOD, V2)
    rig.status.value = unavailable(ComponentName.RUNNER)
    rig.runs.add(make_run("r-active", kind=RunKind.SIMULATION, subject_id=version))

    with pytest.raises(RunActive):
        rig.simulate.execute(version)

    rig.runs.update("r-active", lambda run: replace(run, state=RunState.FAILED))
    with pytest.raises(ComponentUnavailable):
        rig.simulate.execute(version)

    rig.status.value = live(rig.status.value, V2)
    rig.status.value = SystemStatus.of(
        [ComponentStatus.ready(name) for name in ComponentName], SimulationRule.of(V2)
    )
    with pytest.raises(SimulationCurrent):
        rig.simulate.execute(version)
