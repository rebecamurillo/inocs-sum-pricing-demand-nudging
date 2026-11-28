from collections.abc import Sequence

from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.domain.city_datasets import CityDataset


class ListCityDatasets:
    def __init__(self, datasets: CityDatasets) -> None:
        self._datasets = datasets

    def execute(self) -> Sequence[CityDataset]:
        return self._datasets.list()
