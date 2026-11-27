"""What the database itself guarantees about instances, versions, periods and the fingerprint."""

import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from pricing_demo.application.use_cases.record_package_fingerprint import RecordPackageFingerprint
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.domain.city_instances import (
    CityInstance,
    DraftExists,
    InstanceVersion,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.fakes.build_sources import InMemoryBuildSources
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    FakePackageFingerprintReader,
)
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.package_fingerprints import (
    PostgresPackageFingerprints,
)
from pricing_demo.infrastructure.persistence.tables import run_steps, runs
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.worker.main import build_worker
from tests.support.builds import postgres_built, postgres_planning
from tests.support.instances import ensure_instance_versions
from tests.support.runs import T0, later

pytestmark = pytest.mark.integration

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)


def create(engine: Engine, slug: str = "geneva-3km") -> PostgresCityInstances:
    store = PostgresCityInstances(engine)
    if PostgresCityDatasets(engine).get(DATASET.id) is None:
        PostgresCityDatasets(engine).add(DATASET)
    draft = InstanceVersion(f"{slug}.v1", slug, 1, None, "draft", PARAMETERS, T0)
    store.create(
        CityInstance(slug, slug, DATASET.id, 2, T0), draft, first_period(draft.id, DATASET)
    )
    return store


def seal(engine: Engine, version: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE instance_versions SET status = 'sealed', sealed_at = :at WHERE id = :id"),
            {"at": later(1), "id": version},
        )


def test_a_draft_can_be_sealed_and_a_draft_changes_freely(migrated_database: Engine) -> None:
    create(migrated_database)

    with migrated_database.begin() as connection:
        connection.execute(text("UPDATE instance_versions SET seed = 7, radius_m = 4000"))
    seal(migrated_database, "geneva-3km.v1")

    with migrated_database.connect() as connection:
        row = connection.execute(text("SELECT status, seed, radius_m FROM instance_versions")).one()
    assert tuple(row) == ("sealed", 7, 4000)


@pytest.mark.parametrize(
    "column",
    [
        "center_lat",
        "center_lon",
        "radius_m",
        "clustering_threshold_m",
        "clustering_buffer_m",
        "min_od_distance_m",
        "seed",
        "fixed_capacity",
        "min_demand",
        "max_demand",
        "min_inventory_pct",
        "max_inventory_pct",
        "min_park_time_min",
        "max_park_time_min",
    ],
)
def test_a_sealed_version_refuses_an_update_of_any_parameter(
    migrated_database: Engine, column: str
) -> None:
    create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")

    with pytest.raises(DBAPIError, match="cannot change"), migrated_database.begin() as connection:
        connection.execute(text(f"UPDATE instance_versions SET {column} = {column} + 1"))

    with migrated_database.connect() as connection:
        assert connection.execute(
            text(f"SELECT {column} FROM instance_versions")
        ).scalar_one() == getattr(PARAMETERS, column)


def test_a_sealed_version_still_accepts_an_update_that_leaves_its_parameters_alone(
    migrated_database: Engine,
) -> None:
    create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")

    with migrated_database.begin() as connection:
        connection.execute(
            text("UPDATE instance_versions SET seed = seed, sealed_at = :at"), {"at": later(9)}
        )
        connection.execute(text("UPDATE instance_versions SET based_on_id = NULL"))


INSERT_VERSION = (
    "INSERT INTO instance_versions (id, instance_id, number, status, center_lat, center_lon, "
    "radius_m, clustering_threshold_m, clustering_buffer_m, min_od_distance_m, seed, "
    "fixed_capacity, min_demand, max_demand, min_inventory_pct, max_inventory_pct, "
    "min_park_time_min, max_park_time_min, created_at) "
    "SELECT :id, instance_id, :number, :status, center_lat, center_lon, radius_m, "
    "clustering_threshold_m, clustering_buffer_m, min_od_distance_m, seed, fixed_capacity, "
    "min_demand, max_demand, min_inventory_pct, max_inventory_pct, min_park_time_min, "
    "max_park_time_min, created_at FROM instance_versions WHERE id = 'geneva-3km.v1'"
)


def test_one_draft_per_instance(migrated_database: Engine) -> None:
    create(migrated_database)

    with (
        pytest.raises(IntegrityError, match="uq_instance_versions_one_draft"),
        migrated_database.begin() as connection,
    ):
        connection.execute(
            text(INSERT_VERSION), {"id": "geneva-3km.v2", "number": 2, "status": "draft"}
        )


