from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from pricing_demo.application.ports.bus_shape_matcher import MatchedShapes
from pricing_demo.domain.city_datasets import BoundingBox


@dataclass(frozen=True)
class TimetableFacts:
    valid_from: date
    valid_to: date
    timezone: str
    stops_bbox: BoundingBox


class TimetableReader(Protocol):
    def read(self, gtfs_zip: Path) -> TimetableFacts:
        """Raises InvalidTimetable when the validity, the time zone or the stops are missing."""
        ...


class StreetExtract(Protocol):
    def bounds(self, osm_dir: Path) -> BoundingBox:
        """The bounding box of the one `.osm.pbf` in the folder.

        Raises StreetExtractNotFound unless there is exactly one.
        """
        ...

    def file(self, osm_dir: Path) -> Path:
        """The one `.osm.pbf` in the folder; the same refusal as `bounds`."""
        ...


class TimetableShapes(Protocol):
    def add_bus_shapes(self, gtfs_zip: Path, shapes: MatchedShapes) -> int:
        """Rewrite the zip in place with `shapes.txt` and the `shape_id` of the bus trips.

        Returns the number of bus trips given a shape; writes nothing when it is 0.
        """
        ...


class DatasetFiles(Protocol):
    def claim(self, dataset_id: str) -> bool:
        """Create the data set's folder; False when it exists already (another run's)."""
        ...

    def copy_in(self, dataset_id: str, source: Path) -> Path:
        """Copy into the data set's folder; returns the path relative to the data directory."""
        ...

    def folder(self, dataset_id: str) -> Path:
        """The data set's folder, created when missing."""
        ...

    def resolve(self, relative: str) -> Path:
        """The absolute path of a path relative to the data directory."""
        ...

    def relative(self, path: Path) -> str: ...

    def sha256(self, path: Path) -> str: ...

    def remove(self, dataset_id: str) -> None: ...
