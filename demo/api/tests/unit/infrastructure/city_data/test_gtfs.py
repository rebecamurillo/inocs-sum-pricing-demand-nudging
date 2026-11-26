import csv
import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from pricing_demo.application.errors import InvalidTimetable
from pricing_demo.application.ports.bus_shape_matcher import MatchedShapes
from pricing_demo.domain.city_datasets import BoundingBox
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader, ZipTimetableShapes
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


SHAPES = (
    b"shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
    b"s1,46.20,6.10,1\ns1,46.25,6.20,2\ns9,46.0,6.0,1\n"
)


def entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def csv_rows(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def test_only_the_bus_trips_get_a_shape_and_shapes_txt_keeps_the_referenced_ones(
    tmp_path: Path,
) -> None:
    feed = zip_gtfs(tmp_path / "feed.zip")

    count = ZipTimetableShapes().add_bus_shapes(
        feed, MatchedShapes(SHAPES, {"T1": "s1", "T2": "s9"})
    )

    after = entries(feed)
    assert count == 1
    assert csv_rows(after["trips.txt"]) == [
        {"route_id": "R1", "service_id": "WD", "trip_id": "T1", "shape_id": "s1"},
        {"route_id": "R2", "service_id": "WD", "trip_id": "T2", "shape_id": ""},
    ]
    assert after["shapes.txt"] == (
        b"shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\ns1,46.20,6.10,1\ns1,46.25,6.20,2\n"
    )


def test_every_other_entry_is_byte_identical_and_in_the_same_order(tmp_path: Path) -> None:
    source = zip_gtfs(tmp_path / "source.zip")
    feed = zip_gtfs(tmp_path / "feed.zip")
    before = entries(source)

    ZipTimetableShapes().add_bus_shapes(feed, MatchedShapes(SHAPES, {"T1": "s1"}))

    after = entries(feed)
    for name, content in before.items():
        if name != "trips.txt":
            assert after[name] == content
    assert after["stop_times.txt"] == before["stop_times.txt"]
    assert names(feed) == [*names(source), "shapes.txt"]


def test_an_existing_shape_id_column_is_overwritten_and_a_present_shapes_file_replaced(
    tmp_path: Path,
) -> None:
    feed = tmp_path / "feed.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("routes.txt", "route_id,route_type\nR1,3\n")
        archive.writestr("trips.txt", "route_id,trip_id,shape_id,service_id\nR1,T1,old,WD\n")
        archive.writestr("shapes.txt", "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n")

    ZipTimetableShapes().add_bus_shapes(feed, MatchedShapes(SHAPES, {"T1": "s1"}))

    after = entries(feed)
    assert names(feed) == ["routes.txt", "trips.txt", "shapes.txt"]
    assert csv_rows(after["trips.txt"]) == [
        {"route_id": "R1", "trip_id": "T1", "shape_id": "s1", "service_id": "WD"}
    ]
    assert b"s1,46.20,6.10,1" in after["shapes.txt"]


def test_extended_bus_route_types_are_shaped(tmp_path: Path) -> None:
    feed = tmp_path / "feed.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("routes.txt", "route_id,route_type\nR1,714\nR2,900\n")
        archive.writestr("trips.txt", "route_id,trip_id\nR1,T1\nR2,T2\n")

    count = ZipTimetableShapes().add_bus_shapes(
        feed, MatchedShapes(SHAPES, {"T1": "s1", "T2": "s1"})
    )

    assert count == 1
    assert [row["shape_id"] for row in csv_rows(entries(feed)["trips.txt"])] == ["s1", ""]


def test_without_a_bus_trip_the_zip_is_not_touched(tmp_path: Path) -> None:
    feed = zip_gtfs(tmp_path / "feed.zip")
    before = feed.read_bytes()

    count = ZipTimetableShapes().add_bus_shapes(feed, MatchedShapes(SHAPES, {"T2": "s9"}))

    assert count == 0
    assert feed.read_bytes() == before
    assert [path.name for path in tmp_path.iterdir()] == ["feed.zip"]


def test_the_shaped_copy_keeps_the_file_mode_of_the_copy_it_replaces(tmp_path: Path) -> None:
    feed = zip_gtfs(tmp_path / "feed.zip")
    feed.chmod(0o644)

    ZipTimetableShapes().add_bus_shapes(feed, MatchedShapes(SHAPES, {"T1": "s1"}))

    assert feed.stat().st_mode & 0o777 == 0o644
