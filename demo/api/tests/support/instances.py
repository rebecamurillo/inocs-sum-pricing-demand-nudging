"""Instance versions for the tests that insert runs: a run's subject is a foreign key now."""

from collections.abc import Iterable

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.domain.city_instances import (
    InstanceParameters,
    InstanceVersion,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.runs import Run, RunKind
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import (
    period_values,
    version_values,
)
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.tables import (
    city_instances,
    instance_periods,
    instance_versions,
)
from tests.support.runs import T0

SEED_DATASET_ID = "seed-dataset"


def seed_parameters() -> InstanceParameters:
    dataset = fake_city_dataset(SEED_DATASET_ID, T0)
    return parameters_from_defaults(FAKE_FINGERPRINT.defaults, dataset.preset)


def ensure_instance_versions(
    engine: Engine, ids: Iterable[str], periods: Iterable[str] = ()
) -> None:
    """Insert the data set, the instances and the sealed versions the ids name (`a.v1` is
    version 1 of instance `a`), and the periods (`a.v1.mon-08` belongs to `a.v1`). What
    exists is left as it is."""
    datasets = PostgresCityDatasets(engine)
    dataset = fake_city_dataset(SEED_DATASET_ID, T0)
    if datasets.get(SEED_DATASET_ID) is None:
        datasets.add(dataset)
    version_ids = set(ids) | {period.rsplit(".", 1)[0] for period in periods}
    with engine.begin() as connection:
        for version in sorted(version_ids):
            instance_id, number = version.rsplit(".v", 1)
            connection.execute(
                insert(city_instances)
                .values(
                    id=instance_id,
                    name=instance_id,
                    dataset_id=SEED_DATASET_ID,
                    next_number=100,
                    created_at=T0,
                )
                .on_conflict_do_nothing()
            )
            sealed = InstanceVersion(
                version, instance_id, int(number), None, "sealed", seed_parameters(), T0, T0
            )
            connection.execute(
                insert(instance_versions).values(version_values(sealed)).on_conflict_do_nothing()
            )
        for period_id in sorted(set(periods)):
            version = period_id.rsplit(".", 1)[0]
            period = first_period(version, dataset)
            connection.execute(
                insert(instance_periods).values(period_values(period)).on_conflict_do_nothing()
            )


class SeedingRunRepository(PostgresRunRepository):
    """The PostgreSQL run repository that first inserts the versions and periods a run names."""

    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self._seed_engine = engine

    def add(self, run: Run) -> None:
        versions = [run.subject.id] if run.kind is RunKind.BUILD else []
        periods = [item.period for item in run.steps if item.period]
        ensure_instance_versions(self._seed_engine, versions, periods)
        super().add(run)
