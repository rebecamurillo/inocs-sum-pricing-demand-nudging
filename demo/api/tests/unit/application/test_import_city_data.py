import hashlib
import zipfile
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from pricing_demo.application.errors import (
    BikeStationFetchFailed,
    InvalidTimetable,
    StreetExtractNotFound,
)
from pricing_demo.application.ports.bike_station_feed import FetchedStations
from pricing_demo.application.ports.bus_shape_matcher import BusShapeMatcher, MatchedShapes
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.domain.city_datasets import (
    GENEVA_PRESET,
    NO_BUS_SHAPE_REASON,
    BoundingBox,
    BusShapes,
    DisjointAreas,
)
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader, ZipTimetableShapes
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.fakes.bike_station_feed import SOURCE_URL, FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import (
    FAKE_SHAPE_TOOL_IMAGE,
    FakeBusShapeMatcher,
)
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets
from pricing_demo.infrastructure.fakes.clock import FixedClock
from tests.support.city_data import osm_folder, zip_gtfs

NOW = datetime(2026, 11, 26, 9, 30, tzinfo=UTC)


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.data_dir = tmp_path / "data"
        self.datasets = InMemoryCityDatasets()
        self.clock = FixedClock(NOW)
        self.feed = FixtureBikeStationFeed()
        self.gtfs = zip_gtfs(tmp_path / "source" / "tpg_gtfs.zip")
        self.osm = osm_folder(tmp_path / "osm")

    def use_case(
        self, feed: object | None = None, matcher: BusShapeMatcher | None = None
    ) -> ImportCityData:
        return ImportCityData(
            self.datasets,
            ZipTimetableReader(),
            PbfStreetExtract(),
            LocalDatasetFiles(self.data_dir),
            feed or self.feed,  # type: ignore[arg-type]
            matcher or FakeBusShapeMatcher(),
            ZipTimetableShapes(),
            self.clock,
        )

    def folders(self) -> list[str]:
        root = self.data_dir / "datasets"
        return sorted(path.name for path in root.iterdir()) if root.exists() else []


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_the_import_creates_the_data_set_with_every_recorded_fact(rig: Rig) -> None:
    dataset = rig.use_case().execute(rig.gtfs, rig.osm)

    assert dataset.id == "geneva-2026-11-26"
    assert dataset.name == "Geneva · tpg + Donkey Republic"
    assert dataset.gtfs.valid_from == date(2024, 12, 15)
    assert dataset.gtfs.valid_to == date(2025, 12, 13)
    assert dataset.gtfs.timezone == "Europe/Zurich"
    assert dataset.gtfs.operator == "Test Transport"
    assert dataset.available_area == BoundingBox(6.10, 46.15, 6.20, 46.25)
    assert dataset.preset == GENEVA_PRESET
    moment = dataset.routing_moment
    assert (moment.date, moment.time, moment.arrive_by, moment.provisional) == (
        date(2025, 3, 10),
        time(8, 30),
        True,
        True,
    )
    assert dataset.gbfs.source_url == SOURCE_URL
    assert dataset.gbfs.fetched_at == NOW
    assert rig.datasets.list() == [dataset]


def test_the_files_are_copied_and_both_hashes_are_recorded(rig: Rig) -> None:
    dataset = rig.use_case().execute(rig.gtfs, rig.osm)

    copy = rig.data_dir / dataset.gtfs.file
    assert dataset.gtfs.file == "datasets/geneva-2026-11-26/tpg_gtfs.zip"
    assert dataset.gtfs.source_sha256 == hashlib.sha256(rig.gtfs.read_bytes()).hexdigest()
    assert dataset.gtfs.sha256 == hashlib.sha256(copy.read_bytes()).hexdigest()
    stations = rig.data_dir / dataset.gbfs.file
    assert dataset.gbfs.file == "datasets/geneva-2026-11-26/gbfs_station_information.json"
    assert dataset.gbfs.sha256 == hashlib.sha256(stations.read_bytes()).hexdigest()


