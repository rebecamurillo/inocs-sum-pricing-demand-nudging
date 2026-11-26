"""The CityPreparation port: one suite, run against the fake (the real adapter joins it with
story 2-7 as a `characterisation` parameter)."""

import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.application.ports.city_preparation import CityPreparation, PreparationRequest
from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.domain.build_plan import STEP_OUTPUTS
from pricing_demo.domain.city_datasets import GENEVA_PRESET
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.failure_codes import FAILURE_CODES, failure_reason
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation, haversine_m
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.waiter import SystemWaiter
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
PERIOD = first_period("geneva-3km.v1", DATASET)
CENTRE = (GENEVA_PRESET.centre_lat, GENEVA_PRESET.centre_lon)
BUILD_STEPS = list(STEP_OUTPUTS)


@dataclass
class Rig:
    port: CityPreparation
    settings: InMemoryFakeSettings

    def request(self, folder: Path, step: StepName, **changes: Any) -> PreparationRequest:
        folder.mkdir(parents=True, exist_ok=True)
        return PreparationRequest(
            "run-1", step, folder, replace(PARAMETERS, **changes), DATASET, PERIOD
        )

    def prepare(
        self, folder: Path, step: StepName, stop: threading.Event | None = None, **changes: Any
    ) -> StepOutcome:
        return self.port.prepare(
            self.request(folder, step, **changes),
            lambda done, total: None,
            stop or threading.Event(),
        )


@pytest.fixture(params=[pytest.param("fake", id="fake")])
def rig(request: pytest.FixtureRequest) -> Rig:
    settings = InMemoryFakeSettings()
    return Rig(FakeCityPreparation(settings, SystemWaiter()), settings)


def run_all(rig: Rig, folder: Path) -> dict[StepName, StepOutcome]:
    return {step: rig.prepare(folder, step) for step in BUILD_STEPS}


