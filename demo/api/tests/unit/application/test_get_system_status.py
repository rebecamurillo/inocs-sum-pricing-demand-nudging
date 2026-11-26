from datetime import timedelta

import pytest

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.domain.system_status import (
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import fixed_probe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from tests.support.runs import T0

STORAGE_OK = ComponentStatus.ready(ComponentName.STORAGE)


class Rig:
    def __init__(self, storage: ComponentStatus = STORAGE_OK) -> None:
        self.reports = InMemoryComponentReports()
        self.clock = FixedClock(T0)
        self.use_case = GetSystemStatus(fixed_probe(storage), self.reports, self.clock)

    def report_all(self, worker_id: str = "w-1") -> None:
        for name in (ComponentName.SOLVER, ComponentName.PACKAGE, ComponentName.TRIP_PLANNER):
            self.reports.write(ComponentStatus.ready(name), worker_id, T0)
        self.reports.worker_heartbeats[worker_id] = T0


def test_the_status_lists_every_component_in_order() -> None:
    rig = Rig()
    rig.report_all()

    status = rig.use_case.execute()

    assert [item.name for item in status.components] == list(ComponentName)


def test_every_action_can_start_when_the_runner_reports_every_component_available() -> None:
    rig = Rig()
    rig.report_all()

    status = rig.use_case.execute()

    assert status.can_build_instances.allowed
    assert status.can_run_pricing.allowed
    assert status.can_simulate.allowed


def test_a_reported_unavailable_component_keeps_its_reason_and_refuses_its_action() -> None:
    rig = Rig()
    rig.report_all()
    rig.reports.write(
        ComponentStatus.unavailable(ComponentName.TRIP_PLANNER, "OTP does not answer."),
        "w-1",
        T0,
    )

    status = rig.use_case.execute()

    assert not status.can_build_instances.allowed
    assert status.can_build_instances.reasons[0].reason == "OTP does not answer."
    assert status.can_simulate.allowed


def test_the_status_is_read_again_at_each_execution() -> None:
    rig = Rig()
    rig.report_all()
    assert rig.use_case.execute().can_simulate.allowed

    rig.clock.advance(timedelta(seconds=31))

    status = rig.use_case.execute()
    assert not status.can_simulate.allowed
    runner = status.components[1]
    assert runner.state is ComponentState.UNAVAILABLE


def test_storage_down_does_not_read_the_reports() -> None:
    class Exploding(InMemoryComponentReports):
        def read(self):  # type: ignore[no-untyped-def]
            raise AssertionError("reports must not be read")

    use_case = GetSystemStatus(
        fixed_probe(ComponentStatus.unavailable(ComponentName.STORAGE, "no database")),
        Exploding(),
        FixedClock(T0),
    )

    status = use_case.execute()

    assert status.components[0].reason == "no database"
    assert not status.can_simulate.allowed


def test_a_probe_for_another_component_than_storage_is_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="storage"):
        GetSystemStatus(
            fixed_probe(ComponentStatus.ready(ComponentName.SOLVER)),
            InMemoryComponentReports(),
            FixedClock(T0),
        )
