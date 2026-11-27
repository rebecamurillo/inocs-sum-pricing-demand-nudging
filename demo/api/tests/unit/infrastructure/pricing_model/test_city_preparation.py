import os
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = replace(parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset), seed=7)
PERIOD = first_period("geneva-3km.v1", DATASET)


class Recording(StageChild):
    def __init__(self) -> None:
        self.specs: list[StageSpec] = []

    def run(self, spec: StageSpec, stop: StopSignal) -> StepOutcome:
        self.specs.append(spec)
        return StepOutcome.done({"x": 1})


def prepare(step: StepName, tmp_path: Path) -> tuple[StepOutcome, Recording]:
    child = Recording()
    port = PackageCityPreparation(tmp_path / "data", child)
    request = PreparationRequest("run-1", step, tmp_path / "w", PARAMETERS, DATASET, PERIOD)
    return port.prepare(request, lambda done, total: None, threading.Event()), child


def test_the_area_step_gets_the_centre_the_radius_and_the_datasets_files(tmp_path: Path) -> None:
    outcome, child = prepare(StepName.AREA, tmp_path)

    spec = child.specs[0]
    assert outcome.counts == {"x": 1}
    assert (spec.step, spec.working_dir, spec.parent_pid) == (
        "area",
        str(tmp_path / "w"),
        os.getpid(),
    )
    assert spec.pipeline == {
        "center_lat": PARAMETERS.center_lat,
        "center_lon": PARAMETERS.center_lon,
        "radius_m": PARAMETERS.radius_m,
        "gtfs_path": str(tmp_path / "data" / DATASET.gtfs.file),
        "gbfs_path": str(tmp_path / "data" / DATASET.gbfs.file),
    }
    assert spec.instance == {}


def test_the_hubs_step_adds_the_clustering_parameters(tmp_path: Path) -> None:
    _, child = prepare(StepName.HUBS, tmp_path)

    pipeline = child.specs[0].pipeline
    assert pipeline["clustering_threshold_m"] == PARAMETERS.clustering_threshold_m
    assert pipeline["clustering_buffer_m"] == PARAMETERS.clustering_buffer_m
    assert pipeline["gtfs_path"] == str(tmp_path / "data" / DATASET.gtfs.file)


def test_the_travellers_step_gets_the_seed_and_the_instance_parameters(tmp_path: Path) -> None:
    _, child = prepare(StepName.TRAVELLERS_AND_BIKES, tmp_path)

    spec = child.specs[0]
    assert spec.pipeline["seed"] == 7
    assert spec.instance == {
        "fixed_capacity": PARAMETERS.fixed_capacity,
        "min_demand": PARAMETERS.min_demand,
        "max_demand": PARAMETERS.max_demand,
        "min_inventory_pct": PARAMETERS.min_inventory_pct,
        "max_inventory_pct": PARAMETERS.max_inventory_pct,
        "min_park_time": PARAMETERS.min_park_time_min,
        "max_park_time": PARAMETERS.max_park_time_min,
    }


def test_the_routes_step_has_no_real_adapter_yet(tmp_path: Path) -> None:
    outcome, child = prepare(StepName.ROUTES, tmp_path)

    assert outcome.failure_code == "stage_error"
    assert child.specs == []


def test_relative_folders_reach_the_child_as_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The child starts in the working directory: a path relative to the worker's own
    # directory (the default data directory `var/data`) would not resolve there.
    monkeypatch.chdir(tmp_path)
    child = Recording()
    port = PackageCityPreparation(Path("data"), child)
    request = PreparationRequest("run-1", StepName.AREA, Path("w"), PARAMETERS, DATASET, PERIOD)

    port.prepare(request, lambda done, total: None, threading.Event())

    spec = child.specs[0]
    assert spec.working_dir == str(tmp_path / "w")
    assert spec.pipeline["gtfs_path"] == str(tmp_path / "data" / DATASET.gtfs.file)
    assert spec.pipeline["gbfs_path"] == str(tmp_path / "data" / DATASET.gbfs.file)
