"""The BikeStationFeed port: one suite, run on the fixture feed and, live, on the package."""

import json
from pathlib import Path

import pytest

from pricing_demo.application.ports.bike_station_feed import BikeStationFeed
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed

MANIFEST_URL = "https://stables.donkey.bike/api/public/gbfs/2/donkey_ge/gbfs.json"


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("package", id="package", marks=pytest.mark.live),
    ]
)
def feed(request: pytest.FixtureRequest) -> BikeStationFeed:
    return FixtureBikeStationFeed() if request.param == "fake" else PackageBikeStationFeed()


def test_the_feed_writes_station_information_under_the_target_directory(
    feed: BikeStationFeed, tmp_path: Path
) -> None:
    target = tmp_path / "datasets" / "one"

    fetched = feed.fetch(target)

    assert fetched.file.is_file()
    assert fetched.file.is_relative_to(target)
    stations = json.loads(fetched.file.read_text(encoding="utf-8"))["data"]["stations"]
    assert stations
    assert all({"station_id", "lat", "lon"} <= set(station) for station in stations)


def test_the_source_is_the_providers_manifest(feed: BikeStationFeed, tmp_path: Path) -> None:
    assert feed.fetch(tmp_path / "one").source_url == MANIFEST_URL
