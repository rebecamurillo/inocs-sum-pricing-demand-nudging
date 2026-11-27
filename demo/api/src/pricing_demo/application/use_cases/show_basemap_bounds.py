from dataclasses import dataclass

from pricing_demo.application.errors import NoCityDataYet, UnknownCityDataset
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.domain.city_datasets import BoundingBox


@dataclass(frozen=True)
class BasemapBounds:
    dataset_id: str
    area: BoundingBox


class ShowBasemapBounds:
    """The data set a basemap is cut for and its available area's bounding box."""

    def __init__(self, datasets: CityDatasets) -> None:
        self._datasets = datasets

    def execute(self, dataset_id: str | None) -> BasemapBounds:
        if dataset_id is None:
            latest = self._datasets.latest()
            if latest is None:
                raise NoCityDataYet
            dataset = latest
        else:
            found = self._datasets.get(dataset_id)
            if found is None:
                raise UnknownCityDataset(dataset_id)
            dataset = found
        return BasemapBounds(dataset.id, dataset.available_area)
