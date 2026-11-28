from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pricing_demo.application.errors import BikeStationFetchFailed, GtfsCopyChanged, NoCityDataYet
from pricing_demo.application.ports.bike_station_feed import FetchedStations
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.application.use_cases.refresh_bike_stations import RefreshBikeStations
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader, ZipTimetableShapes
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
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
        self.files = LocalDatasetFiles(self.data_dir)
        self.matcher = FakeBusShapeMatcher()
        self.gtfs = zip_gtfs(tmp_path / "source" / "tpg_gtfs.zip")
        self.osm = osm_folder(tmp_path / "osm")

    def import_first(self) -> None:
        ImportCityData(
            self.datasets,
            ZipTimetableReader(),
            PbfStreetExtract(),
            self.files,
            self.feed,
            self.matcher,
            ZipTimetableShapes(),
            self.clock,
        ).execute(self.gtfs, self.osm)

    def refresh(self, feed: object | None = None) -> RefreshBikeStations:
        return RefreshBikeStations(
            self.datasets,
            self.files,
            feed or self.feed,  # type: ignore[arg-type]
            self.clock,
        )


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_without_a_data_set_the_refresh_says_no_city_data_is_imported(rig: Rig) -> None:
    with pytest.raises(NoCityDataYet, match="No city data is imported yet"):
        rig.refresh().execute()

    assert rig.feed.fetches == 0


def test_the_refresh_reuses_the_timetable_and_takes_a_new_snapshot(rig: Rig) -> None:
    rig.import_first()
    first = rig.datasets.latest()
    assert first is not None
    rig.clock.advance(timedelta(hours=2))

    new = rig.refresh().execute()

    assert new.id == "geneva-2026-11-26-2"
    assert new.gtfs.file == "datasets/geneva-2026-11-26-2/tpg_gtfs.zip"
    assert (rig.data_dir / new.gtfs.file).read_bytes() == (
        rig.data_dir / first.gtfs.file
    ).read_bytes()
    assert new.gtfs.sha256 == first.gtfs.sha256
    assert new.gtfs.source_sha256 == first.gtfs.source_sha256
    assert (new.gtfs.valid_from, new.gtfs.valid_to, new.gtfs.timezone) == (
        first.gtfs.valid_from,
        first.gtfs.valid_to,
        first.gtfs.timezone,
    )
    assert new.available_area == first.available_area
    assert new.preset == first.preset
    assert new.routing_moment == first.routing_moment
    assert new.gbfs.file == "datasets/geneva-2026-11-26-2/gbfs_station_information.json"
    assert new.gbfs.fetched_at == NOW + timedelta(hours=2)
    assert rig.feed.fetches == 2
    assert [item.id for item in rig.datasets.list()] == [first.id, new.id]


def test_the_feed_is_fetched_once_per_refresh(rig: Rig) -> None:
    rig.import_first()
    fetches = rig.feed.fetches

    rig.refresh().execute()

    assert rig.feed.fetches == fetches + 1


def test_a_failed_fetch_leaves_the_data_sets_and_folders_as_they_were(rig: Rig) -> None:
    rig.import_first()

    class Failing:
        def fetch(self, target_dir: Path) -> FetchedStations:
            raise BikeStationFetchFailed("The feed does not answer.")

    with pytest.raises(BikeStationFetchFailed):
        rig.refresh(Failing()).execute()

    assert rig.datasets.count() == 1
    assert sorted(path.name for path in (rig.data_dir / "datasets").iterdir()) == [
        "geneva-2026-11-26"
    ]


def test_a_timetable_copy_that_changed_on_disk_is_refused(rig: Rig) -> None:
    rig.import_first()
    first = rig.datasets.latest()
    assert first is not None
    (rig.data_dir / first.gtfs.file).write_bytes(b"tampered")

    with pytest.raises(GtfsCopyChanged):
        rig.refresh().execute()

    assert rig.datasets.count() == 1
    assert not (rig.data_dir / "datasets" / "geneva-2026-11-26-2").exists()


@pytest.mark.parametrize("failing", [False, True])
def test_the_refresh_carries_the_bus_shapes_of_the_data_it_reuses(rig: Rig, failing: bool) -> None:
    if failing:
        rig.matcher = FakeBusShapeMatcher(fail_with="Docker is not available")
    rig.import_first()
    first = rig.datasets.latest()
    assert first is not None

    new = rig.refresh().execute()

    assert new.bus_shapes == first.bus_shapes
    assert new.bus_shapes.status == ("none" if failing else "generated")
