"""The CityDatasets port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta

import pytest

from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from tests.support.runs import T0


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def datasets(request: pytest.FixtureRequest) -> Iterator[CityDatasets]:
    if request.param == "fake":
        yield InMemoryCityDatasets()
    else:
        from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets

        yield PostgresCityDatasets(request.getfixturevalue("migrated_database"))


def dataset(dataset_id: str, age_s: int = 0) -> CityDataset:
    return fake_city_dataset(dataset_id, T0 + timedelta(seconds=age_s))


def test_nothing_is_stored_at_first(datasets: CityDatasets) -> None:
    assert datasets.count() == 0
    assert datasets.list() == []
    assert datasets.latest() is None
    assert datasets.ids_starting_with("geneva") == set()


def test_a_data_set_is_read_back_unchanged(datasets: CityDatasets) -> None:
    stored = replace(dataset("geneva-2026-11-26"), name="Geneva · tpg + Donkey Republic")

    datasets.add(stored)

    assert datasets.list() == [stored]
    assert datasets.latest() == stored
    assert datasets.count() == 1


def test_the_data_sets_are_listed_oldest_first_and_the_latest_is_the_newest(
    datasets: CityDatasets,
) -> None:
    datasets.add(dataset("b", 20))
    datasets.add(dataset("a", 10))
    datasets.add(dataset("c", 30))

    assert [item.id for item in datasets.list()] == ["a", "b", "c"]
    latest = datasets.latest()
    assert latest is not None
    assert latest.id == "c"


def test_ids_are_found_by_prefix_only(datasets: CityDatasets) -> None:
    for name in ("geneva-2026-11-26", "geneva-2026-11-26-2", "geneva-2026-11-27", "other"):
        datasets.add(dataset(name))

    assert datasets.ids_starting_with("geneva-2026-11-26") == {
        "geneva-2026-11-26",
        "geneva-2026-11-26-2",
    }


def test_a_prefix_is_not_a_pattern(datasets: CityDatasets) -> None:
    datasets.add(dataset("geneva-2026"))

    assert datasets.ids_starting_with("geneva_2026") == set()
    assert datasets.ids_starting_with("%") == set()


def test_an_id_cannot_be_stored_twice(datasets: CityDatasets) -> None:
    datasets.add(dataset("a"))

    with pytest.raises(Exception):  # noqa: B017, PT011  # ValueError in memory, IntegrityError in SQL
        datasets.add(dataset("a"))

    assert datasets.count() == 1
