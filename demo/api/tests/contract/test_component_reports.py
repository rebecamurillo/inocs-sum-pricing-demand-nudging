"""The ComponentReports port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import Engine, delete

from pricing_demo.application.ports.component_reports import ComponentReports
from pricing_demo.domain.system_status import ComponentName, ComponentState, ComponentStatus
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.tables import component_reports, workers
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.runs import T0, later


@dataclass
class Reports:
    port: ComponentReports
    beat: Callable[[str, datetime], None]
    drop_worker: Callable[[str], None]
    inject_unknown_component: Callable[[], None]


def fake_reports() -> Iterator[Reports]:
    fake = InMemoryComponentReports()

    def beat(worker_id: str, at: datetime) -> None:
        fake.worker_heartbeats[worker_id] = at

    def drop(worker_id: str) -> None:
        fake.worker_heartbeats.pop(worker_id)

    def inject() -> None:
        pass  # the fake only holds what `write` accepts

    yield Reports(fake, beat, drop, inject)


@pytest.fixture
def postgres_reports(migrated_database: Engine) -> Reports:
    registry = PostgresWorkerRegistry(migrated_database)

    def beat(worker_id: str, at: datetime) -> None:
        registry.heartbeat(worker_id, "h", 1, T0, at)

    def drop_worker(worker_id: str) -> None:
        with migrated_database.begin() as connection:
            connection.execute(delete(workers).where(workers.c.id == worker_id))

    def inject() -> None:
        with migrated_database.begin() as connection:
            connection.execute(
                component_reports.insert().values(
                    component="gps", state="available", reported_at=T0, worker_id="w-1"
                )
            )

    return Reports(PostgresComponentReports(migrated_database), beat, drop_worker, inject)


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def reports(request: pytest.FixtureRequest) -> Iterator[Reports]:
    if request.param == "fake":
        yield from fake_reports()
    else:
        yield request.getfixturevalue("postgres_reports")


def test_nothing_is_reported_before_a_worker_writes(reports: Reports) -> None:
    read = reports.port.read()

    assert read.reports == ()
    assert read.latest_worker_heartbeat is None


def test_a_report_is_read_back_with_its_status_time_and_worker(reports: Reports) -> None:
    reports.beat("w-1", later(2))
    status = ComponentStatus.limited(ComponentName.SOLVER, "Size-limited licence.")

    reports.port.write(status, "w-1", T0)

    (report,) = reports.port.read().reports
    assert report.status == status
    assert (report.reported_at, report.worker_id) == (T0, "w-1")
    assert report.details == {}


def test_a_second_write_replaces_the_report_of_that_component(reports: Reports) -> None:
    reports.beat("w-1", T0)
    reports.port.write(ComponentStatus.ready(ComponentName.PACKAGE), "w-1", T0)
    reports.port.write(ComponentStatus.ready(ComponentName.SOLVER), "w-1", T0)

    reports.port.write(
        ComponentStatus.unavailable(ComponentName.PACKAGE, "Not installed."), "w-1", later(30)
    )

    read = {item.status.name: item for item in reports.port.read().reports}
    assert set(read) == {ComponentName.PACKAGE, ComponentName.SOLVER}
    assert read[ComponentName.PACKAGE].status.state is ComponentState.UNAVAILABLE
    assert read[ComponentName.PACKAGE].reported_at == later(30)
    assert read[ComponentName.SOLVER].reported_at == T0


def test_the_heartbeat_of_the_reporting_worker_is_joined(reports: Reports) -> None:
    reports.beat("w-1", later(7))
    reports.beat("w-2", later(9))
    reports.port.write(ComponentStatus.ready(ComponentName.SOLVER), "w-1", T0)
    reports.port.write(ComponentStatus.ready(ComponentName.PACKAGE), "w-2", T0)

    read = {item.status.name: item for item in reports.port.read().reports}

    assert read[ComponentName.SOLVER].worker_heartbeat_at == later(7)
    assert read[ComponentName.PACKAGE].worker_heartbeat_at == later(9)


def test_a_report_of_a_worker_without_a_row_has_no_heartbeat(reports: Reports) -> None:
    reports.beat("w-1", later(7))
    reports.port.write(ComponentStatus.ready(ComponentName.SOLVER), "w-1", T0)

    reports.drop_worker("w-1")

    (report,) = reports.port.read().reports
    assert report.worker_heartbeat_at is None


def test_the_latest_heartbeat_is_the_latest_of_any_worker(reports: Reports) -> None:
    reports.beat("w-1", later(7))
    reports.beat("w-2", later(3))

    assert reports.port.read().latest_worker_heartbeat == later(7)


def test_a_component_the_worker_does_not_probe_is_ignored(reports: Reports) -> None:
    reports.inject_unknown_component()
    reports.port.write(ComponentStatus.ready(ComponentName.SOLVER), "w-1", T0)

    assert [item.status.name for item in reports.port.read().reports] == [ComponentName.SOLVER]
