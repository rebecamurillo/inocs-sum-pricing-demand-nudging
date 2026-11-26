import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from pricing_demo.domain.system_status import ComponentState
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from tests.support.database import ALEMBIC_INI, migrate_to_head

pytestmark = pytest.mark.integration

BASELINE = "7c1f3a9e2b40"


def test_storage_is_unavailable_before_the_migrations_are_applied(empty_database: Engine) -> None:
    status = StorageProbe(empty_database).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason is not None
    assert "migration none" in status.reason


def test_storage_is_available_once_the_migrations_are_applied(migrated_database: Engine) -> None:
    assert StorageProbe(migrated_database).check().state is ComponentState.AVAILABLE


def test_the_head_creates_the_tables_of_the_runs(migrated_database: Engine) -> None:
    assert set(inspect(migrated_database).get_table_names()) == {
        "alembic_version",
        "runs",
        "run_steps",
        "workers",
        "component_reports",
        "fake_settings",
        "city_datasets",
        "package_fingerprints",
        "city_instances",
        "instance_versions",
        "instance_periods",
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
        "component_reports",
        "fake_settings",
        "city_datasets",
        "package_fingerprints",
        "city_instances",
        "instance_versions",
        "instance_periods",
    }
    assert StorageProbe(migrated_database).check().state is ComponentState.AVAILABLE


def test_applying_the_migrations_twice_changes_nothing(migrated_database: Engine) -> None:
    migrate_to_head()

    assert StorageProbe(migrated_database).check().state is ComponentState.AVAILABLE


def test_the_fake_settings_table_is_empty_after_the_migrations(migrated_database: Engine) -> None:
    with migrated_database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM fake_settings")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM component_reports")).scalar_one() == 0


def test_the_fake_settings_table_holds_one_row_at_most(migrated_database: Engine) -> None:
    with migrated_database.begin() as connection:
        connection.execute(text("INSERT INTO fake_settings (id, settings) VALUES (1, '{}')"))

    with pytest.raises(IntegrityError), migrated_database.begin() as connection:
        connection.execute(text("INSERT INTO fake_settings (id, settings) VALUES (2, '{}')"))
