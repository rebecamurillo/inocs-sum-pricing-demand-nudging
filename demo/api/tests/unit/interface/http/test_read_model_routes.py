from collections.abc import Mapping, Sequence
from pathlib import Path

from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from tests.support.builds import build_fake_city
from tests.support.runs import T0, make_run, step
from tests.unit.interface.http.conftest import CityInstancesApp, RunsApp
from tests.unit.interface.http.test_city_instances_routes import create

VERSION = "/api/v1/instance-versions/geneva-3km.v1"
PERIOD = "geneva-3km.v1.mon-08"
FAILURES = [
    {
        "origin_hub": "H1",
        "destination_hub": "H2",
        "query": "pt_bike",
        "kind": "technical",
        "message": "timeout",
    },
    {
        "origin_hub": "H1",
        "destination_hub": "H6",
        "query": "car",
        "kind": "no_route",
        "message": "no car route",
    },
]


def built(app: CityInstancesApp, folder: Path, failures: Sequence[Mapping[str, str]] = ()) -> str:
    create(app)
    app.client.patch(VERSION, json={"min_od_distance_m": 900})
    return build_fake_city(app.rig, folder, failures)


def test_the_stations_are_listed_as_items(instances_app: CityInstancesApp, tmp_path: Path) -> None:
    built(instances_app, tmp_path)

    response = instances_app.client.get(f"{VERSION}/stations")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 42
    assert set(items[0]) == {"station_id", "kind", "name", "lat", "lon"}
    assert {item["kind"] for item in items} == {"pt", "bs"}


def test_the_hubs_are_listed_with_their_outline_and_stations(
    instances_app: CityInstancesApp, tmp_path: Path
) -> None:
    built(instances_app, tmp_path)

    items = instances_app.client.get(f"{VERSION}/hubs").json()["items"]

    assert [item["hub_id"] for item in items] == ["H1", "H2", "H3", "H4", "H5", "H6"]
    assert set(items[0]) == {
        "hub_id",
        "label",
        "lat",
        "lon",
        "outline",
        "pt_station_ids",
        "bike_station_ids",
        "lines",
    }
    assert items[0]["outline"]["type"] == "Polygon"
    assert len(items[0]["pt_station_ids"]) == 5


def test_the_hub_pairs_default_to_the_only_period(
    instances_app: CityInstancesApp, tmp_path: Path
) -> None:
    built(instances_app, tmp_path)

    default = instances_app.client.get(f"{VERSION}/hub-pairs")
    named = instances_app.client.get(f"{VERSION}/hub-pairs", params={"period": PERIOD})

    assert default.status_code == 200
    assert default.json() == named.json()
    items = default.json()["items"]
    assert len(items) == 24
    assert set(items[0]) == {"origin_hub", "destination_hub", "demand", "euclid_dist_m"}


def test_the_route_pairs_list_the_pairs_the_routes_step_routed(
    instances_app: CityInstancesApp, tmp_path: Path
) -> None:
    built(instances_app, tmp_path)

    response = instances_app.client.get(f"{VERSION}/route-pairs")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 24
    assert set(items[0]) == {"origin_hub", "destination_hub"}


def test_a_version_not_built_yet_has_no_route_pairs_and_an_unknown_one_is_404(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    empty = instances_app.client.get(f"{VERSION}/route-pairs")
    unknown = instances_app.client.get("/api/v1/instance-versions/nope.v1/route-pairs")

    assert (empty.status_code, empty.json()) == (200, {"items": []})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "instance_version_not_found"


def test_a_version_not_built_yet_lists_nothing(instances_app: CityInstancesApp) -> None:
    create(instances_app)

    for name in ("stations", "hubs", "hub-pairs"):
        response = instances_app.client.get(f"{VERSION}/{name}")
        assert (response.status_code, response.json()) == (200, {"items": []})


def test_an_unknown_version_answers_404_instance_version_not_found(
    instances_app: CityInstancesApp,
) -> None:
    for name in ("stations", "hubs", "hub-pairs"):
        response = instances_app.client.get(f"/api/v1/instance-versions/nope.v1/{name}")
        assert response.status_code == 404
        assert response.json()["code"] == "instance_version_not_found"


def test_a_period_that_is_not_the_versions_answers_404_period_not_found(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    response = instances_app.client.get(f"{VERSION}/hub-pairs", params={"period": "x.mon-08"})

    assert response.status_code == 404
    assert response.json()["code"] == "period_not_found"


def test_the_route_failures_of_a_run_are_listed_with_their_period(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("r1", steps=(step(3, StepName.ROUTES, period=PERIOD),)))
    runs_app.route_failures.add(
        "r1", 3, PERIOD, RouteFailure("H1", "H6", "car", "no_route", "no car route", 1), T0
    )
    runs_app.route_failures.add(
        "r1", 3, PERIOD, RouteFailure("H1", "H2", "pt_bike", "technical", "timeout", 4), T0
    )

    response = runs_app.client.get("/api/v1/runs/r1/route-failures")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "origin_hub": "H1",
                "destination_hub": "H2",
                "query": "pt_bike",
                "kind": "technical",
                "message": "timeout",
                "attempts": 4,
                "period": PERIOD,
            },
            {
                "origin_hub": "H1",
                "destination_hub": "H6",
                "query": "car",
                "kind": "no_route",
                "message": "no car route",
                "attempts": 1,
                "period": PERIOD,
            },
        ]
    }


def test_a_run_without_failures_answers_an_empty_list(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("r1"))

    response = runs_app.client.get("/api/v1/runs/r1/route-failures")

    assert (response.status_code, response.json()) == (200, {"items": []})


def test_an_unknown_run_answers_404_run_not_found(runs_app: RunsApp) -> None:
    response = runs_app.client.get("/api/v1/runs/run-9/route-failures")

    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"
