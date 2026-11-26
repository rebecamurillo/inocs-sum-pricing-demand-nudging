from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MatchedShapes:
    """The tool's `shapes.txt` and the shape it gave each trip (trip_id -> shape_id)."""

    shapes_txt: bytes
    trip_shapes: Mapping[str, str]


class BusShapeMatcher(Protocol):
    @property
    def image(self) -> str:
        """The reference of the tool, recorded on the data set."""
        ...

    def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
        """Draw the trips of the timetable on the streets of the extract.

        Raises BusShapeMatchingFailed when the tool cannot run or produces nothing.
        """
        ...