def test_a_second_import_on_the_same_day_gets_a_suffix(rig: Rig) -> None:
    rig.use_case().execute(rig.gtfs, rig.osm)
    second = rig.use_case().execute(rig.gtfs, rig.osm)
    third = rig.use_case().execute(rig.gtfs, rig.osm)

    assert (second.id, third.id) == ("geneva-2026-11-26-2", "geneva-2026-11-26-3")
    assert rig.folders() == ["geneva-2026-11-26", "geneva-2026-11-26-2", "geneva-2026-11-26-3"]


@pytest.mark.parametrize("names", [(), ("a.osm.pbf", "b.osm.pbf")])
def test_a_wrong_number_of_extracts_writes_nothing(rig: Rig, names: tuple[str, ...]) -> None:
    folder = osm_folder(rig.osm.parent / "other", names)

    with pytest.raises(StreetExtractNotFound):
        rig.use_case().execute(rig.gtfs, folder)

    assert rig.datasets.count() == 0
    assert rig.folders() == []
    assert rig.feed.fetches == 0


def test_an_invalid_timetable_writes_nothing(rig: Rig, tmp_path: Path) -> None:
    bad = zip_gtfs(tmp_path / "bad.zip", without=("feed_info.txt",))

    with pytest.raises(InvalidTimetable):
        rig.use_case().execute(bad, rig.osm)

    assert (rig.datasets.count(), rig.folders()) == (0, [])


def test_areas_that_do_not_overlap_write_nothing(rig: Rig, tmp_path: Path) -> None:
    class Elsewhere:
        def bounds(self, osm_dir: Path) -> BoundingBox:
            return BoundingBox(10.0, 40.0, 10.5, 40.5)

        def file(self, osm_dir: Path) -> Path:
            return osm_dir / "geneva.osm.pbf"

    use_case = ImportCityData(
        rig.datasets,
        ZipTimetableReader(),
        Elsewhere(),
        LocalDatasetFiles(rig.data_dir),
        rig.feed,
        FakeBusShapeMatcher(),
        ZipTimetableShapes(),
        rig.clock,
    )

    with pytest.raises(DisjointAreas):
        use_case.execute(rig.gtfs, rig.osm)

    assert (rig.datasets.count(), rig.folders()) == (0, [])


def test_a_failed_fetch_removes_the_folder_and_writes_no_row(rig: Rig) -> None:
    class Failing:
        def fetch(self, target_dir: Path) -> FetchedStations:
            raise BikeStationFetchFailed("The feed does not answer.")

    with pytest.raises(BikeStationFetchFailed, match="does not answer"):
        rig.use_case(Failing()).execute(rig.gtfs, rig.osm)

    assert rig.datasets.count() == 0
    assert rig.folders() == []


def test_a_folder_of_another_run_is_skipped_and_kept_when_the_import_fails(rig: Rig) -> None:
    other = rig.data_dir / "datasets" / "geneva-2026-11-26"
    other.mkdir(parents=True)
    (other / "tpg_gtfs.zip").write_bytes(b"another run's copy")

    dataset = rig.use_case().execute(rig.gtfs, rig.osm)

    assert dataset.id == "geneva-2026-11-26-2"
    assert (other / "tpg_gtfs.zip").read_bytes() == b"another run's copy"

    class Failing:
        def fetch(self, target_dir: Path) -> FetchedStations:
            raise BikeStationFetchFailed("The feed does not answer.")

    with pytest.raises(BikeStationFetchFailed):
        rig.use_case(Failing()).execute(rig.gtfs, rig.osm)

    assert rig.folders() == ["geneva-2026-11-26", "geneva-2026-11-26-2"]
    assert (other / "tpg_gtfs.zip").read_bytes() == b"another run's copy"


def entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def trips(path: Path) -> list[dict[str, str]]:
    import csv
    import io

    return list(csv.DictReader(io.StringIO(entries(path)["trips.txt"].decode("utf-8"))))


