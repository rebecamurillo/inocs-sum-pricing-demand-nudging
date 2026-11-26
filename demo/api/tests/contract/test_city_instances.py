"""The CityInstances port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.domain.city_instances import (
    CityInstance,
    CityInstanceNameTaken,
    CityInstanceNotFound,
    DraftExists,
    InstanceParameters,
    InstanceVersion,
    InstanceVersionNotFound,
    VersionSealed,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.runs import T0, later

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)


@dataclass
class Store:
    port: CityInstances
    seal: Callable[[str], None]


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Iterator[Store]:
    if request.param == "fake":
        fake = InMemoryCityInstances()
        yield Store(fake, lambda version: fake.seal(version, later(1)))
        return
    from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
    from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresCityDatasets(engine).add(DATASET)

    def seal(version: str) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE instance_versions SET status = 'sealed', sealed_at = :at WHERE id = :id"
                ),
                {"at": later(1), "id": version},
            )

    yield Store(PostgresCityInstances(engine), seal)


def instance(name: str = "Geneva 3 km", slug: str = "geneva-3km", age: int = 0) -> CityInstance:
    return CityInstance(slug, name, DATASET.id, 2, T0 + timedelta(seconds=age))


def draft(slug: str = "geneva-3km", parameters: InstanceParameters = PARAMETERS) -> InstanceVersion:
    return InstanceVersion(f"{slug}.v1", slug, 1, None, "draft", parameters, T0)


def create(store: Store, name: str = "Geneva 3 km", slug: str = "geneva-3km", age: int = 0) -> None:
    version = draft(slug)
    store.port.create(instance(name, slug, age), version, first_period(version.id, DATASET))


def new_draft(store: Store, based_on: str = "geneva-3km.v1") -> InstanceVersion:
    return store.port.create_draft(
        "geneva-3km", based_on, PARAMETERS, later(10), lambda v: first_period(v, DATASET)
    )


def test_nothing_is_stored_at_first(store: Store) -> None:
    assert store.port.menu() == []
    assert store.port.get_instance("geneva-3km") is None
    assert store.port.get_version("geneva-3km.v1") is None
    assert store.port.periods_of("geneva-3km.v1") == []


def test_an_instance_is_read_back_with_its_draft_and_period(store: Store) -> None:
    create(store)

    assert store.port.get_instance("geneva-3km") == instance()
    assert store.port.get_version("geneva-3km.v1") == draft()
    assert store.port.periods_of("geneva-3km.v1") == [first_period("geneva-3km.v1", DATASET)]


def test_a_used_id_or_name_is_refused_and_stores_nothing(store: Store) -> None:
    create(store)

    with pytest.raises(CityInstanceNameTaken):
        create(store, name="Other name")
    with pytest.raises(CityInstanceNameTaken):
        create(store, slug="other-slug")
    assert len(store.port.menu()) == 1


def test_a_draft_takes_the_next_number_and_a_second_draft_is_refused(store: Store) -> None:
    create(store)
    store.seal("geneva-3km.v1")

    second = new_draft(store)

    assert (second.id, second.number, second.based_on_id) == ("geneva-3km.v2", 2, "geneva-3km.v1")
    assert store.port.periods_of("geneva-3km.v2") == [first_period("geneva-3km.v2", DATASET)]
    assert (store.port.get_instance("geneva-3km") or instance()).next_number == 3
    with pytest.raises(DraftExists) as raised:
        new_draft(store)
    assert raised.value.draft_id == "geneva-3km.v2"
    assert (store.port.get_instance("geneva-3km") or instance()).next_number == 3


def test_a_discarded_number_is_not_used_again(store: Store) -> None:
    create(store)
    store.seal("geneva-3km.v1")
    second = new_draft(store)
    store.port.delete_draft(second.id)

    third = new_draft(store)

    assert third.id == "geneva-3km.v3"
    assert store.port.get_version("geneva-3km.v2") is None


def test_a_draft_of_an_unknown_instance_is_refused(store: Store) -> None:
    with pytest.raises(CityInstanceNotFound):
        new_draft(store)


def test_a_draft_updates_its_parameters(store: Store) -> None:
    create(store)
    changed = replace(PARAMETERS, seed=1.5, radius_m=6000)

    stored = store.port.update_draft_parameters("geneva-3km.v1", {"seed": 1.5, "radius_m": 6000})

    assert stored.parameters == changed
    assert store.port.get_version("geneva-3km.v1") == replace(draft(), parameters=changed)


def test_an_update_leaves_the_parameters_it_does_not_name_as_stored(store: Store) -> None:
    create(store)
    store.port.update_draft_parameters("geneva-3km.v1", {"seed": 7})

    stored = store.port.update_draft_parameters("geneva-3km.v1", {"radius_m": 3000})

    assert stored.parameters == replace(PARAMETERS, seed=7, radius_m=3000)


def test_a_sealed_version_is_refused_an_update_and_a_delete(store: Store) -> None:
    create(store)
    store.seal("geneva-3km.v1")

    with pytest.raises(VersionSealed):
        store.port.update_draft_parameters("geneva-3km.v1", {"seed": 1})
    with pytest.raises(VersionSealed):
        store.port.delete_draft("geneva-3km.v1")

    version = store.port.get_version("geneva-3km.v1")
    assert version is not None
    assert version.parameters == PARAMETERS


def test_an_unknown_version_is_not_found(store: Store) -> None:
    with pytest.raises(InstanceVersionNotFound):
        store.port.update_draft_parameters("x.v1", {"seed": 1})
    with pytest.raises(InstanceVersionNotFound):
        store.port.delete_draft("x.v1")


def test_discarding_the_only_version_deletes_the_instance_and_its_period(store: Store) -> None:
    create(store)

    store.port.delete_draft("geneva-3km.v1")

    assert store.port.get_instance("geneva-3km") is None
    assert store.port.periods_of("geneva-3km.v1") == []
    assert store.port.menu() == []


def test_discarding_a_draft_keeps_the_instance_that_has_other_versions(store: Store) -> None:
    create(store)
    store.seal("geneva-3km.v1")
    second = new_draft(store)

    store.port.delete_draft(second.id)

    assert store.port.get_instance("geneva-3km") is not None
    (entry,) = store.port.menu()
    assert [version.id for version in entry.versions] == ["geneva-3km.v1"]


def test_the_menu_lists_instances_oldest_first_with_versions_by_number(store: Store) -> None:
    create(store, name="Zurich", slug="zurich", age=0)
    create(store, name="Annecy", slug="annecy", age=5)
    create(store, age=9)
    store.seal("geneva-3km.v1")
    new_draft(store)

    menu = store.port.menu()

    assert [entry.instance.id for entry in menu] == ["zurich", "annecy", "geneva-3km"]
    assert [version.number for version in menu[2].versions] == [1, 2]
    assert [version.status for version in menu[2].versions] == ["sealed", "draft"]
