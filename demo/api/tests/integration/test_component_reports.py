"""The worker's reports and the API's status on a real database and a fake clock."""

import threading
from datetime import datetime

import pytest
from sqlalchemy import Engine, delete

from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe, fixed_probe
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.tables import component_reports, workers
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.reporting import REPORT_EVERY, quiet_fingerprint
from tests.support.runs import T0, later

pytestmark = pytest.mark.integration


class Rig:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.clock = FixedClock(T0)
        self.waiter = FakeWaiter(self.clock)
        self.settings = PostgresFakeSettings(engine)
        self.reports = PostgresComponentReports(engine)
        self.until = threading.Event()
        identity = WorkerIdentity("w-1", "h", 1, T0)
        repository = PostgresRunRepository(engine)
        registry = PostgresWorkerRegistry(engine)
        self.worker = RunWorker(
            identity,
            registry,
            RecoverInterruptedRuns(repository, self.clock),
            ProcessNextRun(repository, StepRegistry(), registry, identity, self.clock, self.waiter),
            ReportComponents(
                [FakeProbe(name, self.settings) for name in PROBED_COMPONENTS],
                self.reports,
                "w-1",
                self.clock,
            ),
            REPORT_EVERY,
            self.clock,
            self.waiter,
            quiet_fingerprint(self.clock),
        )
        self.status = GetSystemStatus(
            fixed_probe(ComponentStatus.ready(ComponentName.STORAGE)),
            self.reports,
            PostgresCityDatasets(self.engine),
            self.clock,
        )

    def stop_at(self, seconds: float) -> None:
        def hook(now: datetime) -> None:
            if now >= later(seconds):
                self.until.set()

        self.waiter.on_wait = hook


@pytest.fixture
def rig(migrated_database: Engine) -> Rig:
    return Rig(migrated_database)


def stored_reports(engine: Engine) -> dict[str, tuple[str, str | None]]:
    with engine.connect() as connection:
        rows = connection.execute(component_reports.select()).all()
    return {row.component: (row.state, row.reason) for row in rows}


def test_starting_the_worker_writes_one_report_per_probed_component(rig: Rig) -> None:
    rig.worker.start()

    assert stored_reports(rig.engine) == {
        "solver": ("available", None),
        "package": ("available", None),
        "trip_planner": ("available", None),
    }
    with rig.engine.connect() as connection:
        rows = connection.execute(component_reports.select()).all()
    assert {(row.worker_id, row.reported_at) for row in rows} == {("w-1", T0)}


def test_the_runner_is_available_until_thirty_seconds_after_its_heartbeat(rig: Rig) -> None:
    rig.worker.start()

    def runner_state() -> dict[ComponentName, ComponentStatus]:
        return {item.name: item for item in rig.status.execute().components}

    rig.clock.set(later(30))
    at_30 = runner_state()
    rig.clock.set(later(31))
    at_31 = runner_state()

    assert at_30[ComponentName.RUNNER].state is ComponentState.AVAILABLE
    assert at_30[ComponentName.SOLVER].state is ComponentState.AVAILABLE
    assert at_31[ComponentName.RUNNER].state is ComponentState.UNAVAILABLE
    for name in PROBED_COMPONENTS:
        assert at_31[name].state is ComponentState.UNAVAILABLE
        assert at_31[name].reason is not None
        assert "has not reported" in (at_31[name].reason or "")


def test_a_report_survives_the_deletion_of_its_workers_row_but_reads_as_not_reported(
    rig: Rig,
) -> None:
    rig.worker.start()
    with rig.engine.begin() as connection:
        connection.execute(delete(workers))

    status = rig.status.execute()

    assert not status.can_simulate.allowed
    assert {item.name: item.state for item in status.components}[ComponentName.SOLVER] is (
        ComponentState.UNAVAILABLE
    )


def test_a_fake_setting_changed_reaches_the_row_at_the_next_cycle(rig: Rig) -> None:
    rig.worker.start()
    rig.settings.set_component("trip_planner", "unavailable", "No answer from OpenTripPlanner.")
    rig.stop_at(31)

    rig.worker.run(rig.until)

    assert stored_reports(rig.engine)["trip_planner"] == (
        "unavailable",
        "No answer from OpenTripPlanner.",
    )
    status = rig.status.execute()
    assert not status.can_build_instances.allowed
    assert status.can_run_pricing.allowed
    assert status.can_simulate.allowed
