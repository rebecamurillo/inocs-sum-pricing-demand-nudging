import hashlib
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from pricing_demo.application.errors import (
    BikeStationFetchFailed,
    InvalidTimetable,
    StreetExtractNotFound,
)
from pricing_demo.application.ports.bike_station_feed import FetchedStations
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.domain.city_datasets import GENEVA_PRESET, BoundingBox, DisjointAreas
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.fakes.bike_station_feed import SOURCE_URL, FixtureBikeStationFeed
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

    def use_case(self, feed: object | None = None) -> ImportCityData:
        return ImportCityData(
            self.datasets,
            ZipTimetableReader(),
            PbfStreetExtract(),
            LocalDatasetFiles(self.data_dir),
            feed or self.feed,  # type: ignore[arg-type]
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
    assert copy.read_bytes() == rig.gtfs.read_bytes()
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

    use_case = ImportCityData(
        rig.datasets,
        ZipTimetableReader(),
        Elsewhere(),
        LocalDatasetFiles(rig.data_dir),
        rig.feed,
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
