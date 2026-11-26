"""The Artifacts port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.artifacts import Artifact, Artifacts, StoredFile
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.runs import T0

FINGERPRINT = FAKE_FINGERPRINT.fingerprint
PERIOD = "a.v1.mon-08"


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Iterator[Artifacts]:
    if request.param == "fake":
        yield InMemoryArtifacts()
        return
    from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
    from pricing_demo.infrastructure.persistence.package_fingerprints import (
        PostgresPackageFingerprints,
    )
    from tests.support.instances import ensure_instance_versions

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresPackageFingerprints(engine).record(FAKE_FINGERPRINT, T0)
    ensure_instance_versions(engine, ["a.v1", "a.v2"], periods=[PERIOD, "a.v2.mon-08"])
    yield PostgresArtifacts(engine)


def artifact(key: str, step: StepName = StepName.AREA, path: str | None = None) -> Artifact:
    return Artifact(
        input_key=key,
        step=step,
        inputs={"step": step.value, "parameters": {"radius_m": 3000, "ratio": 0.5}},
        files=(
            StoredFile("stations.json", "ab" * 32, 120),
            StoredFile("hubs.geojson", "cd" * 32, 7),
        ),
        path=path or f"artifacts/{step.value}/{key}",
        package_fingerprint=FINGERPRINT,
        created_at=T0,
    )


def test_an_artefact_is_read_back_as_it_was_added(store: Artifacts) -> None:
    store.add(artifact("k1"))

    assert store.get("k1") == artifact("k1")


def test_an_unknown_key_has_no_artefact(store: Artifacts) -> None:
    assert store.get("nope") is None


def test_the_stored_keys_are_those_of_the_keys_that_have_an_artefact(store: Artifacts) -> None:
    store.add(artifact("k1"))
    store.add(artifact("k2", StepName.HUBS))

    assert store.stored_keys(["k1", "k3", "k2"]) == {"k1", "k2"}
    assert store.stored_keys([]) == set()
    assert store.stored_keys(["k3"]) == set()


def test_adding_a_key_that_is_stored_leaves_the_first_artefact(store: Artifacts) -> None:
    store.add(artifact("k1", path="first"))

    store.add(artifact("k1", path="second"))

    stored = store.get("k1")
    assert stored is not None
    assert stored.path == "first"


def test_a_link_names_the_artefact_of_a_step_of_a_version(store: Artifacts) -> None:
    store.add(artifact("k1"))
    store.add(artifact("k3", StepName.ROUTES))

    store.link("a.v1", StepName.AREA, None, "k1")
    store.link("a.v1", StepName.ROUTES, PERIOD, "k3")

    assert store.links_of("a.v1") == {StepName.AREA: "k1", StepName.ROUTES: "k3"}
    assert store.links_of("a.v2") == {}


def test_a_new_link_replaces_the_artefact_of_the_step_whether_its_period_is_null_or_not(
    store: Artifacts,
) -> None:
    for key, step in (
        ("k1", StepName.AREA),
        ("k2", StepName.AREA),
        ("k3", StepName.ROUTES),
        ("k4", StepName.ROUTES),
    ):
        store.add(artifact(key, step))
    store.link("a.v1", StepName.AREA, None, "k1")
    store.link("a.v1", StepName.ROUTES, PERIOD, "k3")

    store.link("a.v1", StepName.AREA, None, "k2")
    store.link("a.v1", StepName.ROUTES, PERIOD, "k4")

    assert store.links_of("a.v1") == {StepName.AREA: "k2", StepName.ROUTES: "k4"}


def test_two_versions_link_the_same_artefact(store: Artifacts) -> None:
    store.add(artifact("k1"))

    store.link("a.v1", StepName.AREA, None, "k1")
    store.link("a.v2", StepName.AREA, None, "k1")

    assert store.links_of("a.v1") == store.links_of("a.v2") == {StepName.AREA: "k1"}
