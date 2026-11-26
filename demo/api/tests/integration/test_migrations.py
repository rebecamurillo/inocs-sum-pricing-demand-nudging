import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect

from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from tests.support.database import ALEMBIC_INI, migrate_to_head

pytestmark = pytest.mark.integration

BASELINE = "7c1f3a9e2b40"


def test_storage_is_unavailable_before_the_migrations_are_applied(empty_database: Engine) -> None:
    status = StorageProbe(empty_database).check()

    assert not status.available
    assert status.reason is not None
    assert "migration none" in status.reason


def test_storage_is_available_once_the_migrations_are_applied(migrated_database: Engine) -> None:
    assert StorageProbe(migrated_database).check().available


def test_the_head_creates_the_tables_of_the_runs(migrated_database: Engine) -> None:
    assert set(inspect(migrated_database).get_table_names()) == {
        "alembic_version",
        "runs",
        "run_steps",
        "workers",
    }


def test_the_migration_goes_down_and_up_again(migrated_database: Engine) -> None:
    command.downgrade(Config(str(ALEMBIC_INI)), BASELINE)

    assert inspect(migrated_database).get_table_names() == ["alembic_version"]

    migrate_to_head()

    assert set(inspect(migrated_database).get_table_names()) == {
        "alembic_version",
        "runs",
        "run_steps",
        "workers",
    }
    assert StorageProbe(migrated_database).check().available


def test_applying_the_migrations_twice_changes_nothing(migrated_database: Engine) -> None:
    migrate_to_head()

    assert StorageProbe(migrated_database).check().available
