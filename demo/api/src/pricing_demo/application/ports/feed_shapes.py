from typing import Protocol

from pricing_demo.domain.city_datasets import CityDataset


class FeedShapes(Protocol):
    def routes_with_shapes(self, dataset: CityDataset) -> frozenset[str]:
        """The public codes (`route_short_name`) of the routes that have at least one trip
        with a shape in the data set's timetable."""
        ...
