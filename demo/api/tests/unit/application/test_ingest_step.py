from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from pricing_demo.application.ingest_step import StepIngestion
from pricing_demo.application.ports.artifacts import Artifact, StoredFile
from pricing_demo.domain.build_plan import STEP_OUTPUTS
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.feed_shapes import FakeFeedShapes
from pricing_demo.infrastructure.fakes.read_model import InMemoryReadModel
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from tests.support.builds import RecordingFiles
from tests.support.city_files import DATASET, FakeCity
from tests.support.runs import T0

ROUTES_FAILURES = [
    {
        "origin_hub": "H1",
        "destination_hub": "H2",
        "query": "pt_bike",
        "kind": "technical",
        "message": "timeout",
    }
]


class Rig:
    def __init__(self, tmp_path: Path, failures: list[dict[str, str]] | None = None) -> None:
        self.city = FakeCity(tmp_path, failures or [])
        self.files = RecordingFiles()
        self.read_model = InMemoryReadModel()
        self.route_failures = InMemoryRouteFailures()
        self.ingestion = StepIngestion(
            self.files, self.read_model, self.route_failures, FakeFeedShapes(frozenset({"1"}))
        )
        self.artifacts: dict[StepName, Artifact] = {}
        for step, names in STEP_OUTPUTS.items():
            for name in names:
                self.files.contents[(f"artifacts/{step.value}/k-{step.value}", name)] = (
                    self.city.files[name]
                )
            self.artifacts[step] = self.artifact(step)
        for failure in self.city.failures:
            self.route_failures.add("run-1", 3, "p", failure, T0)

    def artifact(self, step: StepName, run_id: str | None = "run-1") -> Artifact:
        return Artifact(
            f"k-{step.value}",
            step,
            {},
            tuple(StoredFile(name, "0" * 64, 1) for name in STEP_OUTPUTS[step]),
            f"artifacts/{step.value}/k-{step.value}",
            "f" * 64,
            datetime(2026, 11, 26, tzinfo=T0.tzinfo),
            run_id,
            self.city.counts[step],
        )

    def ingest(self, step: StepName) -> object:
        return self.ingestion.ingest(self.artifacts[step], DATASET, self.artifacts)


def test_the_area_step_stores_its_stations_and_counts_them(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    counts = rig.ingest(StepName.AREA)

    assert counts == {"stops": 30, "bike_stations": 12}
    assert len(rig.read_model.stations("k-area")) == 42
    assert rig.read_model.counts_of(["k-area"]) == {"k-area": counts}


def test_the_hubs_step_stores_its_hubs_and_the_station_links(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    counts = rig.ingest(StepName.HUBS)

    assert counts == {"hubs": 6}
    assert len(rig.read_model.hubs("k-hubs")) == 6


def test_the_routes_counts_read_the_failures_of_the_producing_run_step(tmp_path: Path) -> None:
    rig = Rig(tmp_path, ROUTES_FAILURES)

    counts = rig.ingest(StepName.ROUTES)

    assert counts == {
        "hub_pairs_requested": 24,
        "hub_pairs_with_routes": 23,
        "hub_pairs_removed": 0,
        "queries": 48,
        "queries_failed": 1,
        "failure_pct": pytest.approx(100 / 48),
        "retries": 3,
    }


def test_the_routes_step_stores_the_pairs_it_routed(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.ingest(StepName.ROUTES)

    pairs = rig.read_model.route_pairs("k-routes")
    assert len(pairs) == 24
    assert pairs == sorted(pairs, key=lambda item: (item.origin_hub, item.destination_hub))
    assert rig.read_model.hub_pairs("k-routes") == []


def test_the_routes_of_an_artefact_with_no_producing_run_have_no_failures(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, ROUTES_FAILURES)
    rig.artifacts[StepName.ROUTES] = rig.artifact(StepName.ROUTES, run_id=None)

    counts = rig.ingest(StepName.ROUTES)

    assert isinstance(counts, dict)
    assert counts["queries_failed"] == 0


def test_the_last_step_stores_pairs_options_bikes_and_deltas(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    counts = rig.ingest(StepName.TRAVELLERS_AND_BIKES)

    assert isinstance(counts, dict)
    assert (counts["hub_pairs"], counts["bike_stations"]) == (24, 12)
    assert counts["options"] == {"pt_bike": 25, "pt_only": 24, "car": 24}
    assert len(rig.read_model.hub_pairs("k-travellers_and_bikes")) == 24
    # It reads the routes artefact's files too.
    assert ("artifacts/routes/k-routes", "od_geometry.json") in rig.files.contents
    assert [call[1] for call in rig.files.named("read_json")].count(
        "artifacts/routes/k-routes"
    ) == 2


def test_a_file_that_cannot_be_read_stores_nothing(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    del rig.files.contents[("artifacts/area/k-area", "stations.json")]

    with pytest.raises(KeyError):
        rig.ingest(StepName.AREA)

    assert not rig.read_model.is_ingested("k-area")


def test_a_malformed_file_stores_nothing(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.files.contents[("artifacts/area/k-area", "stations.json")] = {"stations": [{}]}

    with pytest.raises(ValueError, match=r"stations\.json"):
        rig.ingest(StepName.AREA)

    assert not rig.read_model.is_ingested("k-area")


def test_the_options_carry_the_bike_legs_the_package_parser_counted(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    rig.ingest(StepName.TRAVELLERS_AND_BIKES)

    options = rig.read_model._batches["k-travellers_and_bikes"].route_options
    expected = rig.city.files["option_bike_legs.json"]
    assert {item.arc_id: item.bike_legs for item in options} == {
        arc: expected[arc] for arc in (item.arc_id for item in options)
    }
    assert {item.bike_legs for item in options if item.mode == "pt_bike"} == {1}
    assert {item.bike_legs for item in options if item.mode != "pt_bike"} == {0}


def test_an_artefact_stored_without_the_file_has_null_bike_legs(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    stored = rig.artifacts[StepName.TRAVELLERS_AND_BIKES]
    rig.artifacts[StepName.TRAVELLERS_AND_BIKES] = replace(
        stored, files=tuple(item for item in stored.files if item.name == "Instance_1.json")
    )

    rig.ingest(StepName.TRAVELLERS_AND_BIKES)

    options = rig.read_model._batches["k-travellers_and_bikes"].route_options
    assert options
    assert {item.bike_legs for item in options} == {None}
