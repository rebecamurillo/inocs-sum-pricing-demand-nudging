import zipfile
from datetime import date
from pathlib import Path

import pytest

from pricing_demo.application.errors import InvalidTimetable
from pricing_demo.domain.city_datasets import BoundingBox
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader
from tests.support.city_data import GTFS_FILES, zip_gtfs


def test_the_validity_the_time_zone_and_the_stops_box_are_read(tmp_path: Path) -> None:
    facts = ZipTimetableReader().read(zip_gtfs(tmp_path / "feed.zip"))

    assert facts.valid_from == date(2024, 12, 15)
    assert facts.valid_to == date(2025, 12, 13)
    assert facts.timezone == "Europe/Zurich"
    # S4 has no coordinates and is ignored.
    assert facts.stops_bbox == BoundingBox(6.10, 46.15, 6.20, 46.25)


@pytest.mark.parametrize("missing", ["feed_info.txt", "agency.txt", "stops.txt"])
def test_a_feed_without_a_needed_file_is_refused(tmp_path: Path, missing: str) -> None:
    with pytest.raises(InvalidTimetable, match=missing):
        ZipTimetableReader().read(zip_gtfs(tmp_path / "feed.zip", without=(missing,)))


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    (tmp_path / "feed.zip").write_text("not a zip")

    with pytest.raises(InvalidTimetable, match="zip"):
        ZipTimetableReader().read(tmp_path / "feed.zip")


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(InvalidTimetable):
        ZipTimetableReader().read(tmp_path / "absent.zip")


def test_an_agency_row_without_a_time_zone_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "src"
    for path in GTFS_FILES.glob("*.txt"):
        (source / path.name).parent.mkdir(parents=True, exist_ok=True)
        (source / path.name).write_bytes(path.read_bytes())
    agency = (source / "agency.txt").read_text().splitlines()
    (source / "agency.txt").write_text("\n".join([*agency, "short"]) + "\n")
    feed = tmp_path / "feed.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        for path in sorted(source.glob("*.txt")):
            archive.write(path, path.name)

    with pytest.raises(InvalidTimetable, match="agency_timezone"):
        ZipTimetableReader().read(feed)
