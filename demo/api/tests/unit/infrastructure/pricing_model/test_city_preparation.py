import json
import os
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.routes_progress import (
    CAR_DONE,
    CLEANUP_REMOVED,
    PT_FAILED,
    ROUTE_TOTAL,
)
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = replace(parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset), seed=7)
OTP_URL = "http://otp.test/otp/gtfs/v1"
PERIOD = first_period("geneva-3km.v1", DATASET)


class Recording(StageChild):
    def __init__(self) -> None:
        self.specs: list[StageSpec] = []

    def run(
        self, spec: StageSpec, stop: StopSignal, on_progress: Callable[[], None] | None = None
    ) -> StepOutcome:
        self.specs.append(spec)
        return StepOutcome.done({"x": 1})


def prepare(step: StepName, tmp_path: Path) -> tuple[StepOutcome, Recording]:
    child = Recording()
    port = PackageCityPreparation(tmp_path / "data", child, OTP_URL)
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


def test_the_routes_step_gets_the_timestamp_the_url_the_workers_and_the_retry_settings(
    tmp_path: Path,
) -> None:
    child = Recording()
    port = PackageCityPreparation(tmp_path / "data", child, OTP_URL, 6, 5, 0.5)
    request = PreparationRequest(
        "run-1", StepName.ROUTES, tmp_path / "w", PARAMETERS, DATASET, PERIOD
    )

    port.prepare(request, lambda done, total: None, threading.Event())

    spec = child.specs[0]
    assert spec.step == "routes"
    moment = DATASET.routing_moment
    assert spec.pipeline == {
        "center_lat": PARAMETERS.center_lat,
        "center_lon": PARAMETERS.center_lon,
        "radius_m": PARAMETERS.radius_m,
        "gtfs_path": str(tmp_path / "data" / DATASET.gtfs.file),
        "min_od_distance_m": PARAMETERS.min_od_distance_m,
        "otp_url": OTP_URL,
        "otp_workers": 6,
        "otp_timestamp": f"{PERIOD.routing_date}T{PERIOD.routing_time:%H:%M:%S}.000000Z",
    }
    assert spec.routes == {
        "retries": 5,
        "retry_wait_s": 0.5,
        "routing_date": PERIOD.routing_date.isoformat(),
    }
    assert moment is not None


class Writing(StageChild):
    """A child that logs lines to `progress.jsonl` between two reads."""

    def __init__(self, outcome: StepOutcome) -> None:
        self.outcome = outcome

    def run(
        self, spec: StageSpec, stop: StopSignal, on_progress: Callable[[], None] | None = None
    ) -> StepOutcome:
        assert on_progress is not None
        path = Path(spec.working_dir) / "progress.jsonl"

        def write(*records: dict[str, object]) -> None:
            with path.open("a", encoding="utf-8") as file:
                for record in records:
                    file.write(json.dumps(record) + "\n")

        write({"template": ROUTE_TOTAL, "args": [3, 0, 3, 4, 0.05]})
        on_progress()
        write(
            {"template": PT_FAILED, "args": ["1|2", "503"]},
            {"template": CAR_DONE, "args": ["1|3", 2]},
            {"template": CAR_DONE, "args": ["2|3", 0]},
            {"template": CLEANUP_REMOVED, "args": [2, 3, 66.67, "f"]},
        )
        on_progress()  # the child's read after the process ended
        return self.outcome


def test_the_routes_step_reports_the_failures_the_progress_and_the_three_counts(
    tmp_path: Path,
) -> None:
    (tmp_path / "w").mkdir()
    port = PackageCityPreparation(
        tmp_path / "data", Writing(StepOutcome.done({"x": 1})), OTP_URL, retries=2
    )
    request = PreparationRequest(
        "run-1", StepName.ROUTES, tmp_path / "w", PARAMETERS, DATASET, PERIOD
    )
    failures: list[RouteFailure] = []
    steps: list[tuple[int, int]] = []

    outcome = port.prepare(
        request, lambda done, total: steps.append((done, total)), threading.Event(), failures.append
    )

    assert [(f.origin_hub, f.destination_hub, f.query, f.kind, f.attempts) for f in failures] == [
        ("1", "2", "pt_bike", "technical", 3),
        ("2", "3", "car", "no_route", 1),
    ]
    assert steps == [(0, 3), (3, 3)]
    assert dict(outcome.counts) == {
        "hub_pairs_requested": 3,
        "hub_pairs_removed": 2,
        "retries": 2,
    }


def test_a_failed_routes_step_is_returned_as_it_is(tmp_path: Path) -> None:
    (tmp_path / "w").mkdir()
    failed = StepOutcome.failed("no_public_transport", "none")
    port = PackageCityPreparation(tmp_path / "data", Writing(failed), OTP_URL)
    request = PreparationRequest(
        "run-1", StepName.ROUTES, tmp_path / "w", PARAMETERS, DATASET, PERIOD
    )

    outcome = port.prepare(request, lambda done, total: None, threading.Event())

    assert outcome.failure_code == "no_public_transport"
    assert outcome.counts == {}


def test_relative_folders_reach_the_child_as_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The child starts in the working directory: a path relative to the worker's own
    # directory (the default data directory `var/data`) would not resolve there.
    monkeypatch.chdir(tmp_path)
    child = Recording()
    port = PackageCityPreparation(Path("data"), child, OTP_URL)
    request = PreparationRequest("run-1", StepName.AREA, Path("w"), PARAMETERS, DATASET, PERIOD)

    port.prepare(request, lambda done, total: None, threading.Event())

    spec = child.specs[0]
    assert spec.working_dir == str(tmp_path / "w")
    assert spec.pipeline["gtfs_path"] == str(tmp_path / "data" / DATASET.gtfs.file)
    assert spec.pipeline["gbfs_path"] == str(tmp_path / "data" / DATASET.gbfs.file)
