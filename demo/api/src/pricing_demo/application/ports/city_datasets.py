from collections.abc import Collection, Sequence
from typing import Protocol

from pricing_demo.domain.city_datasets import CityDataset


class CityDatasets(Protocol):
    def add(self, dataset: CityDataset) -> None: ...

    def list(self) -> Sequence[CityDataset]:
        """Every data set, oldest `created_at` first."""
        ...

    def latest(self) -> CityDataset | None: ...

    def ids_starting_with(self, prefix: str) -> Collection[str]: ...

    def count(self) -> int: ...
