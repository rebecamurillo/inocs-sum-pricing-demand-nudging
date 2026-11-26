import csv
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

from pricing_demo.application.errors import InvalidTimetable
from pricing_demo.application.ports.city_source_files import TimetableFacts
from pricing_demo.domain.city_datasets import BoundingBox


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
            zones = {
                (row.get("agency_timezone") or "").strip() for row in _rows(archive, "agency.txt")
            }
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
        lons = [lon for lon, _ in coordinates]
        lats = [lat for _, lat in coordinates]
        return TimetableFacts(
            valid_from=valid_from,
            valid_to=valid_to,
            timezone=zones.pop(),
            stops_bbox=BoundingBox(min(lons), min(lats), max(lons), max(lats)),
        )
