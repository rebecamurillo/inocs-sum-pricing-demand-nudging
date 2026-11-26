"""Emptying the stored data, on scratch tables of a metadata that belongs to the test."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, Engine, ForeignKey, Integer, MetaData, String, Table, insert, select
from sqlalchemy import func as sql

from pricing_demo import bootstrap
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.metadata import NAMING_CONVENTION
from pricing_demo.infrastructure.persistence.tables import component_reports
from pricing_demo.infrastructure.persistence.truncate import truncate_all
from tests.support.runs import T0

pytestmark = pytest.mark.integration

RESET = "/api/test-control/reset"


def scratch_tables() -> tuple[MetaData, Table, Table]:
    """A parent and a child that references it, so the order of emptying matters."""
    scratch = MetaData(naming_convention=NAMING_CONVENTION)
    parent = Table(
        "scratch_parent",
        scratch,
        Column("id", Integer, primary_key=True),
        Column("name", String, nullable=False),
    )
    child = Table(
        "scratch_child",
        scratch,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("scratch_parent.id"), nullable=False),
    )
    return scratch, parent, child


def fill(engine: Engine, parent: Table, child: Table) -> None:
    with engine.begin() as connection:
        connection.execute(insert(parent).values(name="first"))
        connection.execute(insert(child).values(parent_id=1))


def count(engine: Engine, table: Table) -> int:
    with engine.connect() as connection:
        return connection.execute(select(sql.count()).select_from(table)).scalar_one()


def test_every_table_of_the_metadata_is_emptied(migrated_database: Engine) -> None:
    scratch, parent, child = scratch_tables()
    scratch.create_all(migrated_database)
    fill(migrated_database, parent, child)

    truncate_all(migrated_database, scratch)

    assert (count(migrated_database, parent), count(migrated_database, child)) == (0, 0)


def test_the_identity_counters_restart(migrated_database: Engine) -> None:
    scratch, parent, child = scratch_tables()
    scratch.create_all(migrated_database)
    fill(migrated_database, parent, child)

    truncate_all(migrated_database, scratch)
    fill(migrated_database, parent, child)

    with migrated_database.connect() as connection:
        assert connection.execute(select(parent.c.id)).scalar_one() == 1


def test_the_migration_history_is_kept(migrated_database: Engine) -> None:
    scratch, _, _ = scratch_tables()
    scratch.create_all(migrated_database)
    history = Table("alembic_version", MetaData(), autoload_with=migrated_database)

    truncate_all(migrated_database, scratch)

    assert count(migrated_database, history) == 1


def test_a_metadata_without_tables_changes_nothing(migrated_database: Engine) -> None:
    truncate_all(migrated_database, MetaData())


def test_the_reset_route_empties_the_stored_data(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch, parent, child = scratch_tables()
    scratch.create_all(migrated_database)
    fill(migrated_database, parent, child)
    monkeypatch.setattr(bootstrap, "metadata", scratch)
    app = bootstrap.create_application(Settings(adapters="fake"))

    with TestClient(app) as client:
        response = client.post(RESET)

    assert response.status_code == 204
    assert (count(migrated_database, parent), count(migrated_database, child)) == (0, 0)


def test_the_reset_route_leaves_the_default_fake_settings(
    migrated_database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    PostgresFakeSettings(migrated_database).set_component("solver", "unavailable", "No licence.")
    app = bootstrap.create_application(Settings(adapters="fake"))

    with TestClient(app) as client:
        response = client.post(RESET)

    assert response.status_code == 204
    assert PostgresFakeSettings(migrated_database).read() == {
        "components": {
            name: {"state": "available", "reason": None}
            for name in ("solver", "package", "trip_planner")
        }
    }


def test_the_reset_route_empties_the_component_reports_and_the_workers(
    migrated_database: Engine,
) -> None:
    with migrated_database.begin() as connection:
        connection.execute(
            component_reports.insert().values(
                component="solver", state="available", reported_at=T0, worker_id="w-1"
            )
        )
    app = bootstrap.create_application(Settings(adapters="fake"))

    with TestClient(app) as client:
        client.post(RESET)

    assert count(migrated_database, component_reports) == 0
