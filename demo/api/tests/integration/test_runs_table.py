import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, insert, inspect
from sqlalchemy.exc import IntegrityError

from pricing_demo.infrastructure.persistence.metadata import metadata
from pricing_demo.infrastructure.persistence.tables import run_steps, runs
from tests.support.runs import T0

pytestmark = pytest.mark.integration


def values(run_id: str, **fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": run_id,
        "kind": "build",
        "instance_version_id": "geneva-3km.v1",
        "state": "queued",
        "queued_at": T0,
    }
    return {**base, **fields}


def insert_run(engine: Engine, run_id: str, **fields: object) -> None:
    with engine.begin() as connection:
        connection.execute(insert(runs).values(values(run_id, **fields)))


@pytest.mark.parametrize("first", ["queued", "running"])
@pytest.mark.parametrize("second", ["queued", "running"])
def test_one_queued_or_running_run_per_subject(
    migrated_database: Engine, first: str, second: str
) -> None:
    insert_run(migrated_database, "r1", state=first)

    with pytest.raises(IntegrityError):
        insert_run(migrated_database, "r2", state=second)


def test_the_unique_index_covers_pricing_subjects_too(migrated_database: Engine) -> None:
    pricing = {"kind": "pricing", "instance_version_id": None, "pricing_version_id": "g.v1.A"}
    insert_run(migrated_database, "r1", **pricing)

    with pytest.raises(IntegrityError):
        insert_run(migrated_database, "r2", **{**pricing, "kind": "simulation"})


def test_another_subject_is_accepted(migrated_database: Engine) -> None:
    insert_run(migrated_database, "r1")

    insert_run(migrated_database, "r2", instance_version_id="geneva-5km.v1")


@pytest.mark.parametrize("finished", ["succeeded", "failed", "cancelled"])
def test_a_finished_run_leaves_the_subject_free(migrated_database: Engine, finished: str) -> None:
    insert_run(migrated_database, "r1", state=finished)

    insert_run(migrated_database, "r2")
    insert_run(migrated_database, "r3", state=finished)


@pytest.mark.parametrize(
    "fields",
    [
        {"pricing_version_id": "g.v1.A"},
        {"instance_version_id": None},
        {"kind": "pricing"},
        {"kind": "simulation"},
        {"kind": "pricing", "instance_version_id": "g.v1", "pricing_version_id": "g.v1.A"},
        {"kind": "pricing", "instance_version_id": None, "pricing_version_id": None},
    ],
)
def test_the_subject_must_match_the_kind(
    migrated_database: Engine, fields: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        insert_run(migrated_database, "r1", **fields)


@pytest.mark.parametrize("fields", [{"kind": "other"}, {"state": "paused"}])
def test_kind_and_state_are_enumerated(
    migrated_database: Engine, fields: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        insert_run(migrated_database, "r1", **fields)


def test_a_step_is_unique_by_run_and_position_and_enumerated(migrated_database: Engine) -> None:
    insert_run(migrated_database, "r1")
    step = {"run_id": "r1", "position": 1, "step": "area", "state": "pending"}
    with migrated_database.begin() as connection:
        connection.execute(insert(run_steps).values(step))
    for bad in (
        step,
        {**step, "position": 2, "step": "other"},
        {**step, "position": 2, "state": "x"},
    ):
        with pytest.raises(IntegrityError), migrated_database.begin() as connection:
            connection.execute(insert(run_steps).values(bad))


def test_a_step_needs_a_run(migrated_database: Engine) -> None:
    with pytest.raises(IntegrityError), migrated_database.begin() as connection:
        connection.execute(
            insert(run_steps).values(run_id="none", position=1, step="area", state="pending")
        )


def test_the_migration_creates_the_tables_of_the_metadata(migrated_database: Engine) -> None:
    with migrated_database.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)

    assert differences == []
    checks = {
        table: {item["name"] for item in inspect(migrated_database).get_check_constraints(table)}
        for table in ("runs", "run_steps")
    }
    assert checks == {
        "runs": {"ck_runs_kind", "ck_runs_state", "ck_runs_kind_subject"},
        "run_steps": {"ck_run_steps_step", "ck_run_steps_state"},
    }
    (index,) = inspect(migrated_database).get_indexes("runs")
    assert index["name"] == "uq_runs_active_subject"
    assert index["unique"]


def test_a_run_names_a_known_worker(migrated_database: Engine) -> None:
    with pytest.raises(IntegrityError):
        insert_run(migrated_database, "r1", worker_id="no-such-worker")
