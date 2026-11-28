"""The WorkerRegistry port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import Engine, select

from pricing_demo.application.ports.worker_registry import WorkerRegistry
from pricing_demo.infrastructure.fakes.worker_registry import InMemoryWorkerRegistry
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.tables import workers
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.runs import T0, later


@dataclass
class Registry:
    port: WorkerRegistry
    # (host, pid, started_at, heartbeat_at) of the row, or None when there is none.
    row: Callable[[str], tuple[str, int, datetime, datetime] | None]
    delete: Callable[[str], None]
    fingerprint: Callable[[str], str | None]
    latest_heartbeat: Callable[[], datetime | None] | None = None
    rule: Callable[[str], Mapping[str, object] | None] | None = None


def fake_registry() -> Iterator[Registry]:
    fake = InMemoryWorkerRegistry()

    def row(worker_id: str) -> tuple[str, int, datetime, datetime] | None:
        found = fake.rows.get(worker_id)
        return (
            None if found is None else (found.host, found.pid, found.started_at, found.heartbeat_at)
        )

    def fingerprint(worker_id: str) -> str | None:
        found = fake.rows.get(worker_id)
        return None if found is None else found.package_fingerprint

    def rule(worker_id: str) -> Mapping[str, object] | None:
        found = fake.rows.get(worker_id)
        return None if found is None else found.simulation_rule

    yield Registry(fake, row, fake.delete, fingerprint, None, rule)


@pytest.fixture
def postgres_registry(migrated_database: Engine) -> Registry:
    def row(worker_id: str) -> tuple[str, int, datetime, datetime] | None:
        with migrated_database.connect() as connection:
            found = connection.execute(select(workers).where(workers.c.id == worker_id)).first()
        return (
            None if found is None else (found.host, found.pid, found.started_at, found.heartbeat_at)
        )

    def delete(worker_id: str) -> None:
        with migrated_database.begin() as connection:
            connection.execute(workers.delete().where(workers.c.id == worker_id))

    def fingerprint(worker_id: str) -> str | None:
        with migrated_database.connect() as connection:
            return connection.execute(
                select(workers.c.package_fingerprint).where(workers.c.id == worker_id)
            ).scalar()

    def rule(worker_id: str) -> Mapping[str, object] | None:
        with migrated_database.connect() as connection:
            return connection.execute(
                select(workers.c.simulation_rule).where(workers.c.id == worker_id)
            ).scalar()

    return Registry(
        PostgresWorkerRegistry(migrated_database),
        row,
        delete,
        fingerprint,
        PostgresRunRepository(migrated_database).latest_worker_heartbeat,
        rule,
    )


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def registry(request: pytest.FixtureRequest) -> Iterator[Registry]:
    if request.param == "fake":
        yield from fake_registry()
    else:
        yield request.getfixturevalue("postgres_registry")


def test_register_stores_the_worker_with_its_start_as_first_heartbeat(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 4242, T0)

    assert registry.row("w-1") == ("host-a", 4242, T0, T0)


def test_registering_again_replaces_the_row(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 4242, T0)

    registry.port.register("w-1", "host-a", 4243, later(100))

    assert registry.row("w-1") == ("host-a", 4243, later(100), later(100))


def test_a_heartbeat_moves_only_the_heartbeat(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 4242, T0)

    registry.port.heartbeat("w-1", "host-a", 4242, T0, later(5))

    assert registry.row("w-1") == ("host-a", 4242, T0, later(5))


def test_a_heartbeat_after_the_row_was_deleted_creates_it_again(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 4242, T0)
    registry.delete("w-1")
    assert registry.row("w-1") is None

    registry.port.heartbeat("w-1", "host-a", 4242, T0, later(10))

    assert registry.row("w-1") == ("host-a", 4242, T0, later(10))


def test_two_workers_have_two_rows(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0)
    registry.port.register("w-2", "host-b", 2, later(1))

    assert registry.row("w-1") == ("host-a", 1, T0, T0)
    assert registry.row("w-2") == ("host-b", 2, later(1), later(1))


def test_the_row_carries_the_package_fingerprint(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0, "abc")

    assert registry.fingerprint("w-1") == "abc"

    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5), "def")

    assert registry.fingerprint("w-1") == "def"


def test_a_worker_without_a_fingerprint_has_none(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0)

    assert registry.fingerprint("w-1") is None


def test_a_heartbeat_that_knows_no_fingerprint_keeps_the_rows(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0, "abc")

    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5))

    assert registry.fingerprint("w-1") == "abc"


def test_a_heartbeat_after_the_row_was_deleted_writes_the_fingerprint_it_knows(
    registry: Registry,
) -> None:
    registry.port.register("w-1", "host-a", 1, T0, "abc")
    registry.delete("w-1")

    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5), "abc")

    assert registry.fingerprint("w-1") == "abc"


RULE = {"id": "balanced-score", "version": 1, "parameters": {"price_weight": 0.5}}


def rule_of(registry: Registry, worker_id: str) -> Mapping[str, object] | None:
    assert registry.rule is not None
    return registry.rule(worker_id)


def test_the_row_carries_the_simulation_rule_of_the_worker(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0, None, RULE)

    assert rule_of(registry, "w-1") == RULE

    other = {**RULE, "version": 2}
    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5), None, other)

    assert rule_of(registry, "w-1") == other


def test_a_worker_without_a_rule_has_none(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0)

    assert rule_of(registry, "w-1") is None


def test_a_heartbeat_that_knows_no_rule_keeps_the_rows(registry: Registry) -> None:
    registry.port.register("w-1", "host-a", 1, T0, None, RULE)

    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5))

    assert rule_of(registry, "w-1") == RULE


def test_a_heartbeat_after_the_row_was_deleted_writes_the_rule_it_knows(
    registry: Registry,
) -> None:
    registry.port.register("w-1", "host-a", 1, T0, None, RULE)
    registry.delete("w-1")

    registry.port.heartbeat("w-1", "host-a", 1, T0, later(5), None, RULE)

    assert rule_of(registry, "w-1") == RULE


@pytest.mark.integration
def test_the_run_repository_sees_the_latest_heartbeat(postgres_registry: Registry) -> None:
    assert postgres_registry.latest_heartbeat is not None
    postgres_registry.port.register("w-1", "host-a", 1, T0)
    postgres_registry.port.heartbeat("w-1", "host-a", 1, T0, later(9))

    assert postgres_registry.latest_heartbeat() == later(9)
