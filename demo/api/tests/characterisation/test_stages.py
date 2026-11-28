"""Steps 1, 2 and 4 of a build, run by the real adapter and its child process on the committed
synthetic city. Pins the files and fields the demonstrator reads from the package."""

import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.domain import read_model as rows
from pricing_demo.domain.build_plan import STEP_OUTPUTS
from pricing_demo.domain.runs import StepName
from tests.characterisation.rig import City, build

pytestmark = pytest.mark.characterisation

# Fixed at the first run: the fixture's routes hold two bike legs in arc a1b and one each in
# a2b and a3b.
GOLDEN_BIKE_LEGS = 4
NEVER = threading.Event()


def read(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def test_the_three_steps_write_their_outputs_with_the_fields_of_the_package(
    city: City, tmp_path: Path
) -> None:
    folder = tmp_path / "w"

    outcomes = build(city, folder)

    for step, outcome in outcomes.items():
        assert outcome.failure_code is None, outcome.failure_reason
        for name in STEP_OUTPUTS[step]:
            assert (folder / name).is_file(), name
    stations = read(folder, "stations.json")["stations"]
    assert {item["type"] for item in stations} == {"pt", "bs"}
    assert set(stations[0]) == {"station_id", "type", "name", "lat", "lon"}
    hub = read(folder, "hubs.geojson")["features"][0]["properties"]
    assert set(hub) == {"hub_id", "label", "bike_stations", "pt_stations", "lines"}
    assert read(folder, "stations_hubs.geojson")["features"][0]["geometry"]["type"] == "Point"
    assert read(folder, "hub_polygons.geojson")["features"][0]["geometry"]["type"] == "Polygon"
    instance = read(folder, "Instance_1.json")
    assert {"OD_pairs", "bike_stations", "arcs_pt_bike", "arcs_pt_only", "car_paths"} <= set(
        instance
    )
    assert not list(folder.glob("Instance_[!1]*.json"))


def test_the_area_has_the_stops_and_stations_inside_the_radius(city: City, tmp_path: Path) -> None:
    outcome = city.prepare(tmp_path / "w", StepName.AREA, NEVER)

    stations = read(tmp_path / "w", "stations.json")["stations"]
    assert outcome.failure_code is None
    assert sum(item["type"] == "pt" for item in stations) == 4
    assert sum(item["type"] == "bs" for item in stations) == 4


def test_the_hubs_are_two_pt_plus_bike_stations(city: City, tmp_path: Path) -> None:
    folder = tmp_path / "w"
    city.prepare(folder, StepName.AREA, NEVER)

    city.prepare(folder, StepName.HUBS, NEVER)

    labels = [item["properties"]["label"] for item in read(folder, "hubs.geojson")["features"]]
    assert labels == ["pt+bike station", "pt+bike station"]


def test_the_demand_is_integer_and_the_deltas_are_one_unit_with_minus_one_where_a_bike_is_taken(
    city: City, tmp_path: Path
) -> None:
    folder = tmp_path / "w"
    build(city, folder)
    instance = read(folder, "Instance_1.json")
    stations = read(folder, "stations.json")["stations"]
    by_name = {item["name"].strip().lower(): item["station_id"] for item in stations}

    assert all(type(item["demand"]) is int for item in instance["OD_pairs"])
    taken: dict[str, str] = {}
    for pair in instance["arcs_pt_bike"].values():
        for arc in pair:
            first = next(leg for leg in arc["legs"] if leg["mode"] == "BICYCLE")
            taken[arc["arc_id"]] = by_name[first["from_place"].strip().lower()]
    for arc_id, station in taken.items():
        deltas = instance["delta_ia"][arc_id]
        assert set(deltas.values()) <= {-1, 1}
        assert deltas[station] == -1


def test_the_bike_legs_are_counted_per_option(city: City, tmp_path: Path) -> None:
    folder = tmp_path / "w"
    build(city, folder)

    legs = read(folder, "option_bike_legs.json")

    assert legs["a1b"] == 2
    assert legs["a2b"] == legs["a3b"] == 1
    assert sum(legs.values()) == GOLDEN_BIKE_LEGS
    assert legs["a1p"] == legs["a1c"] == 0


def test_the_working_directory_holds_the_childs_files_and_the_outcome_its_log_and_memory(
    city: City, tmp_path: Path
) -> None:
    folder = tmp_path / "w"

    outcome = city.prepare(folder, StepName.AREA, NEVER)

    for name in ("stdout.log", "stderr.log", "progress.jsonl", "outcome.json"):
        assert (folder / name).is_file(), name
    assert read(folder, "outcome.json") == {"status": "done", "counts": {}}
    assert outcome.log_excerpt is not None
    assert (outcome.peak_rss_bytes or 0) > 0


def test_the_domain_readers_accept_the_real_files(city: City, tmp_path: Path) -> None:
    folder = tmp_path / "w"
    build(city, folder)
    instance = read(folder, "Instance_1.json")

    stations = rows.stations_from(read(folder, "stations.json"))
    hubs = rows.hubs_from(read(folder, "hubs.geojson"), read(folder, "hub_polygons.geojson"))
    links = rows.station_hubs_from(read(folder, "stations_hubs.geojson"))
    pairs = rows.hub_pairs_from(instance)
    options = rows.route_options_from(
        read(folder, "od_routes.json"),
        read(folder, "od_geometry.json"),
        instance,
        frozenset(),
        read(folder, "option_bike_legs.json"),
    )

    assert rows.area_counts(stations) == {"stops": 4, "bike_stations": 4}
    assert rows.hubs_counts(hubs) == {"hubs": 2}
    assert links
    assert len(pairs) == 2
    assert {item.arc_id: item.bike_legs for item in options}["a1b"] == 2
    assert rows.instance_counts(instance)["hub_pairs"] == 2
    assert rows.station_bikes_from(instance)
    assert rows.deltas_from(instance)


def test_a_missing_timetable_ends_stage_error_with_the_exception(
    city: City, tmp_path: Path
) -> None:
    (city.data_dir / city.dataset.gtfs.file).unlink()

    outcome = city.prepare(tmp_path / "w", StepName.AREA, NEVER)

    assert outcome.failure_code == "stage_error"
    assert (outcome.failure_reason or "").startswith("FileNotFoundError: ")
    assert "Traceback" in (outcome.log_excerpt or "")


def test_a_stop_set_while_the_child_runs_ends_stopped_and_leaves_no_process(
    city: City, tmp_path: Path
) -> None:
    stop = threading.Event()
    stop.set()

    outcome = city.prepare(tmp_path / "w", StepName.AREA, stop)

    assert outcome.stopped is True
    with pytest.raises(ChildProcessError):
        os.wait4(-1, os.WNOHANG)