def read(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def test_each_step_writes_its_outputs_as_parseable_files(rig: Rig, tmp_path: Path) -> None:
    for step, names in STEP_OUTPUTS.items():
        outcome = rig.prepare(tmp_path, step)

        assert outcome.failure_code is None
        assert not outcome.stopped
        for name in names:
            assert read(tmp_path, name), name


def test_the_files_have_the_fields_of_the_package(rig: Rig, tmp_path: Path) -> None:
    run_all(rig, tmp_path)

    station = read(tmp_path, "stations.json")["stations"][0]
    assert set(station) == {"station_id", "type", "name", "lat", "lon"}
    hub = read(tmp_path, "hubs.geojson")["features"][0]["properties"]
    assert set(hub) == {"hub_id", "label", "bike_stations", "pt_stations", "lines"}
    assert read(tmp_path, "stations_hubs.geojson")["features"][0]["geometry"]["type"] == "Point"
    assert read(tmp_path, "hub_polygons.geojson")["features"][0]["geometry"]["type"] == "Polygon"
    pair = read(tmp_path, "od_routes.json")["od_results"][0]
    assert {"from_id", "to_id", "arc_pt_bike", "arc_pt_only", "arc_car"} <= set(pair)
    assert read(tmp_path, "od_geometry.json")["geometries"][0]["legs_geometry"][0]["geometry"]
    instance = read(tmp_path, "Instance_1.json")
    assert {"OD_pairs", "bike_stations", "arcs_pt_bike", "arcs_pt_only", "car_paths"} <= set(
        instance
    )
    assert {"origin", "destination", "demand"} == set(instance["OD_pairs"][0])


def test_the_counts_describe_the_fixed_city(rig: Rig, tmp_path: Path) -> None:
    outcomes = run_all(rig, tmp_path)

    assert outcomes[StepName.AREA].counts == {"stops": 30, "bike_stations": 12}
    assert outcomes[StepName.HUBS].counts == {"hubs": 6}
    assert outcomes[StepName.ROUTES].counts == {
        "hub_pairs_requested": 24,
        "hub_pairs_with_routes": 24,
        "hub_pairs_removed": 0,
    }
    counts = outcomes[StepName.TRAVELLERS_AND_BIKES].counts
    assert (counts["hub_pairs"], counts["bike_stations"]) == (24, 12)
    assert counts["travellers"] == sum(
        item["demand"] for item in read(tmp_path, "Instance_1.json")["OD_pairs"]
    )
    assert counts["options"] == {"pt_bike": 23, "pt_only": 24, "car": 24}


def test_every_station_and_hub_is_within_a_kilometre_of_the_preset_centre(
    rig: Rig, tmp_path: Path
) -> None:
    run_all(rig, tmp_path)

    stations = read(tmp_path, "stations.json")["stations"]
    hubs = read(tmp_path, "hubs.geojson")["features"]
    points = [(item["lat"], item["lon"]) for item in stations]
    points += [tuple(reversed(item["geometry"]["coordinates"])) for item in hubs]
    assert len(points) == 42 + 6
    assert all(haversine_m(CENTRE, point) < 1000 for point in points)


def test_two_pairs_are_under_the_minimum_trip_distance_and_one_has_no_bike_option(
    rig: Rig, tmp_path: Path
) -> None:
    run_all(rig, tmp_path)
    where = {
        item["properties"]["hub_id"]: tuple(reversed(item["geometry"]["coordinates"]))
        for item in read(tmp_path, "hubs.geojson")["features"]
    }
    results = read(tmp_path, "od_routes.json")["od_results"]

    close = [
        item
        for item in results
        if haversine_m(where[item["from_id"]], where[item["to_id"]]) < PARAMETERS.min_od_distance_m
    ]
    without_bike = [item for item in results if not item["arc_pt_bike"]]
    assert len(results) == 24
    assert len(close) == 2
    assert len(without_bike) == 1


def test_every_mode_is_present(rig: Rig, tmp_path: Path) -> None:
    run_all(rig, tmp_path)
    modes = {
        leg["mode"]
        for item in read(tmp_path, "od_routes.json")["od_results"]
        for arcs in (item["arc_pt_bike"], item["arc_pt_only"], item["arc_car"])
        for arc in arcs
        for leg in arc["legs"]
    }

    assert modes == {"BICYCLE", "BUS", "TRAM", "FOOT", "CAR"}


def test_some_stations_have_no_bike_and_some_no_free_dock(rig: Rig, tmp_path: Path) -> None:
    run_all(rig, tmp_path)

    info = read(tmp_path, "Instance_1.json")["bike_stations"]
    inventory, capacity = info["station_inventory"], info["station_capacity"]
    assert any(inventory[station] == 0 for station in inventory)
    assert any(inventory[station] == capacity[station] for station in inventory)


def test_the_same_request_writes_the_same_files_and_the_seed_changes_the_travellers(
    rig: Rig, tmp_path: Path
) -> None:
    first, second, other = tmp_path / "a", tmp_path / "b", tmp_path / "c"

    rig.prepare(first, StepName.TRAVELLERS_AND_BIKES)
    rig.prepare(second, StepName.TRAVELLERS_AND_BIKES)
    rig.prepare(other, StepName.TRAVELLERS_AND_BIKES, seed=7)

    assert (first / "Instance_1.json").read_bytes() == (second / "Instance_1.json").read_bytes()
    assert (first / "Instance_1.json").read_bytes() != (other / "Instance_1.json").read_bytes()


@pytest.mark.parametrize("code", FAILURE_CODES)
def test_a_step_named_to_fail_fails_with_the_code_and_its_reason(
    rig: Rig, tmp_path: Path, code: str
) -> None:
    rig.settings.set_pricing_model({"fail_at": {"step": "routes", "code": code}})

    ok = rig.prepare(tmp_path, StepName.HUBS)
    outcome = rig.prepare(tmp_path, StepName.ROUTES)

    assert ok.failure_code is None
    assert outcome.failure_code == code
    assert outcome.failure_reason
    assert outcome.failure_reason == failure_reason(
        code,
        url="http://trip-planner.fake/otp",
        d="2025-03-10",
        name="INFEASIBLE",
        check="the travellers of a pair do not add up",
        n=9,
        exception_type="RuntimeError",
        message="fake failure",
    )
    assert not (tmp_path / "od_routes.json").exists()


def test_clearing_the_settings_clears_the_failure(rig: Rig, tmp_path: Path) -> None:
    rig.settings.set_pricing_model({"fail_at": {"step": "area", "code": "stage_error"}})
    assert rig.prepare(tmp_path, StepName.AREA).failure_code == "stage_error"

    rig.settings.set_pricing_model(None)

    assert rig.prepare(tmp_path, StepName.AREA).failure_code is None


def start(
    rig: Rig, folder: Path, step: StepName, stop: threading.Event
) -> tuple[threading.Thread, list[StepOutcome]]:
    results: list[StepOutcome] = []
    thread = threading.Thread(target=lambda: results.append(rig.prepare(folder, step, stop)))
    thread.start()
    return thread, results


def test_a_held_step_waits_until_its_run_is_released(rig: Rig, tmp_path: Path) -> None:
    rig.settings.set_pricing_model({"hold_at": "hubs"})
    thread, results = start(rig, tmp_path, StepName.HUBS, threading.Event())

    thread.join(0.3)
    held = thread.is_alive()
    # The release of another run does not free this one.
    rig.settings.release_run("run-2")
    thread.join(0.3)
    still_held = thread.is_alive()
    rig.settings.release_run("run-1")
    thread.join(5)

    assert (held, still_held) == (True, True)
    assert not thread.is_alive()
    assert results[0].counts == {"hubs": 6}


def test_a_held_step_ends_stopped_when_the_stop_is_set(rig: Rig, tmp_path: Path) -> None:
    rig.settings.set_pricing_model({"hold_at": "area"})
    stop = threading.Event()
    thread, results = start(rig, tmp_path, StepName.AREA, stop)

    thread.join(0.2)
    stop.set()
    thread.join(5)

    assert not thread.is_alive()
    assert results[0].stopped is True
    assert not (tmp_path / "stations.json").exists()


def test_the_routes_step_reports_its_progress_pair_by_pair_at_the_set_pace(
    tmp_path: Path,
) -> None:
    settings = InMemoryFakeSettings()
    settings.set_pricing_model({"routes_pace_ms": 20})
    waits: list[float] = []

    class Recording:
        def wait(self, seconds: float, wake: threading.Event) -> bool:
            waits.append(seconds)
            return False

    port = FakeCityPreparation(settings, Recording())
    seen: list[tuple[int, int]] = []
    request = PreparationRequest("run-1", StepName.ROUTES, tmp_path, PARAMETERS, DATASET, PERIOD)

    outcome = port.prepare(
        request, lambda done, total: seen.append((done, total)), threading.Event()
    )

    assert seen == [(done, 24) for done in range(1, 25)]
    assert waits == [0.02] * 24
    assert outcome.counts["hub_pairs_requested"] == 24


def test_the_routes_step_without_a_pace_reports_no_progress(rig: Rig, tmp_path: Path) -> None:
    seen: list[tuple[int, int]] = []
    request = rig.request(tmp_path, StepName.ROUTES)

    rig.port.prepare(request, lambda done, total: seen.append((done, total)), threading.Event())

    assert seen == []


def test_a_paced_routes_step_ends_stopped_when_the_stop_is_set(tmp_path: Path) -> None:
    settings = InMemoryFakeSettings()
    settings.set_pricing_model({"routes_pace_ms": 1})
    stop = threading.Event()
    stop.set()
    port = FakeCityPreparation(settings, SystemWaiter())
    request = PreparationRequest("run-1", StepName.ROUTES, tmp_path, PARAMETERS, DATASET, PERIOD)

    outcome = port.prepare(request, lambda done, total: None, stop)

    assert outcome.stopped is True
