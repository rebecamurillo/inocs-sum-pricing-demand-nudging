from dataclasses import replace
from datetime import datetime

import pytest

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.domain.build_plan import BUILD_STEPS
from pricing_demo.domain.builds import AlreadyBuilt, ComponentUnavailable, RuleBroken, RunActive
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, StepState, SubjectType
from pricing_demo.domain.system_status import ComponentName
from tests.support.builds import MemoryBuilds, unavailable
from tests.support.runs import T0, later


def stored_run(rig: MemoryBuilds, run_id: str) -> Run:
    run = rig.runs.get(run_id)
    assert run is not None
    return run


def finish(rig: MemoryBuilds, run_id: str, state: RunState) -> None:
    rig.runs.update(run_id, lambda run: replace(run, state=state, finished_at=later(5)))


def test_an_unknown_version_is_refused() -> None:
    rig = MemoryBuilds()

    with pytest.raises(InstanceVersionNotFound):
        rig.build.execute("nope.v1")


def test_a_draft_that_breaks_a_rule_is_refused_with_the_rules_and_stays_a_draft() -> None:
    rig = MemoryBuilds()
    rig.add_draft(("min_od_distance_m", 500.0))

    with pytest.raises(RuleBroken) as refusal:
        rig.build.execute("geneva-3km.v1")

    assert [item.rule for item in refusal.value.failures] == ["min_trip_distance_above_grouping"]
    assert [value.value for value in refusal.value.failures[0].values] == [500, 500]
    assert rig.instances.get_version("geneva-3km.v1").status == "draft"  # type: ignore[union-attr]
    assert rig.runs.list_by_states(list(RunState)) == []


def test_a_valid_draft_is_sealed_and_a_build_run_with_four_steps_is_queued() -> None:
    rig = MemoryBuilds()
    rig.add_draft()

    run = rig.build.execute("geneva-3km.v1")

    stored = stored_run(rig, run.id)
    assert (stored.kind, stored.state, stored.queued_at) == (RunKind.BUILD, RunState.QUEUED, T0)
    assert (stored.subject.type, stored.subject.id) == (
        SubjectType.INSTANCE_VERSION,
        "geneva-3km.v1",
    )
    assert [(item.position, item.step) for item in stored.steps] == list(
        enumerate(BUILD_STEPS, start=1)
    )
    period = "geneva-3km.v1.mon-08"
    assert [item.period for item in stored.steps] == [None, None, period, period]
    assert all(item.state is StepState.PENDING for item in stored.steps)
    version = rig.instances.get_version("geneva-3km.v1")
    assert version is not None
    assert (version.status, version.sealed_at) == ("sealed", T0)


def test_each_step_stores_the_input_key_of_the_plan() -> None:
    rig = MemoryBuilds()
    draft = rig.add_draft()

    run = rig.build.execute("geneva-3km.v1")

    plan = rig.planning.plan(draft)
    assert [item.input_key for item in run.steps] == [item.input_key for item in plan.steps]
    assert all(len(item.input_key or "") == 64 for item in run.steps)


def test_the_run_gets_the_next_identifier() -> None:
    rig = MemoryBuilds()
    rig.add_draft()

    assert rig.build.execute("geneva-3km.v1").id == "run-1"


def test_a_version_with_a_queued_run_is_refused_with_the_run() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    first = rig.build.execute("geneva-3km.v1")

    with pytest.raises(RunActive) as refusal:
        rig.build.execute("geneva-3km.v1")

    assert refusal.value.run_id == first.id
    assert len(rig.runs.list_by_states(list(RunState))) == 1


def test_a_version_with_a_running_run_is_refused() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    first = rig.build.execute("geneva-3km.v1")
    finish(rig, first.id, RunState.RUNNING)

    with pytest.raises(RunActive):
        rig.build.execute("geneva-3km.v1")


def test_a_version_whose_latest_build_succeeded_is_already_built() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    first = rig.build.execute("geneva-3km.v1")
    finish(rig, first.id, RunState.SUCCEEDED)

    with pytest.raises(AlreadyBuilt):
        rig.build.execute("geneva-3km.v1")


@pytest.mark.parametrize("state", [RunState.FAILED, RunState.CANCELLED])
def test_a_sealed_version_whose_build_failed_or_was_cancelled_is_queued_again_without_sealing(
    state: RunState,
) -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    first = rig.build.execute("geneva-3km.v1")
    finish(rig, first.id, state)
    rig.clock.set(later(60))

    second = rig.build.execute("geneva-3km.v1")

    assert second.id != first.id
    assert stored_run(rig, second.id).state is RunState.QUEUED
    version = rig.instances.get_version("geneva-3km.v1")
    assert version is not None
    assert version.sealed_at == T0


def test_a_sealed_version_with_no_run_is_queued_without_sealing_again() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    rig.instances.seal("geneva-3km.v1", later(1))

    rig.build.execute("geneva-3km.v1")

    version = rig.instances.get_version("geneva-3km.v1")
    assert version is not None
    assert version.sealed_at == later(1)


