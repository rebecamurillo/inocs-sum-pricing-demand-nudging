"""The ReadModel port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.read_model import IngestionBatch, ReadModel
from pricing_demo.domain import read_model as rows
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.read_model import InMemoryReadModel
from tests.support.city_files import FakeCity
from tests.support.runs import T0


@dataclass
class Store:
    read_model: ReadModel
    # PostgreSQL keeps a foreign key from every row to its artefact.
    add_artifact: Callable[[str, StepName], None]
    # The `bike_legs` kept for each option (arc id) of a key: the port has no reader for options.
    bike_legs_of: Callable[[str], dict[str, int | None]]


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Store:
    if request.param == "fake":
        memory = InMemoryReadModel()
        return Store(
            memory,
            lambda key, step: None,
            lambda key: {
                item.arc_id: item.bike_legs for item in memory._batches[key].route_options
            },
        )
    from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
    from pricing_demo.infrastructure.persistence.package_fingerprints import (
        PostgresPackageFingerprints,
    )
    from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresPackageFingerprints(engine).record(FAKE_FINGERPRINT, T0)
    artifacts = PostgresArtifacts(engine)

    def add_artifact(key: str, step: StepName) -> None:
        artifacts.add(
            Artifact(
                key, step, {}, (), f"artifacts/{step.value}/{key}", FAKE_FINGERPRINT.fingerprint, T0
            )
        )

    def bike_legs_of(key: str) -> dict[str, int | None]:
        with engine.connect() as connection:
            found = connection.execute(
                sa.text("select arc_id, bike_legs from route_options where instance_key = :key"),
                {"key": key},
            )
            return {str(row[0]): row[1] for row in found}

    return Store(PostgresReadModel(engine), add_artifact, bike_legs_of)


@pytest.fixture
def city(tmp_path: Path) -> FakeCity:
    return FakeCity(tmp_path)


def hubs_batch(city: FakeCity, key: str = "k-hubs") -> IngestionBatch:
    hubs = rows.hubs_from(city.files["hubs.geojson"], city.files["hub_polygons.geojson"])
    return IngestionBatch(
        key,
        StepName.HUBS,
        rows.hubs_counts(hubs),
        hubs=hubs,
        station_hubs=rows.station_hubs_from(city.files["stations_hubs.geojson"]),
    )


def test_an_artefact_that_is_not_ingested_is_reported_so(store: Store) -> None:
    store.add_artifact("k-hubs", StepName.HUBS)

    assert store.read_model.is_ingested("k-hubs") is False
    assert store.read_model.counts_of(["k-hubs"]) == {}
    assert store.read_model.hubs("k-hubs") == []


def test_an_ingested_batch_is_read_back_in_id_order_with_its_counts(
    store: Store, city: FakeCity
) -> None:
    store.add_artifact("k-hubs", StepName.HUBS)
    batch = hubs_batch(city)

    store.read_model.ingest(batch)

    assert store.read_model.is_ingested("k-hubs") is True
    assert store.read_model.counts_of(["k-hubs", "other"]) == {"k-hubs": {"hubs": 6}}
    assert store.read_model.hubs("k-hubs") == list(batch.hubs)
    assert [item.hub_id for item in store.read_model.hubs("k-hubs")] == [
        "H1",
        "H2",
        "H3",
        "H4",
        "H5",
        "H6",
    ]


def test_stations_and_hub_pairs_are_read_back_in_order(store: Store, city: FakeCity) -> None:
    store.add_artifact("k-area", StepName.AREA)
    store.add_artifact("k-instance", StepName.TRAVELLERS_AND_BIKES)
    stations = rows.stations_from(city.files["stations.json"])
    pairs = rows.hub_pairs_from(city.files["Instance_1.json"])

    store.read_model.ingest(IngestionBatch("k-area", StepName.AREA, {}, stations=stations))
    store.read_model.ingest(
        IngestionBatch("k-instance", StepName.TRAVELLERS_AND_BIKES, {}, hub_pairs=pairs)
    )

    assert store.read_model.stations("k-area") == list(stations)
    assert store.read_model.hub_pairs("k-instance") == list(pairs)


def test_the_last_step_stores_every_table_of_its_instance(store: Store, city: FakeCity) -> None:
    store.add_artifact("k-instance", StepName.TRAVELLERS_AND_BIKES)
    instance = city.files["Instance_1.json"]
    batch = IngestionBatch(
        "k-instance",
        StepName.TRAVELLERS_AND_BIKES,
        rows.instance_counts(instance),
        hub_pairs=rows.hub_pairs_from(instance),
        route_options=rows.route_options_from(
            city.files["od_routes.json"], city.files["od_geometry.json"], instance, {"1"}
        ),
        station_bikes=rows.station_bikes_from(instance),
        deltas=rows.deltas_from(instance),
    )

    store.read_model.ingest(batch)

    assert store.read_model.counts_of(["k-instance"])["k-instance"]["options"] == {
        "pt_bike": 23,
        "pt_only": 24,
        "car": 24,
    }
    assert len(store.read_model.hub_pairs("k-instance")) == 24


def test_a_stored_route_option_keeps_its_bike_legs(store: Store, city: FakeCity) -> None:
    store.add_artifact("k-instance", StepName.TRAVELLERS_AND_BIKES)
    instance = city.files["Instance_1.json"]
    options = rows.route_options_from(
        city.files["od_routes.json"],
        city.files["od_geometry.json"],
        instance,
        {"1"},
        city.files["option_bike_legs.json"],
    )

    store.read_model.ingest(
        IngestionBatch(
            "k-instance",
            StepName.TRAVELLERS_AND_BIKES,
            rows.instance_counts(instance),
            route_options=options,
        )
    )

    kept = store.bike_legs_of("k-instance")
    assert kept == city.files["option_bike_legs.json"]
    assert {legs for arc, legs in kept.items() if arc.endswith("b")} == {1}
    assert {legs for arc, legs in kept.items() if not arc.endswith("b")} == {0}


def test_ingesting_a_key_again_replaces_its_rows(store: Store, city: FakeCity) -> None:
    store.add_artifact("k-hubs", StepName.HUBS)
    batch = hubs_batch(city)
    store.read_model.ingest(batch)

    store.read_model.ingest(
        IngestionBatch("k-hubs", StepName.HUBS, {"hubs": 5}, hubs=batch.hubs[:5])
    )

    assert len(store.read_model.hubs("k-hubs")) == 5
    assert store.read_model.counts_of(["k-hubs"]) == {"k-hubs": {"hubs": 5}}


def test_the_rows_of_two_keys_stay_apart(store: Store, city: FakeCity) -> None:
    store.add_artifact("k-hubs", StepName.HUBS)
    store.add_artifact("k-other", StepName.HUBS)
    store.read_model.ingest(hubs_batch(city))
    store.read_model.ingest(hubs_batch(city, "k-other"))

    store.read_model.ingest(IngestionBatch("k-other", StepName.HUBS, {"hubs": 0}))

    assert len(store.read_model.hubs("k-hubs")) == 6
    assert store.read_model.hubs("k-other") == []
