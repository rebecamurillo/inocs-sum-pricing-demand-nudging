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
PRICING_VERSIONS = "f2c6a9d4b871"
# Story 3-3: the solves, the simulations and the links of a pricing version to them.
NEW_TABLES = (
    "solves",
    "solve_rows",
    "solve_ods",
    "simulations",
    "simulation_modes",
    "simulation_choices",
    "simulation_pairs",
    "simulation_stations",
    "pricing_version_simulations",
    # Story 3-6: the numbers of a result, and the one showcase mark.
    "result_summaries",
    "showcase",
)
RESULT_SUMMARIES = "e6c1b4a8f209"


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
        "artifacts",
        "instance_version_steps",
        "stations",
        "hubs",
        "station_hubs",
        "hub_pairs",
        "route_options",
        "station_bikes",
        "option_station_deltas",
        "route_failures",
        "route_pairs",
        "pricing_versions",
        "pricing_version_periods",
        *NEW_TABLES,
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
        "artifacts",
        "instance_version_steps",
        "stations",
        "hubs",
        "station_hubs",
        "hub_pairs",
        "route_options",
        "station_bikes",
        "option_station_deltas",
        "route_failures",
        "route_pairs",
        "pricing_versions",
        "pricing_version_periods",
        *NEW_TABLES,
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


def test_the_solves_and_simulations_migration_goes_down_and_up_again(
    migrated_database: Engine,
) -> None:
    command.downgrade(Config(str(ALEMBIC_INI)), PRICING_VERSIONS)

    tables = set(inspect(migrated_database).get_table_names())
    assert not tables & set(NEW_TABLES)
    assert "simulation_rule" not in {
        column["name"] for column in inspect(migrated_database).get_columns("workers")
    }

    migrate_to_head()

    assert set(NEW_TABLES) <= set(inspect(migrated_database).get_table_names())
    assert "simulation_rule" in {
        column["name"] for column in inspect(migrated_database).get_columns("workers")
    }


def test_the_solves_are_unique_per_pricing_version_and_period(migrated_database: Engine) -> None:
    constraints = inspect(migrated_database).get_unique_constraints("solves")

    assert [item["column_names"] for item in constraints] == [["pricing_version_id", "period_id"]]


def test_an_artefact_of_the_pricing_model_step_is_accepted_and_another_name_is_not(
    migrated_database: Engine,
) -> None:
    checks = inspect(migrated_database).get_check_constraints("artifacts")

    (step_check,) = [item for item in checks if item["name"] == "ck_artifacts_step"]
    assert "pricing_model" in step_check["sqltext"]
    assert "traveller_simulation" not in step_check["sqltext"]


def test_the_result_summaries_and_showcase_migration_goes_down_and_up_again(
    migrated_database: Engine,
) -> None:
    command.downgrade(Config(str(ALEMBIC_INI)), RESULT_SUMMARIES)

    tables = set(inspect(migrated_database).get_table_names())
    assert not tables & {"result_summaries", "showcase"}

    migrate_to_head()

    inspector = inspect(migrated_database)
    assert {"result_summaries", "showcase"} <= set(inspector.get_table_names())
    assert {column["name"] for column in inspector.get_columns("result_summaries")} == {
        "solve_key",
        "derivation_version",
        "numbers",
        "package_summary",
        "objective_residual",
        "created_at",
    }
    assert {column["name"] for column in inspector.get_columns("showcase")} == {
        "id",
        "pricing_version_id",
        "period_id",
        "marked_at",
    }


def test_the_showcase_table_holds_one_row_at_most(migrated_database: Engine) -> None:
    from tests.support.pricing_versions import insert_pricing_version

    version = insert_pricing_version(migrated_database)
    period = f"{version.rsplit('.', 1)[0]}.mon-08"
    insert = (
        "INSERT INTO showcase (id, pricing_version_id, period_id, marked_at) "
        "VALUES ({id}, '{version}', '{period}', now())"
    )
    with migrated_database.begin() as connection:
        connection.execute(text(insert.format(id=1, version=version, period=period)))

    with pytest.raises(IntegrityError), migrated_database.begin() as connection:
        connection.execute(text(insert.format(id=2, version=version, period=period)))
