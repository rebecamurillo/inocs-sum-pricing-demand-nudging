import pytest
from sqlalchemy import Engine, inspect

from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from tests.support.database import migrate_to_head

pytestmark = pytest.mark.integration


def test_storage_is_unavailable_before_the_migrations_are_applied(empty_database: Engine) -> None:
    status = StorageProbe(empty_database).check()

    assert not status.available
    assert status.reason is not None
    assert "migration none" in status.reason


def test_storage_is_available_once_the_migrations_are_applied(migrated_database: Engine) -> None:
    assert StorageProbe(migrated_database).check().available


def test_the_baseline_migration_creates_no_table_of_its_own(migrated_database: Engine) -> None:
    assert inspect(migrated_database).get_table_names() == ["alembic_version"]


def test_applying_the_migrations_twice_changes_nothing(migrated_database: Engine) -> None:
    migrate_to_head()

    assert StorageProbe(migrated_database).check().available
