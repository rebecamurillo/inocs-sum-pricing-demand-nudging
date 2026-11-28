"""The ComponentReports port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable, Iterator, Mapping
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
    beat_with_rule: Callable[[str, datetime, Mapping[str, object]], None]
    drop_worker: Callable[[str], None]
    inject_unknown_component: Callable[[], None]


def fake_reports() -> Iterator[Reports]:
    fake = InMemoryComponentReports()

    def beat(worker_id: str, at: datetime) -> None:
        fake.worker_heartbeats[worker_id] = at

    def beat_with_rule(worker_id: str, at: datetime, rule: Mapping[str, object]) -> None:
        fake.worker_heartbeats[worker_id] = at
        fake.worker_rules[worker_id] = rule

    def drop(worker_id: str) -> None:
        fake.worker_heartbeats.pop(worker_id)

    def inject() -> None:
        pass  # the fake only holds what `write` accepts

    yield Reports(fake, beat, beat_with_rule, drop, inject)


@pytest.fixture
def postgres_reports(migrated_database: Engine) -> Reports:
    registry = PostgresWorkerRegistry(migrated_database)

    def beat(worker_id: str, at: datetime) -> None:
        registry.heartbeat(worker_id, "h", 1, T0, at)

    def beat_with_rule(worker_id: str, at: datetime, rule: Mapping[str, object]) -> None:
        registry.heartbeat(worker_id, "h", 1, T0, at, None, rule)

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

    return Reports(
        PostgresComponentReports(migrated_database), beat, beat_with_rule, drop_worker, inject
    )


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


def test_the_details_given_to_a_write_are_read_back(reports: Reports) -> None:
    reports.beat("w-1", T0)
    details = {"graph_manifest": {"dataset_id": "d"}, "graph_sha256": None}

    reports.port.write(ComponentStatus.ready(ComponentName.TRIP_PLANNER), "w-1", T0, details)
    reports.port.write(ComponentStatus.ready(ComponentName.SOLVER), "w-1", T0)

    read = {item.status.name: item for item in reports.port.read().reports}
    assert read[ComponentName.TRIP_PLANNER].details == details
    assert read[ComponentName.SOLVER].details == {}


RULE_1 = {"id": "balanced-score", "version": 1, "parameters": {"price_weight": 0.5}}
RULE_2 = {"id": "balanced-score", "version": 2, "parameters": {"price_weight": 0.6}}


def test_the_rule_is_the_one_of_the_worker_with_the_latest_heartbeat(reports: Reports) -> None:
    reports.beat_with_rule("w-1", later(3), RULE_1)
    reports.beat_with_rule("w-2", later(9), RULE_2)

    assert reports.port.read().simulation_rule == RULE_2

    reports.beat_with_rule("w-1", later(20), RULE_1)

    assert reports.port.read().simulation_rule == RULE_1


def test_there_is_no_rule_without_a_worker_or_when_the_latest_worker_records_none(
    reports: Reports,
) -> None:
    assert reports.port.read().simulation_rule is None

    reports.beat_with_rule("w-1", later(3), RULE_1)
    reports.beat("w-2", later(9))

    assert reports.port.read().simulation_rule is None
