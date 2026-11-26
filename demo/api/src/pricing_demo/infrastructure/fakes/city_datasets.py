from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime

from pricing_demo.domain.city_datasets import (
    GENEVA_NAME,
    GENEVA_PRESET,
    GENEVA_ROUTING_MOMENT,
    BoundingBox,
    CityDataset,
    GbfsSnapshot,
    GtfsSnapshot,
)


class InMemoryCityDatasets:
    """The data sets in a list; passes the same contract suite as the PostgreSQL one."""

    def __init__(self) -> None:
        self._datasets: list[CityDataset] = []

    def clear(self) -> None:
        self._datasets.clear()

    def add(self, dataset: CityDataset) -> None:
        if any(item.id == dataset.id for item in self._datasets):
            raise ValueError(f"The city data set {dataset.id} exists.")
        self._datasets.append(dataset)

    def list(self) -> Sequence[CityDataset]:
        return sorted(self._datasets, key=lambda item: item.created_at)

    def latest(self) -> CityDataset | None:
        ordered = self.list()
        return ordered[-1] if ordered else None

    def ids_starting_with(self, prefix: str) -> Collection[str]:
        return {item.id for item in self._datasets if item.id.startswith(prefix)}

    def count(self) -> int:
        return len(self._datasets)


def fake_city_dataset(dataset_id: str, now: datetime) -> CityDataset:
    """The data set the e2e suite inserts: no file behind it, an area that covers the preset."""
    return CityDataset(
        id=dataset_id,
        name=GENEVA_NAME,
        gtfs=GtfsSnapshot(
            file=f"datasets/{dataset_id}/tpg_gtfs.zip",
            sha256="0" * 64,
            source_sha256="0" * 64,
            valid_from=date(2024, 12, 15),
            valid_to=date(2025, 12, 13),
            timezone="Europe/Zurich",
        ),
        gbfs=GbfsSnapshot(
            file=f"datasets/{dataset_id}/gbfs_station_information.json",
            sha256="0" * 64,
            source_url="https://stables.donkey.bike/api/public/gbfs/2/donkey_ge/gbfs.json",
            fetched_at=datetime(2026, 11, 10, tzinfo=UTC),
        ),
        available_area=BoundingBox(min_lon=6.05, min_lat=46.12, max_lon=6.25, max_lat=46.29),
        preset=GENEVA_PRESET,
        routing_moment=GENEVA_ROUTING_MOMENT,
        created_at=now,
    )
