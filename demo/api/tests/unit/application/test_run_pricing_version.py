from datetime import datetime

import pytest

from pricing_demo.application.use_cases.run_pricing_version import RunPricingVersion
from pricing_demo.domain.builds import ComponentUnavailable, DraftChanged, RunActive
from pricing_demo.domain.pricing_rules import PricingRuleBroken
from pricing_demo.domain.pricing_versions import AlreadyRun, PricingVersionNotFound, new_draft_goals
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, SubjectType
from pricing_demo.domain.system_status import ComponentName
from tests.support.builds import MemoryBuilds, unavailable
from tests.support.pricing_versions import sealed_pricing_version
from tests.support.runs import T0

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"


def rig_with_draft(**changes: float) -> tuple[MemoryBuilds, str]:
    rig = MemoryBuilds()
    goals = new_draft_goals(None).replacing(changes)
    return rig, rig.pricing.create_draft(VERSION, None, goals, PERIOD, None, T0).id


def stored(rig: MemoryBuilds, run_id: str) -> Run:
    run = rig.runs.get(run_id)
    assert run is not None
    return run


def test_an_unknown_version_is_refused() -> None:
    rig = MemoryBuilds()

    with pytest.raises(PricingVersionNotFound):
        rig.run_pricing.execute("geneva-3km.v1.Q")


def test_a_version_deleted_after_it_was_read_is_refused_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig, version = rig_with_draft()
    # A deletion that commits between the read of the version and the read of its periods.
    monkeypatch.setattr(rig.pricing, "period_ids", lambda version_id: [])

    with pytest.raises(PricingVersionNotFound):
        rig.run_pricing.execute(version)

    assert rig.runs.list_by_states(list(RunState)) == []


def test_a_valid_draft_is_sealed_and_a_pricing_run_with_two_steps_is_queued() -> None:
    rig, version = rig_with_draft()

    run = rig.run_pricing.execute(version)

    found = stored(rig, run.id)
    assert (found.kind, found.state, found.queued_at) == (RunKind.PRICING, RunState.QUEUED, T0)
    assert (found.subject.type, found.subject.id) == (SubjectType.PRICING_VERSION, version)
    assert [(item.position, item.step, item.period) for item in found.steps] == [
        (1, StepName.PRICING_MODEL, PERIOD),
        (2, StepName.TRAVELLER_SIMULATION, PERIOD),
    ]
    sealed = rig.pricing.get(version)
    assert sealed is not None
    assert (sealed.status, sealed.sealed_at) == ("sealed", T0)


def test_a_draft_that_breaks_a_rule_is_refused_with_every_failure_and_stays_a_draft() -> None:
    rig, version = rig_with_draft(pt_fare_chf=-1, max_displayed_options=0)

    with pytest.raises(PricingRuleBroken) as refusal:
        rig.run_pricing.execute(version)

    assert [(item.field, item.value) for item in refusal.value.failures] == [
        ("pt_fare_chf", -1),
        ("max_displayed_options", 0),
    ]
    assert rig.pricing.get(version).status == "draft"  # type: ignore[union-attr]
    assert rig.runs.list_by_states(list(RunState)) == []


@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING])
def test_a_version_with_an_active_run_is_refused_with_that_run(state: RunState) -> None:
    rig, version = rig_with_draft()
    sealed_pricing_version(rig, version, state)

    with pytest.raises(RunActive) as refusal:
        rig.run_pricing.execute(version)

    assert refusal.value.run_id == f"pricing-{version}"


def test_a_version_whose_last_run_succeeded_is_refused_as_already_run() -> None:
    rig, version = rig_with_draft()
    sealed_pricing_version(rig, version, RunState.SUCCEEDED)

    with pytest.raises(AlreadyRun):
        rig.run_pricing.execute(version)


def test_the_refusals_come_in_their_order() -> None:
    rig, version = rig_with_draft(pt_fare_chf=-1)
    rig.status.value = unavailable(ComponentName.SOLVER)

    with pytest.raises(PricingRuleBroken):
        rig.run_pricing.execute(version)
    rig.pricing.update_draft(version, {"pt_fare_chf": 2})
    sealed_pricing_version(rig, version, RunState.RUNNING)
    with pytest.raises(RunActive):
        rig.run_pricing.execute(version)


def test_a_component_the_run_needs_blocks_it_and_nothing_is_sealed_or_queued() -> None:
    rig, version = rig_with_draft()
    rig.status.value = unavailable(ComponentName.SOLVER, ComponentName.RUNNER)

    with pytest.raises(ComponentUnavailable) as refusal:
        rig.run_pricing.execute(version)

    assert [item.component for item in refusal.value.reasons] == [
        ComponentName.RUNNER,
        ComponentName.SOLVER,
    ]
    assert rig.pricing.get(version).status == "draft"  # type: ignore[union-attr]
    assert rig.runs.list_by_states(list(RunState)) == []


def test_the_trip_planner_is_not_a_component_a_pricing_run_needs() -> None:
    rig, version = rig_with_draft()
    rig.status.value = unavailable(ComponentName.TRIP_PLANNER)

    run = rig.run_pricing.execute(version)

    assert stored(rig, run.id).state is RunState.QUEUED


@pytest.mark.parametrize("state", [RunState.FAILED, RunState.CANCELLED])
def test_run_again_queues_a_new_run_on_a_sealed_version_whose_last_run_ended_badly(
    state: RunState,
) -> None:
    rig, version = rig_with_draft()
    sealed_pricing_version(rig, version, state)

    run = rig.run_pricing.execute(version)

    assert stored(rig, run.id).state is RunState.QUEUED
    assert len(rig.runs.list_by_states(list(RunState))) == 2
    # The version stays sealed as it was: a run again seals nothing.
    assert rig.pricing.get(version).sealed_at == datetime(2026, 11, 27, tzinfo=T0.tzinfo)  # type: ignore[union-attr]


class ChangingPricing:
    """A pricing versions port whose draft is edited under the use case a number of times."""

    def __init__(self, rig: MemoryBuilds, version: str, changes: int) -> None:
        self._rig, self._version, self.changes, self.attempts = rig, version, changes, 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._rig.pricing, name)

    def queue_run(self, run: Run, seal_at: object, checked: object) -> None:
        self.attempts += 1
        if self.changes > 0:
            self.changes -= 1
            raise DraftChanged(self._version)
        self._rig.pricing.queue_run(run, seal_at, checked)  # type: ignore[arg-type]


def test_a_draft_edited_between_the_check_and_the_seal_is_checked_again() -> None:
    rig, version = rig_with_draft()
    pricing = ChangingPricing(rig, version, 1)
    use_case = RunPricingVersion(pricing, rig.status, rig.ids, rig.clock)  # type: ignore[arg-type]

    run = use_case.execute(version)

    assert pricing.attempts == 2
    assert stored(rig, run.id).state is RunState.QUEUED


def test_a_draft_that_keeps_changing_is_left_to_the_next_request() -> None:
    rig, version = rig_with_draft()
    pricing = ChangingPricing(rig, version, 99)
    use_case = RunPricingVersion(pricing, rig.status, rig.ids, rig.clock)  # type: ignore[arg-type]

    with pytest.raises(DraftChanged):
        use_case.execute(version)

    assert pricing.attempts == 3
    assert rig.pricing.get(version).status == "draft"  # type: ignore[union-attr]
