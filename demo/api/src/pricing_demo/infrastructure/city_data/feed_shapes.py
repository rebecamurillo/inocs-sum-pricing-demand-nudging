import zipfile
from pathlib import Path

from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.infrastructure.city_data.gtfs import _rows


class GtfsFeedShapes:
    """The routes of a data set's timetable copy that have a shape, found once per data set."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._cache: dict[str, frozenset[str]] = {}

    def routes_with_shapes(self, dataset: CityDataset) -> frozenset[str]:
        if dataset.id not in self._cache:
            self._cache[dataset.id] = self._read(self._data_dir / dataset.gtfs.file)
        return self._cache[dataset.id]

    @staticmethod
    def _read(gtfs_zip: Path) -> frozenset[str]:
        with zipfile.ZipFile(gtfs_zip) as archive:
            shaped = {
                row["route_id"]
                for row in _rows(archive, "trips.txt")
                if (row.get("shape_id") or "").strip()
            }
            return frozenset(
                row["route_short_name"]
                for row in _rows(archive, "routes.txt")
                if row["route_id"] in shaped and row.get("route_short_name")
            )
