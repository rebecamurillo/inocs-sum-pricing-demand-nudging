from datetime import timedelta

from pricing_demo.application.use_cases.list_city_datasets import ListCityDatasets
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from tests.support.runs import T0


def test_no_data_set_lists_nothing() -> None:
    assert ListCityDatasets(InMemoryCityDatasets()).execute() == []


def test_the_data_sets_come_oldest_first() -> None:
    datasets = InMemoryCityDatasets()
    datasets.add(fake_city_dataset("later", T0 + timedelta(days=1)))
    datasets.add(fake_city_dataset("earlier", T0))

    assert [item.id for item in ListCityDatasets(datasets).execute()] == ["earlier", "later"]
