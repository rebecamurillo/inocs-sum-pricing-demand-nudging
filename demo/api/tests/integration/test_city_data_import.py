"""The import and the refresh end to end on a migrated database, with local inputs."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine

from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.application.use_cases.refresh_bike_stations import RefreshBikeStations
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from tests.support.city_data import osm_folder, zip_gtfs

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 26, 9, 30, tzinfo=UTC)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_import_then_the_refresh_store_two_data_sets_that_share_the_timetable(
    migrated_database: Engine, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    datasets = PostgresCityDatasets(migrated_database)
    files = LocalDatasetFiles(data_dir)
    feed = FixtureBikeStationFeed()
    clock = FixedClock(NOW)
    gtfs = zip_gtfs(tmp_path / "source" / "tpg_gtfs.zip")

    first = ImportCityData(
        datasets, ZipTimetableReader(), PbfStreetExtract(), files, feed, clock
    ).execute(gtfs, osm_folder(tmp_path / "osm"))

    assert first.id == "geneva-2026-11-26"
    assert sorted(path.name for path in (data_dir / "datasets" / first.id).iterdir()) == [
        "gbfs_station_information.json",
        "tpg_gtfs.zip",
    ]
    assert first.gtfs.source_sha256 == sha(gtfs)
    assert first.gtfs.sha256 == sha(data_dir / first.gtfs.file)
    assert first.gbfs.sha256 == sha(data_dir / first.gbfs.file)

    second = RefreshBikeStations(datasets, files, feed, clock).execute()

    assert second.id == "geneva-2026-11-26-2"
    assert (second.gtfs.sha256, second.gtfs.source_sha256) == (
        first.gtfs.sha256,
        first.gtfs.source_sha256,
    )
    assert sha(data_dir / second.gtfs.file) == second.gtfs.sha256
    assert [item.id for item in datasets.list()] == [first.id, second.id]
    stored = datasets.list()[0]
    assert stored.available_area == first.available_area
    assert stored.gtfs.valid_from == first.gtfs.valid_from
