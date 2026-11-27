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
from pricing_demo.domain.read_model import RouteFailure
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
    assert {"origin", "destination", "demand", "euclid_dist"} == set(instance["OD_pairs"][0])


def test_the_counts_describe_the_fixed_city(rig: Rig, tmp_path: Path) -> None:
    outcomes = run_all(rig, tmp_path)

    assert outcomes[StepName.AREA].counts == {"stops": 30, "bike_stations": 12}
    assert outcomes[StepName.HUBS].counts == {"hubs": 6}
    assert outcomes[StepName.ROUTES].counts == {
        "hub_pairs_requested": 24,
        "hub_pairs_with_routes": 24,
        "hub_pairs_removed": 0,
        "retries": 3,
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


def failure(origin: str, destination: str, query: str, kind: str) -> dict[str, str]:
    return {
        "origin_hub": origin,
        "destination_hub": destination,
        "query": query,
        "kind": kind,
        "message": f"{kind} at {origin}-{destination}",
    }


def routes_with_failures(
    rig: Rig, folder: Path, failures: list[dict[str, str]]
) -> tuple[StepOutcome, list[RouteFailure]]:
    rig.settings.set_pricing_model({"route_failures": failures})
    reported: list[RouteFailure] = []
    outcome = rig.port.prepare(
        rig.request(folder, StepName.ROUTES),
        lambda done, total: None,
        threading.Event(),
        reported.append,
    )
    return outcome, reported


def test_every_pair_carries_the_euclidean_distance_the_package_writes(
    rig: Rig, tmp_path: Path
) -> None:
    run_all(rig, tmp_path)
    where = {
        item["properties"]["hub_id"]: tuple(reversed(item["geometry"]["coordinates"]))
        for item in read(tmp_path, "hubs.geojson")["features"]
    }

    for pair in read(tmp_path, "Instance_1.json")["OD_pairs"]:
        assert pair["euclid_dist"] == round(
            haversine_m(where[pair["origin"]], where[pair["destination"]])
        )


def test_no_failed_query_is_reported_by_default(rig: Rig, tmp_path: Path) -> None:
    reported: list[RouteFailure] = []

    rig.port.prepare(
        rig.request(tmp_path, StepName.ROUTES),
        lambda done, total: None,
        threading.Event(),
        reported.append,
    )

    assert reported == []


def test_a_failed_public_transport_query_drops_the_pair_and_a_failed_car_query_its_car_option(
    rig: Rig, tmp_path: Path
) -> None:
    failures = [
        failure("H1", "H2", "pt_bike", "technical"),
        failure("H1", "H6", "car", "no_route"),
    ]

    outcome, reported = routes_with_failures(rig, tmp_path, failures)

    assert [(item.origin_hub, item.query, item.kind, item.attempts) for item in reported] == [
        ("H1", "pt_bike", "technical", 4),
        ("H1", "car", "no_route", 1),
    ]
    results = {
        (item["from_id"], item["to_id"]): item
        for item in read(tmp_path, "od_routes.json")["od_results"]
    }
    assert ("H1", "H2") not in results
    assert results[("H1", "H6")]["arc_car"] == []
    assert results[("H1", "H6")]["arc_pt_only"]
    assert outcome.counts == {
        "hub_pairs_requested": 24,
        "hub_pairs_with_routes": 23,
        "hub_pairs_removed": 0,
        "retries": 3,
    }
    whole = tmp_path / "whole"
    rig.settings.set_pricing_model(None)
    rig.prepare(whole, StepName.ROUTES)
    full = {
        (item["from_id"], item["to_id"]): item
        for item in read(whole, "od_routes.json")["od_results"]
    }
    gone = {
        arc["arc_id"]
        for key in ("arc_pt_bike", "arc_pt_only", "arc_car")
        for arc in full[("H1", "H2")][key]
    } | {arc["arc_id"] for arc in full[("H1", "H6")]["arc_car"]}
    kept = {item["arc_id"] for item in read(tmp_path, "od_geometry.json")["geometries"]}
    assert gone
    assert not gone & kept


def test_the_travellers_step_reads_the_routes_the_routes_step_wrote(
    rig: Rig, tmp_path: Path
) -> None:
    routes_with_failures(rig, tmp_path, [failure("H1", "H2", "pt_bike", "no_route")])
    rig.settings.set_pricing_model(None)

    outcome = rig.prepare(tmp_path, StepName.TRAVELLERS_AND_BIKES)

    assert outcome.counts["hub_pairs"] == 23


def test_a_failure_at_a_pair_the_city_does_not_request_is_ignored(rig: Rig, tmp_path: Path) -> None:
    outcome, reported = routes_with_failures(
        rig, tmp_path, [failure("H3", "H4", "car", "no_route")]
    )

    assert reported == []
    assert outcome.counts["hub_pairs_with_routes"] == 24