def test_an_instance_may_have_many_sealed_versions_and_one_draft(
    migrated_database: Engine,
) -> None:
    create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")

    with migrated_database.begin() as connection:
        for number, status in ((2, "sealed"), (3, "sealed"), (4, "draft")):
            connection.execute(
                text(INSERT_VERSION),
                {"id": f"geneva-3km.v{number}", "number": number, "status": status},
            )


def test_a_version_number_is_unique_within_its_instance(migrated_database: Engine) -> None:
    create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")

    with (
        pytest.raises(IntegrityError, match="uq_instance_versions_instance_id"),
        migrated_database.begin() as connection,
    ):
        connection.execute(
            text(INSERT_VERSION), {"id": "geneva-3km.again", "number": 1, "status": "sealed"}
        )


def test_a_second_draft_through_the_adapter_is_refused_and_a_sealed_one_allows_it(
    migrated_database: Engine,
) -> None:
    store = create(migrated_database)

    with pytest.raises(DraftExists):
        store.create_draft(
            "geneva-3km", "geneva-3km.v1", PARAMETERS, later(1), lambda v: first_period(v, DATASET)
        )
    seal(migrated_database, "geneva-3km.v1")
    draft = store.create_draft(
        "geneva-3km", "geneva-3km.v1", PARAMETERS, later(1), lambda v: first_period(v, DATASET)
    )

    assert draft.id == "geneva-3km.v2"