def test_the_copy_holds_shapes_for_the_bus_trips_only_and_the_hash_follows_the_rewrite(
    rig: Rig,
) -> None:
    dataset = rig.use_case().execute(rig.gtfs, rig.osm)

    copy = rig.data_dir / dataset.gtfs.file
    assert dataset.bus_shapes == BusShapes.generated(FAKE_SHAPE_TOOL_IMAGE)
    assert dataset.bus_shapes.reason is None
    after = entries(copy)
    assert "shapes.txt" in after
    assert [(row["trip_id"], row["shape_id"]) for row in trips(copy)] == [
        ("T1", "fake_T1"),
        ("T2", ""),
    ]
    assert {line.split(",")[0] for line in after["shapes.txt"].decode().splitlines()[1:]} == {
        "fake_T1"
    }
    assert dataset.gtfs.sha256 == hashlib.sha256(copy.read_bytes()).hexdigest()
    assert dataset.gtfs.sha256 != dataset.gtfs.source_sha256
    assert dataset.gtfs.source_sha256 == hashlib.sha256(rig.gtfs.read_bytes()).hexdigest()


def test_every_file_of_the_copy_but_trips_and_shapes_is_the_source_entry(rig: Rig) -> None:
    dataset = rig.use_case().execute(rig.gtfs, rig.osm)

    source = entries(rig.gtfs)
    copy = entries(rig.data_dir / dataset.gtfs.file)
    assert copy["stop_times.txt"] == source["stop_times.txt"]
    for name, content in source.items():
        if name != "trips.txt":
            assert copy[name] == content
    assert set(copy) == {*source, "shapes.txt"}


@pytest.mark.parametrize(
    "reason", ["Docker is not available: no such file", "pfaedle exited with 1: boom"]
)
def test_a_failing_matcher_leaves_the_copy_unchanged_and_records_the_reason(
    rig: Rig, reason: str
) -> None:
    dataset = rig.use_case(matcher=FakeBusShapeMatcher(fail_with=reason)).execute(rig.gtfs, rig.osm)

    assert dataset.bus_shapes == BusShapes.none(reason, FAKE_SHAPE_TOOL_IMAGE)
    assert (rig.data_dir / dataset.gtfs.file).read_bytes() == rig.gtfs.read_bytes()
    assert dataset.gtfs.sha256 == dataset.gtfs.source_sha256
    assert rig.datasets.list() == [dataset]


def test_a_matcher_that_produces_no_bus_shape_records_the_standard_reason(rig: Rig) -> None:
    class Empty:
        image = "empty-matcher"

        def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
            return MatchedShapes(b"shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n", {})

    dataset = rig.use_case(matcher=Empty()).execute(rig.gtfs, rig.osm)

    assert dataset.bus_shapes == BusShapes.none(NO_BUS_SHAPE_REASON, "empty-matcher")
    assert dataset.bus_shapes.reason == "no bus shape was produced"
    assert dataset.gtfs.sha256 == dataset.gtfs.source_sha256
    assert (rig.data_dir / dataset.gtfs.file).read_bytes() == rig.gtfs.read_bytes()


def test_a_matcher_that_fails_in_another_way_removes_the_folder(rig: Rig) -> None:
    class Crashing:
        image = "crashing-matcher"

        def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
            raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError):
        rig.use_case(matcher=Crashing()).execute(rig.gtfs, rig.osm)

    assert (rig.datasets.count(), rig.folders()) == (0, [])


def test_the_matcher_runs_on_the_copy_and_the_extract(rig: Rig) -> None:
    seen: list[tuple[Path, Path]] = []

    class Spy(FakeBusShapeMatcher):
        def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
            seen.append((gtfs_zip, osm_file))
            return super().match(gtfs_zip, osm_file)

    dataset = rig.use_case(matcher=Spy()).execute(rig.gtfs, rig.osm)

    assert seen == [(rig.data_dir / dataset.gtfs.file, rig.osm / "geneva.osm.pbf")]
