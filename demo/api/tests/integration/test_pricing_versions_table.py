"""What the database itself guarantees about pricing versions, and the deletions around them."""

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.domain.builds import RunActive
from pricing_demo.domain.pricing_versions import HasPricingVersions
from pricing_demo.domain.runs import RunKind, RunState
from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.tables import run_steps, runs
from tests.support.pricing_versions import insert_pricing_version
from tests.support.runs import T0, later, make_run

pytestmark = pytest.mark.integration

GOALS = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
    "flat_price_per_ride_chf",
)


def update(engine: Engine, sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.mark.parametrize("column", GOALS)
def test_a_sealed_version_refuses_an_update_of_any_goal(
    migrated_database: Engine, column: str
) -> None:
    version = insert_pricing_version(migrated_database, status="sealed")

    with pytest.raises(DBAPIError, match="cannot change"):
        update(
            migrated_database, f"UPDATE pricing_versions SET {column} = 99 WHERE id = '{version}'"
        )


def test_a_sealed_version_still_allows_the_name_and_an_unchanged_goal(
    migrated_database: Engine,
) -> None:
    version = insert_pricing_version(migrated_database, status="sealed")

    update(
        migrated_database,
        "UPDATE pricing_versions SET name = 'Renamed', pt_fare_chf = pt_fare_chf "
        f"WHERE id = '{version}'",
    )

    with migrated_database.connect() as connection:
        name = connection.execute(text("SELECT name FROM pricing_versions")).scalar_one()
    assert name == "Renamed"


def test_a_draft_changes_freely_and_can_be_sealed(migrated_database: Engine) -> None:
    version = insert_pricing_version(migrated_database)

    update(
        migrated_database, f"UPDATE pricing_versions SET cost_bike_chf = 3 WHERE id = '{version}'"
    )
    update(
        migrated_database, f"UPDATE pricing_versions SET status = 'sealed' WHERE id = '{version}'"
    )

    with pytest.raises(DBAPIError):
        update(
            migrated_database,
            f"UPDATE pricing_versions SET cost_bike_chf = 4 WHERE id = '{version}'",
        )


def test_a_letter_is_unique_per_instance_version_and_the_status_and_kind_are_enumerated(
    migrated_database: Engine,
) -> None:
    insert_pricing_version(migrated_database)

    with pytest.raises(IntegrityError):
        insert_pricing_version(migrated_database)
    with pytest.raises(IntegrityError):
        update(migrated_database, "UPDATE pricing_versions SET status = 'open'")
    with pytest.raises(IntegrityError):
        update(migrated_database, "UPDATE pricing_versions SET flat_price_kind = 'per_km'")


def test_a_run_naming_an_unknown_pricing_version_is_refused_by_the_foreign_key(
    migrated_database: Engine,
) -> None:
    with pytest.raises(IntegrityError) as refusal, migrated_database.begin() as connection:
        connection.execute(
            insert(runs).values(
                id="r1",
                kind="pricing",
                pricing_version_id="g.v1.A",
                state="queued",
                queued_at=T0,
            )
        )

    diagnostics = getattr(refusal.value.orig, "diag", None)
    assert getattr(diagnostics, "constraint_name", None) == (
        "fk_runs_pricing_version_id_pricing_versions"
    )


def seal_with_run(engine: Engine, version: str, run_id: str, state: RunState) -> None:
    update(engine, f"UPDATE pricing_versions SET status = 'sealed' WHERE id = '{version}'")
    PostgresRunRepository(engine).add(
        make_run(run_id, kind=RunKind.PRICING, subject_id=version, state=state, queued_at=later(1))
    )
    with engine.begin() as connection:
        connection.execute(
            insert(run_steps).values(run_id=run_id, position=2, step="pricing_model", state="done")
        )


def count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_deleting_a_pricing_version_removes_its_periods_runs_and_steps(
    migrated_database: Engine,
) -> None:
    version = insert_pricing_version(migrated_database)
    seal_with_run(migrated_database, version, "r1", RunState.SUCCEEDED)

    PostgresPricingVersions(migrated_database).delete(version)

    assert [
        count(migrated_database, name) for name in ("pricing_versions", "pricing_version_periods")
    ] == [0, 0]
    assert count(migrated_database, "runs") == 0
    assert count(migrated_database, "run_steps") == 0


def test_deleting_with_or_without_the_flag(migrated_database: Engine) -> None:
    first = insert_pricing_version(migrated_database, letter="A")
    insert_pricing_version(migrated_database, letter="B")
    seal_with_run(migrated_database, first, "r1", RunState.FAILED)
    builds = PostgresBuilds(migrated_database)

    with pytest.raises(HasPricingVersions) as refusal:
        builds.delete_version("geneva-3km.v1")
    assert refusal.value.pricing_version_ids == ("geneva-3km.v1.A", "geneva-3km.v1.B")
    assert count(migrated_database, "pricing_versions") == 2

    builds.delete_version("geneva-3km.v1", including_pricing_versions=True)

    assert [
        count(migrated_database, name) for name in ("pricing_versions", "runs", "run_steps")
    ] == [0, 0, 0]
    assert count(migrated_database, "instance_versions") == 0


def test_deleting_an_instance_with_the_flag_removes_the_pricing_versions(
    migrated_database: Engine,
) -> None:
    version = insert_pricing_version(migrated_database)
    seal_with_run(migrated_database, version, "r1", RunState.SUCCEEDED)
    builds = PostgresBuilds(migrated_database)

    with pytest.raises(HasPricingVersions):
        builds.delete_instance("geneva-3km")
    builds.delete_instance("geneva-3km", including_pricing_versions=True)

    assert [
        count(migrated_database, name) for name in ("pricing_versions", "runs", "city_instances")
    ] == [0, 0, 0]


def test_an_active_pricing_run_refuses_every_deletion(migrated_database: Engine) -> None:
    version = insert_pricing_version(migrated_database)
    seal_with_run(migrated_database, version, "r1", RunState.RUNNING)
    builds = PostgresBuilds(migrated_database)
    pricing: PricingVersions = PostgresPricingVersions(migrated_database)

    with pytest.raises(RunActive):
        builds.delete_version("geneva-3km.v1", including_pricing_versions=True)
    with pytest.raises(RunActive):
        builds.delete_instance("geneva-3km", including_pricing_versions=True)
    with pytest.raises(RunActive):
        pricing.delete(version)

    assert count(migrated_database, "pricing_versions") == 1
    assert count(migrated_database, "runs") == 1


def test_the_migration_goes_down_and_up_with_pricing_versions_present(
    migrated_database: Engine,
) -> None:
    from alembic import command
    from alembic.config import Config

    from tests.support.database import ALEMBIC_INI, migrate_to_head

    command.downgrade(Config(str(ALEMBIC_INI)), "d5b8e2a7c314")
    with migrated_database.connect() as connection:
        columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'instance_versions'"
                )
            ).scalars()
        )
    assert "next_pricing_letter" not in columns
    migrate_to_head()
    assert count(migrated_database, "pricing_versions") == 0