def test_two_drafts_created_at_once_give_one_draft_and_one_refusal(
    migrated_database: Engine,
) -> None:
    store = create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def make() -> None:
        barrier.wait(timeout=10)
        try:
            outcomes.append(
                store.create_draft(
                    "geneva-3km",
                    "geneva-3km.v1",
                    PARAMETERS,
                    later(1),
                    lambda v: first_period(v, DATASET),
                )
            )
        except DraftExists as error:
            outcomes.append(error)

    threads = [threading.Thread(target=make) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(type(item).__name__ for item in outcomes) == ["DraftExists", "InstanceVersion"]
    assert (store.get_instance("geneva-3km") or CityInstance("", "", "", 0, T0)).next_number == 3


def test_numbers_are_never_reused_after_a_discard(migrated_database: Engine) -> None:
    store = create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")
    period = lambda v: first_period(v, DATASET)  # noqa: E731
    second = store.create_draft("geneva-3km", "geneva-3km.v1", PARAMETERS, later(1), period)
    store.delete_draft(second.id)

    third = store.create_draft("geneva-3km", "geneva-3km.v1", PARAMETERS, later(2), period)

    assert (second.number, third.number) == (2, 3)


def test_deleting_a_draft_removes_its_periods_and_an_only_version_removes_the_instance(
    migrated_database: Engine,
) -> None:
    store = create(migrated_database)

    store.delete_draft("geneva-3km.v1")

    with migrated_database.connect() as connection:
        for table in ("city_instances", "instance_versions", "instance_periods"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0


def test_deleting_the_version_a_draft_is_based_on_clears_the_base(
    migrated_database: Engine,
) -> None:
    store = create(migrated_database)
    seal(migrated_database, "geneva-3km.v1")
    store.create_draft(
        "geneva-3km", "geneva-3km.v1", PARAMETERS, later(1), lambda v: first_period(v, DATASET)
    )

    with migrated_database.begin() as connection:
        connection.execute(text("DELETE FROM instance_versions WHERE id = 'geneva-3km.v1'"))

    version = store.get_version("geneva-3km.v2")
    assert version is not None
    assert version.based_on_id is None


def test_two_patches_of_different_parameters_sent_at_once_both_stay(
    migrated_database: Engine,
) -> None:
    store = create(migrated_database)
    update = UpdateInstanceVersion(
        store,
        PostgresCityDatasets(migrated_database),
        postgres_planning(migrated_database, InMemoryBuildSources()),
        postgres_built(migrated_database),
    )
    errors: list[BaseException] = []

    def patch(changes: dict[str, int]) -> None:
        try:
            update.execute("geneva-3km.v1", changes)
        except BaseException as error:  # reported by the assertion below
            errors.append(error)

    threads = [
        threading.Thread(target=patch, args=({"seed": 7},)),
        threading.Thread(target=patch, args=({"radius_m": 3000},)),
    ]
    # Both requests read the draft while another transaction holds its row, then wait for it.
    with migrated_database.begin() as holder:
        holder.execute(text("SELECT 1 FROM instance_versions FOR UPDATE"))
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with migrated_database.connect() as connection:
                waiting = connection.execute(
                    text("SELECT count(*) FROM pg_locks WHERE NOT granted")
                ).scalar_one()
            if waiting >= 2:
                break
            time.sleep(0.05)
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    version = store.get_version("geneva-3km.v1")
    assert version is not None
    assert (version.parameters.seed, version.parameters.radius_m) == (7, 3000)


def test_a_status_is_draft_or_sealed(migrated_database: Engine) -> None:
    create(migrated_database)

    with pytest.raises(IntegrityError), migrated_database.begin() as connection:
        connection.execute(text("UPDATE instance_versions SET status = 'open'"))


def test_a_run_naming_an_unknown_instance_version_is_refused(migrated_database: Engine) -> None:
    with (
        pytest.raises(IntegrityError, match="fk_runs_instance_version_id"),
        migrated_database.begin() as connection,
    ):
        connection.execute(
            insert(runs).values(
                id="r1",
                kind="build",
                instance_version_id="nowhere.v1",
                state="queued",
                queued_at=T0,
            )
        )


def test_a_run_naming_a_known_instance_version_is_accepted(migrated_database: Engine) -> None:
    ensure_instance_versions(migrated_database, ["geneva-3km.v1"])

    with migrated_database.begin() as connection:
        connection.execute(
            insert(runs).values(
                id="r1",
                kind="build",
                instance_version_id="geneva-3km.v1",
                state="queued",
                queued_at=T0,
            )
        )


def test_a_step_naming_an_unknown_period_is_refused(migrated_database: Engine) -> None:
    ensure_instance_versions(migrated_database, ["geneva-3km.v1"])
    with migrated_database.begin() as connection:
        connection.execute(
            insert(runs).values(
                id="r1",
                kind="build",
                instance_version_id="geneva-3km.v1",
                state="queued",
                queued_at=T0,
            )
        )

    step = {"run_id": "r1", "position": 1, "step": "area", "state": "pending"}
    with (
        pytest.raises(IntegrityError, match="fk_run_steps_period_id"),
        migrated_database.begin() as connection,
    ):
        connection.execute(insert(run_steps).values({**step, "period_id": "nowhere.v1.mon-08"}))

    ensure_instance_versions(migrated_database, [], ["geneva-3km.v1.mon-08"])
    with migrated_database.begin() as connection:
        connection.execute(insert(run_steps).values({**step, "period_id": "geneva-3km.v1.mon-08"}))


def test_a_started_worker_records_the_fingerprint_row_and_names_it(
    integration_database_url: str, migrated_database: Engine, tmp_path: Path
) -> None:
    built = build_worker(
        Settings(database_url=integration_database_url, adapters="fake", data_dir=tmp_path / "data")
    )
    try:
        built.worker.start()
    finally:
        built.engine.dispose()

    assert PostgresPackageFingerprints(migrated_database).latest() == FAKE_FINGERPRINT
    with migrated_database.connect() as connection:
        named = connection.execute(text("SELECT package_fingerprint FROM workers")).scalar_one()
    assert named == FAKE_FINGERPRINT.fingerprint


def test_the_fingerprint_comes_back_after_the_rows_were_truncated(
    migrated_database: Engine,
) -> None:
    store = PostgresPackageFingerprints(migrated_database)
    record = RecordPackageFingerprint(FakePackageFingerprintReader(), store, FixedClock(T0))
    registry = PostgresWorkerRegistry(migrated_database)
    registry.register("w-1", "h", 1, T0, record.execute())

    with migrated_database.begin() as connection:
        connection.execute(text("TRUNCATE workers, package_fingerprints CASCADE"))
    assert store.latest() is None
    registry.heartbeat("w-1", "h", 1, T0, later(5), record.execute())

    assert store.latest() == FAKE_FINGERPRINT
    with migrated_database.connect() as connection:
        named = connection.execute(text("SELECT package_fingerprint FROM workers")).scalar_one()
    assert named == FAKE_FINGERPRINT.fingerprint
