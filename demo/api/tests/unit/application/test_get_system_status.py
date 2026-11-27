from datetime import timedelta

import pytest

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.domain.system_status import (
    NO_CITY_DATA_REASON,
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import fixed_probe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from tests.support.runs import T0

STORAGE_OK = ComponentStatus.ready(ComponentName.STORAGE)


class Rig:
    def __init__(self, storage: ComponentStatus = STORAGE_OK) -> None:
        self.reports = InMemoryComponentReports()
        self.clock = FixedClock(T0)
        self.datasets = InMemoryCityDatasets()
        self.datasets.add(fake_city_dataset("geneva-2026-11-26", T0))
        self.use_case = GetSystemStatus(
            fixed_probe(storage), self.reports, self.datasets, self.clock
        )

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
        InMemoryCityDatasets(),
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
            InMemoryCityDatasets(),
            FixedClock(T0),
        )


def test_city_data_is_unavailable_while_no_data_set_is_imported() -> None:
    rig = Rig()
    rig.report_all()
    rig.datasets = InMemoryCityDatasets()
    rig.use_case = GetSystemStatus(fixed_probe(STORAGE_OK), rig.reports, rig.datasets, rig.clock)

    status = rig.use_case.execute()

    city = status.components[-1]
    assert (city.name, city.state, city.reason) == (
        ComponentName.CITY_DATA,
        ComponentState.UNAVAILABLE,
        NO_CITY_DATA_REASON,
    )
    assert not status.can_build_instances.allowed
    assert status.can_run_pricing.allowed
    assert status.can_simulate.allowed


def test_city_data_is_available_once_a_data_set_exists() -> None:
    rig = Rig()
    rig.report_all()

    assert rig.use_case.execute().components[-1].state is ComponentState.AVAILABLE


def test_storage_down_makes_city_data_not_known_without_counting() -> None:
    class Exploding(InMemoryCityDatasets):
        def count(self) -> int:
            raise AssertionError("the data sets must not be counted")

    use_case = GetSystemStatus(
        fixed_probe(ComponentStatus.unavailable(ComponentName.STORAGE, "no database")),
        InMemoryComponentReports(),
        Exploding(),
        FixedClock(T0),
    )

    city = use_case.execute().components[-1]

    assert city.state is ComponentState.UNAVAILABLE
    assert city.reason == "Not known: the database does not answer."


def test_the_current_rule_is_the_one_the_latest_live_worker_records() -> None:
    rig = Rig()
    rig.report_all()
    rig.reports.worker_rules["w-1"] = {"id": "balanced-score", "version": 2, "parameters": {"a": 1}}

    status = rig.use_case.execute()

    assert status.simulation_rule is not None
    assert (status.simulation_rule.id, status.simulation_rule.version) == ("balanced-score", 2)


def test_there_is_no_current_rule_without_a_worker_record() -> None:
    rig = Rig()
    rig.report_all()

    assert rig.use_case.execute().simulation_rule is None
