import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pricing_demo.application.errors import (
    GraphBuildFailed,
    GtfsCopyChanged,
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    StreetExtractNotFound,
    UnknownCityDataset,
)
from pricing_demo.application.use_cases.build_trip_planner_graph import BuildTripPlannerGraph
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader, ZipTimetableShapes
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.graph_builder import FakeGraphBuilder
from pricing_demo.infrastructure.trip_planner.graph_folder import LocalGraphFolder
from tests.support.city_data import osm_folder, zip_gtfs


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.datasets = InMemoryCityDatasets()
        self.files = LocalDatasetFiles(tmp_path / "data")
        self.graph = osm_folder(tmp_path / "graph")
        self.folder = LocalGraphFolder(self.graph)
        self.builder = FakeGraphBuilder(image="otp:1", folder=self.graph)
        self.gtfs = zip_gtfs(tmp_path / "source" / "tpg_gtfs.zip")
        self.osm = osm_folder(tmp_path / "osm")

    def import_dataset(self, day: int) -> str:
        clock = FixedClock(datetime(2026, 11, day, 9, 0, tzinfo=UTC))
        return (
            ImportCityData(
                self.datasets,
                ZipTimetableReader(),
                PbfStreetExtract(),
                self.files,
                FixtureBikeStationFeed(),
                FakeBusShapeMatcher(),
                ZipTimetableShapes(),
                clock,
            )
            .execute(self.gtfs, self.osm)
            .id
        )

    def use_case(self, builder: FakeGraphBuilder | None = None) -> BuildTripPlannerGraph:
        return BuildTripPlannerGraph(
            self.datasets, self.files, self.folder, builder or self.builder
        )

    def manifest_path(self) -> Path:
        return self.graph / "graph-manifest.json"


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_the_latest_data_set_is_built_and_the_manifest_says_what_went_in(rig: Rig) -> None:
    rig.import_dataset(25)
    latest = rig.import_dataset(26)

    path = rig.use_case().execute(None)

    assert path == rig.manifest_path()
    copy = rig.files.resolve(rig.datasets.latest().gtfs.file)  # type: ignore[union-attr]
    assert (rig.graph / "gtfs.zip").read_bytes() == copy.read_bytes()
    manifest = json.loads(path.read_text())
    assert manifest == {
        "otp_image": "otp:1",
        "dataset_id": latest,
        "gtfs_sha256": rig.folder.sha256(rig.graph / "gtfs.zip"),
        "osm_file": "geneva.osm.pbf",
        "osm_sha256": rig.folder.sha256(rig.graph / "geneva.osm.pbf"),
        "build_config": {"transitServiceStart": "2024-12-15", "transitServiceEnd": "2025-12-13"},
    }
    assert json.loads((rig.graph / "build-config.json").read_text()) == manifest["build_config"]


def test_a_named_data_set_is_built(rig: Rig) -> None:
    first = rig.import_dataset(25)
    rig.import_dataset(26)

    rig.use_case().execute(first)

    assert json.loads(rig.manifest_path().read_text())["dataset_id"] == first


def test_the_builder_runs_once_after_the_config_and_the_timetable_are_written(rig: Rig) -> None:
    rig.import_dataset(26)

    rig.use_case().execute(None)

    assert len(rig.builder.calls) == 1
    assert {"build-config.json", "gtfs.zip", "geneva.osm.pbf"} <= set(rig.builder.calls[0])
    assert "graph-manifest.json" not in rig.builder.calls[0]


@pytest.mark.parametrize("case", ["other-gtfs", "no-data", "unknown-id", "no-osm", "two-osm"])
def test_a_refusal_runs_no_builder_and_writes_no_manifest(rig: Rig, case: str) -> None:
    dataset_id: str | None = None
    expected: type[Exception] = NoCityDataYet
    if case != "no-data":
        rig.import_dataset(26)
    if case == "other-gtfs":
        (rig.graph / "tpg_gtfs.zip").write_bytes(b"x")
        expected = OtherTimetableInGraphFolder
    if case == "unknown-id":
        dataset_id, expected = "geneva-1999-01-01", UnknownCityDataset
    if case == "no-osm":
        (rig.graph / "geneva.osm.pbf").unlink()
        expected = StreetExtractNotFound
    if case == "two-osm":
        osm_folder(rig.graph, ("a.osm.pbf",))
        expected = StreetExtractNotFound
    rig.manifest_path().write_text("{}")

    with pytest.raises(expected):
        rig.use_case().execute(dataset_id)

    assert rig.builder.calls == []
    assert not (rig.graph / "gtfs.zip").exists()
    assert not (rig.graph / "build-config.json").exists()


def test_the_refusal_names_the_offending_files(rig: Rig) -> None:
    rig.import_dataset(26)
    (rig.graph / "tpg_gtfs.zip").write_bytes(b"x")

    with pytest.raises(OtherTimetableInGraphFolder, match=r"tpg_gtfs\.zip"):
        rig.use_case().execute(None)


def test_a_failing_builder_leaves_no_manifest_and_removes_a_stale_one(rig: Rig) -> None:
    rig.import_dataset(26)
    rig.manifest_path().write_text('{"stale": true}')
    builder = FakeGraphBuilder(fail_with="exit 3", folder=rig.graph)

    with pytest.raises(GraphBuildFailed, match="exit 3"):
        rig.use_case(builder).execute(None)

    assert len(builder.calls) == 1
    assert not rig.manifest_path().exists()


@pytest.mark.parametrize("change", ["missing", "edited"])
def test_a_missing_or_changed_timetable_copy_is_refused_before_anything_is_written(
    rig: Rig, change: str
) -> None:
    dataset_id = rig.import_dataset(26)
    dataset = rig.datasets.latest()
    assert dataset is not None
    assert dataset.id == dataset_id
    copy = rig.files.resolve(dataset.gtfs.file)
    if change == "missing":
        copy.unlink()
    else:
        copy.write_bytes(copy.read_bytes() + b"\0")
    rig.manifest_path().write_text('{"earlier": true}')

    with pytest.raises(GtfsCopyChanged, match=dataset_id):
        rig.use_case().execute(None)

    assert rig.builder.calls == []
    assert rig.manifest_path().read_text() == '{"earlier": true}'
    assert not (rig.graph / "gtfs.zip").exists()
