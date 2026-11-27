import csv
import io
import os
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

from pricing_demo.application.errors import InvalidTimetable
from pricing_demo.application.ports.bus_shape_matcher import MatchedShapes
from pricing_demo.application.ports.city_source_files import TimetableFacts
from pricing_demo.domain.city_datasets import BoundingBox, is_bus_route_type


def _rows(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        raw = archive.read(name)
    except KeyError:
        raise InvalidTimetable(f"The timetable has no {name}.") from None
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _day(value: str | None, field: str) -> date:
    try:
        return datetime.strptime((value or "").strip(), "%Y%m%d").date()
    except ValueError:
        raise InvalidTimetable(f"feed_info.txt has no valid {field}.") from None


class ZipTimetableReader:
    """Reads the facts the data set records from a GTFS zip: validity, time zone, stops box."""

    def read(self, gtfs_zip: Path) -> TimetableFacts:
        try:
            archive = zipfile.ZipFile(gtfs_zip)
        except (OSError, zipfile.BadZipFile) as error:
            raise InvalidTimetable(f"{gtfs_zip} is not a readable zip file: {error}") from error
        with archive:
            feed_info = _rows(archive, "feed_info.txt")
            if not feed_info:
                raise InvalidTimetable("feed_info.txt has no row.")
            valid_from = _day(feed_info[0].get("feed_start_date"), "feed_start_date")
            valid_to = _day(feed_info[0].get("feed_end_date"), "feed_end_date")
            # A short row reads as None in its missing fields.
            agencies = _rows(archive, "agency.txt")
            zones = {(row.get("agency_timezone") or "").strip() for row in agencies}
            if len(zones) != 1 or "" in zones:
                raise InvalidTimetable(
                    "agency.txt must give one agency_timezone shared by every agency."
                )
            coordinates = []
            for row in _rows(archive, "stops.txt"):
                try:
                    coordinates.append((float(row["stop_lon"]), float(row["stop_lat"])))
                except (KeyError, TypeError, ValueError):
                    continue
            if not coordinates:
                raise InvalidTimetable("stops.txt has no stop with coordinates.")
        names = list(
            dict.fromkeys(
                name for row in agencies if (name := (row.get("agency_name") or "").strip())
            )
        )
        lons = [lon for lon, _ in coordinates]
        lats = [lat for _, lat in coordinates]
        return TimetableFacts(
            valid_from=valid_from,
            valid_to=valid_to,
            timezone=zones.pop(),
            stops_bbox=BoundingBox(min(lons), min(lats), max(lons), max(lats)),
            operator=", ".join(names) or None,
        )


class ZipTimetableShapes:
    """Writes the tool's shapes and the bus trips' `shape_id` into a GTFS zip, nothing else."""

    def add_bus_shapes(self, gtfs_zip: Path, shapes: MatchedShapes) -> int:
        with zipfile.ZipFile(gtfs_zip) as archive:
            bus_routes = {
                row["route_id"]
                for row in _rows(archive, "routes.txt")
                if _is_bus(row.get("route_type"))
            }
            trips_text = archive.read("trips.txt").decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(trips_text))
            trips = list(reader)
            columns = list(reader.fieldnames or [])
            shaped = {
                row["trip_id"]: shapes.trip_shapes[row["trip_id"]]
                for row in trips
                if row.get("route_id") in bus_routes and row["trip_id"] in shapes.trip_shapes
            }
            if not shaped:
                return 0
            trips_out = _trips_with_shape_ids(columns, trips, shaped)
            shapes_out = _shapes_of(shapes.shapes_txt, set(shaped.values()))
            self._rewrite(gtfs_zip, archive, trips_out, shapes_out)
        return len(shaped)

    @staticmethod
    def _rewrite(gtfs_zip: Path, archive: zipfile.ZipFile, trips: bytes, shapes: bytes) -> None:
        handle, temporary = tempfile.mkstemp(dir=gtfs_zip.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as raw, zipfile.ZipFile(raw, "w") as target:
                for info in archive.infolist():
                    if info.filename == "shapes.txt":
                        continue
                    content = trips if info.filename == "trips.txt" else archive.read(info)
                    target.writestr(info.filename, content, compress_type=info.compress_type)
                target.writestr("shapes.txt", shapes, compress_type=zipfile.ZIP_DEFLATED)
            # mkstemp creates the file 0600; the shaped copy keeps the mode of the copy it replaces.
            os.chmod(temporary, gtfs_zip.stat().st_mode & 0o777)
            Path(temporary).replace(gtfs_zip)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def _is_bus(route_type: str | None) -> bool:
    try:
        return is_bus_route_type(int((route_type or "").strip()))
    except ValueError:
        return False


def _trips_with_shape_ids(
    columns: list[str], trips: list[dict[str, str]], shaped: dict[str, str]
) -> bytes:
    if "shape_id" not in columns:
        columns = [*columns, "shape_id"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in trips:
        writer.writerow({**row, "shape_id": shaped.get(row["trip_id"], "")})
    return output.getvalue().encode("utf-8")


def _shapes_of(shapes_txt: bytes, wanted: set[str]) -> bytes:
    reader = csv.DictReader(io.StringIO(shapes_txt.decode("utf-8-sig")))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames or [], lineterminator="\n")
    writer.writeheader()
    writer.writerows(row for row in reader if row["shape_id"] in wanted)
    return output.getvalue().encode("utf-8")
