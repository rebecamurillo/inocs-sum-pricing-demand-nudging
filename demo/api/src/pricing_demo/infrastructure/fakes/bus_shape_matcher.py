import csv
import io
import zipfile
from pathlib import Path

from pricing_demo.application.errors import BusShapeMatchingFailed
from pricing_demo.application.ports.bus_shape_matcher import MatchedShapes
from pricing_demo.domain.city_datasets import is_bus_route_type

FAKE_SHAPE_TOOL_IMAGE = "fake-bus-shape-matcher"
SHAPES_HEADER = ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]


def _rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))


class FakeBusShapeMatcher:
    """Gives every bus trip one shape through its stops, in stop order; needs no Docker."""

    image = FAKE_SHAPE_TOOL_IMAGE

    def __init__(self, fail_with: str | None = None) -> None:
        self._fail_with = fail_with

    def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
        if self._fail_with is not None:
            raise BusShapeMatchingFailed(self._fail_with)
        with zipfile.ZipFile(gtfs_zip) as archive:
            bus_routes = {
                row["route_id"]
                for row in _rows(archive, "routes.txt")
                if is_bus_route_type(int(row["route_type"]))
            }
            bus_trips = [
                row["trip_id"]
                for row in _rows(archive, "trips.txt")
                if row["route_id"] in bus_routes
            ]
            stops = {row["stop_id"]: row for row in _rows(archive, "stops.txt")}
            stop_times = _rows(archive, "stop_times.txt")
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(SHAPES_HEADER)
        trip_shapes: dict[str, str] = {}
        for trip_id in bus_trips:
            visits = sorted(
                (row for row in stop_times if row["trip_id"] == trip_id),
                key=lambda row: int(row["stop_sequence"]),
            )
            points = [stops[row["stop_id"]] for row in visits if stops[row["stop_id"]]["stop_lat"]]
            if not points:
                continue
            shape_id = f"fake_{trip_id}"
            trip_shapes[trip_id] = shape_id
            for sequence, stop in enumerate(points, start=1):
                writer.writerow([shape_id, stop["stop_lat"], stop["stop_lon"], sequence])
        return MatchedShapes(output.getvalue().encode("utf-8"), trip_shapes)