def test_a_missing_component_refuses_the_build_with_its_reason_and_seals_nothing() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    rig.status.value = unavailable(ComponentName.RUNNER, ComponentName.TRIP_PLANNER)

    with pytest.raises(ComponentUnavailable) as refusal:
        rig.build.execute("geneva-3km.v1")

    assert [(item.component, item.reason) for item in refusal.value.reasons] == [
        (ComponentName.RUNNER, "runner is down."),
        (ComponentName.TRIP_PLANNER, "trip_planner is down."),
    ]
    assert rig.instances.get_version("geneva-3km.v1").status == "draft"  # type: ignore[union-attr]
    assert rig.runs.list_by_states(list(RunState)) == []


def test_a_package_that_has_not_been_reported_refuses_the_build() -> None:
    rig = MemoryBuilds(fingerprint=None)
    rig.add_draft()

    with pytest.raises(ComponentUnavailable) as refusal:
        rig.build.execute("geneva-3km.v1")

    assert [item.component for item in refusal.value.reasons] == [ComponentName.PACKAGE]


def test_a_plan_that_keeps_the_routes_needs_no_trip_planner() -> None:
    rig = MemoryBuilds()
    draft = rig.add_draft()
    plan = rig.planning.plan(draft)
    for item in plan.steps[:3]:
        assert item.input_key is not None
        assert item.inputs is not None
        rig.artifacts.add(Artifact(item.input_key, item.step, item.inputs, (), "a", "f" * 64, T0))
    rig.status.value = unavailable(ComponentName.TRIP_PLANNER)

    run = rig.build.execute("geneva-3km.v1")

    assert stored_run(rig, run.id).state is RunState.QUEUED
    # The steps are queued pending: the worker decides `kept` from the stored artefacts.
    assert [item.state for item in run.steps] == [StepState.PENDING] * 4


def test_a_broken_rule_is_reported_before_a_missing_component() -> None:
    rig = MemoryBuilds()
    rig.add_draft(("min_od_distance_m", 500.0))
    rig.status.value = unavailable(ComponentName.RUNNER)

    with pytest.raises(RuleBroken):
        rig.build.execute("geneva-3km.v1")


def test_a_run_in_progress_is_reported_before_a_missing_component() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    rig.build.execute("geneva-3km.v1")
    rig.status.value = unavailable(ComponentName.RUNNER)

    with pytest.raises(RunActive):
        rig.build.execute("geneva-3km.v1")


def test_a_finished_build_is_reported_before_a_missing_component() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    first = rig.build.execute("geneva-3km.v1")
    finish(rig, first.id, RunState.SUCCEEDED)
    rig.status.value = unavailable(ComponentName.RUNNER)

    with pytest.raises(AlreadyBuilt):
        rig.build.execute("geneva-3km.v1")


def test_the_state_of_a_version_follows_its_latest_build() -> None:
    rig = MemoryBuilds()
    draft = rig.add_draft()
    assert rig.planning.state(draft) == "draft"

    run = rig.build.execute("geneva-3km.v1")
    sealed = rig.instances.get_version("geneva-3km.v1")
    assert sealed is not None
    states = [rig.planning.state(sealed)]
    for state in (RunState.RUNNING, RunState.SUCCEEDED):
        finish(rig, run.id, state)
        states.append(rig.planning.state(sealed))

    assert states == ["queued", "building", "ready"]


def test_the_steps_of_the_plan_name_their_periods_by_the_version() -> None:
    rig = MemoryBuilds()
    rig.add_draft()

    run = rig.build.execute("geneva-3km.v1")

    assert [item.step for item in run.steps] == [
        StepName.AREA,
        StepName.HUBS,
        StepName.ROUTES,
        StepName.TRAVELLERS_AND_BIKES,
    ]


def edit_before_the_seal(rig: MemoryBuilds, changes: dict[str, float], times: int = 1) -> None:
    """Make the draft change between the rule check and the seal, as a concurrent PATCH."""
    queue = rig.builds.queue_build
    edits = [changes] * times

    def racing(run: Run, seal_version_at: datetime | None, checked: object = None) -> None:
        if edits:
            rig.instances.update_draft_parameters(run.subject.id, edits.pop())
        queue(run, seal_version_at, checked)  # type: ignore[arg-type]

    rig.builds.queue_build = racing  # type: ignore[method-assign]


def test_a_draft_edited_to_break_a_rule_during_the_post_is_refused_and_stays_a_draft() -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    edit_before_the_seal(rig, {"min_od_distance_m": 500.0})

    with pytest.raises(RuleBroken):
        rig.build.execute("geneva-3km.v1")

    assert rig.instances.get_version("geneva-3km.v1").status == "draft"  # type: ignore[union-attr]
    assert rig.runs.list_by_states(list(RunState)) == []


def test_a_draft_edited_to_valid_values_during_the_post_is_sealed_with_them() -> None:
    rig = MemoryBuilds()
    draft = rig.add_draft()
    edit_before_the_seal(rig, {"seed": draft.parameters.seed + 1})

    run = rig.build.execute("geneva-3km.v1")

    version = rig.instances.get_version("geneva-3km.v1")
    assert version is not None
    assert (version.status, version.parameters.seed) == ("sealed", draft.parameters.seed + 1)
    assert [item.input_key for item in stored_run(rig, run.id).steps] == [
        item.input_key for item in rig.planning.plan(version).steps
    ]
