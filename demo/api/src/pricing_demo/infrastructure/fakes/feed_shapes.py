from collections.abc import Collection

from pricing_demo.domain.city_datasets import CityDataset


class FakeFeedShapes:
    """The same codes for every data set."""

    def __init__(self, codes: Collection[str]) -> None:
        self._codes = frozenset(codes)

    def routes_with_shapes(self, dataset: CityDataset) -> frozenset[str]:
        return self._codes
