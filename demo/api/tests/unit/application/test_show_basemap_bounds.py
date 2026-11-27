from datetime import timedelta

import pytest

from pricing_demo.application.errors import NoCityDataYet, UnknownCityDataset
from pricing_demo.application.use_cases.show_basemap_bounds import ShowBasemapBounds
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from tests.support.runs import T0


def two_datasets() -> InMemoryCityDatasets:
    datasets = InMemoryCityDatasets()
    datasets.add(fake_city_dataset("earlier", T0))
    datasets.add(fake_city_dataset("later", T0 + timedelta(days=1)))
    return datasets


def test_the_latest_data_set_is_the_default() -> None:
    bounds = ShowBasemapBounds(two_datasets()).execute(None)

    assert bounds.dataset_id == "later"
    assert bounds.area == fake_city_dataset("later", T0).available_area


def test_a_named_data_set_is_used() -> None:
    assert ShowBasemapBounds(two_datasets()).execute("earlier").dataset_id == "earlier"


def test_no_data_set_at_all_is_refused() -> None:
    with pytest.raises(NoCityDataYet):
        ShowBasemapBounds(InMemoryCityDatasets()).execute(None)


def test_an_unknown_data_set_is_refused() -> None:
    with pytest.raises(UnknownCityDataset):
        ShowBasemapBounds(two_datasets()).execute("nope")
