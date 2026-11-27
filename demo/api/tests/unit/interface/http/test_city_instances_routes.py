import json
from dataclasses import replace
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.domain.instance_rules import RULE_IDS
from pricing_demo.domain.runs import RunState
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.builds import build_fake_city, unavailable
from tests.support.runs import make_run
from tests.unit.interface.http.conftest import SERVER_TIME, CityInstancesApp

CREATE = {
    "name": "Geneva 3 km",
    "dataset_id": "geneva-2026-11-26",
    "start_from": {"kind": "package_defaults"},
}


def create(app: CityInstancesApp, **fields: Any) -> dict[str, Any]:
    response = app.client.post("/api/v1/city-instances", json={**CREATE, **fields})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_creating_an_instance_answers_201_with_its_first_draft(
    instances_app: CityInstancesApp,
) -> None:
    response = instances_app.client.post("/api/v1/city-instances", json=CREATE)

    assert response.status_code == 201
    assert response.headers["location"] == "/api/v1/instance-versions/geneva-3km.v1"
    body = response.json()
    assert (body["id"], body["instance_id"], body["number"]) == ("geneva-3km.v1", "geneva-3km", 1)
    assert (body["status"], body["state"], body["based_on_id"]) == ("draft", "draft", None)
    assert body["counts"] is None
    assert body["changes"] == []
    assert body["parameters"]["seed"] == 42
    assert body["parameters"]["radius_m"] == 3000
    (period,) = body["periods"]
    assert period["id"] == "geneva-3km.v1.mon-08"
    assert period["label"] == "Monday 08:00–09:00"  # noqa: RUF001
    assert period["routing_date_provisional"] is True
    assert [rule["rule"] for rule in body["rules"]] == list(RULE_IDS)
    assert all(len(rule["values"]) == 2 for rule in body["rules"])


def test_creating_from_a_copy_is_based_on_the_version(instances_app: CityInstancesApp) -> None:
    create(instances_app)
    instances_app.client.patch("/api/v1/instance-versions/geneva-3km.v1", json={"radius_m": 4000})

    body = create(
        instances_app,
        name="Geneva 4 km",
        start_from={"kind": "copy", "instance_version_id": "geneva-3km.v1"},
    )

    assert body["based_on_id"] == "geneva-3km.v1"
    assert body["parameters"]["radius_m"] == 4000


def test_a_used_name_answers_409_name_taken(instances_app: CityInstancesApp) -> None:
    create(instances_app)

    response = instances_app.client.post("/api/v1/city-instances", json=CREATE)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "name_taken"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"dataset_id": "nope"}, "unknown_city_dataset"),
        ({"start_from": {"kind": "copy", "instance_version_id": "x.v1"}}, "unknown_start_version"),
        ({"name": "***"}, "invalid_instance_name"),
        ({"name": ""}, "validation_failed"),
        ({"start_from": {"kind": "other"}}, "validation_failed"),
        ({"start_from": {"kind": "copy"}}, "validation_failed"),
    ],
)
def test_a_request_that_cannot_be_served_answers_422(
    instances_app: CityInstancesApp, fields: dict[str, Any], code: str
) -> None:
    response = instances_app.client.post("/api/v1/city-instances", json={**CREATE, **fields})

    assert response.status_code == 422
    assert response.json()["code"] == code


def test_the_package_defaults_need_a_worker_that_reported() -> None:
    app = CityInstancesApp(with_fingerprint=False)

    response = app.client.post("/api/v1/city-instances", json=CREATE)

    assert response.status_code == 409
    assert response.json()["code"] == "package_defaults_missing"


def test_a_second_draft_answers_409_with_the_draft_id(instances_app: CityInstancesApp) -> None:
    create(instances_app)

    response = instances_app.client.post(
        "/api/v1/city-instances/geneva-3km/versions", json={"based_on_id": "geneva-3km.v1"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "draft_exists"
    assert response.json()["draft_id"] == "geneva-3km.v1"


def test_a_draft_takes_the_next_number_and_a_discarded_number_is_not_reused(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)
    path = "/api/v1/city-instances/geneva-3km/versions"
    body = {"based_on_id": "geneva-3km.v1"}

    second = instances_app.client.post(path, json=body)
    instances_app.client.delete("/api/v1/instance-versions/geneva-3km.v2")
    third = instances_app.client.post(path, json=body)

    assert second.status_code == third.status_code == 201
    assert second.headers["location"] == "/api/v1/instance-versions/geneva-3km.v2"
    assert third.json()["id"] == "geneva-3km.v3"
    assert third.json()["based_on_id"] == "geneva-3km.v1"


def test_a_draft_of_an_unknown_instance_or_base_is_refused(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)

    unknown_instance = instances_app.client.post(
        "/api/v1/city-instances/none/versions", json={"based_on_id": "geneva-3km.v1"}
    )
    unknown_base = instances_app.client.post(
        "/api/v1/city-instances/geneva-3km/versions", json={"based_on_id": "none.v1"}
    )

    assert unknown_instance.status_code == 404
    assert unknown_instance.json()["code"] == "city_instance_not_found"
    assert unknown_base.status_code == 422
    assert unknown_base.json()["code"] == "unknown_start_version"


def test_a_patch_stores_values_as_sent_and_reports_the_failed_rules(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    response = instances_app.client.patch(
        "/api/v1/instance-versions/geneva-3km.v1",
        json={"seed": 1.5, "radius_m": 6000, "fixed_capacity": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["parameters"]["seed"], body["parameters"]["radius_m"]) == (1.5, 6000)
    failed = {rule["rule"]: rule for rule in body["rules"] if not rule["passed"]}
    assert {"seed_whole_number", "radius_1_to_5_km", "docks_at_least_1"} <= set(failed)
    assert failed["radius_1_to_5_km"]["values"] == [
        {"name": "radius", "value": 6000, "unit": "m"},
        {"name": "allowed range", "value": "1 to 5 km", "unit": None},
    ]
    assert instances_app.client.get("/api/v1/instance-versions/geneva-3km.v1").json() == body


def test_a_patch_names_what_changes_against_the_base(instances_app: CityInstancesApp) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)
    instances_app.client.post(
        "/api/v1/city-instances/geneva-3km/versions", json={"based_on_id": "geneva-3km.v1"}
    )

    response = instances_app.client.patch(
        "/api/v1/instance-versions/geneva-3km.v2", json={"fixed_capacity": 25}
    )

    assert response.json()["changes"] == [
        {"parameter": "fixed_capacity", "before": 20, "after": 25}
    ]


@pytest.mark.parametrize(
    "patch",
    [
        {"seed": "42"},
        {"seed": True},
        {"radius_m": None},
        {"radius_m": [3000]},
        {"unknown": 1},
        {"radius_m": float("nan")},
    ],
)
def test_a_value_that_is_not_a_json_number_answers_422(
    instances_app: CityInstancesApp, patch: dict[str, Any]
) -> None:
    create(instances_app)

    response = instances_app.client.patch(
        "/api/v1/instance-versions/geneva-3km.v1", content=_json(patch)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_an_integer_a_double_cannot_hold_exactly_answers_422(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    response = instances_app.client.patch(
        "/api/v1/instance-versions/geneva-3km.v1", content=_json({"seed": 10**400})
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def _json(value: object) -> bytes:
    return json.dumps(value).encode()


def test_a_sealed_version_answers_409_to_a_patch(instances_app: CityInstancesApp) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)

    patch = instances_app.client.patch("/api/v1/instance-versions/geneva-3km.v1", json={"seed": 1})

    assert patch.status_code == 409
    assert patch.json()["code"] == "version_sealed"


def test_a_sealed_version_is_deleted_with_204(instances_app: CityInstancesApp) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)
    path = "/api/v1/instance-versions/geneva-3km.v1"

    assert instances_app.client.delete(path).status_code == 204
    assert instances_app.client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/instance-versions/geneva-3km.v1", "/city-instances/geneva-3km"])
def test_a_delete_answers_409_run_active_while_a_build_is_queued_or_running(
    instances_app: CityInstancesApp, path: str
) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)
    instances_app.runs.add(make_run("r1", subject_id="geneva-3km.v1", state=RunState.RUNNING))

    response = instances_app.client.delete(f"/api/v1{path}")

    assert response.status_code == 409
    assert (response.json()["code"], response.json()["run_id"]) == ("run_active", "r1")
    assert instances_app.instances.get_version("geneva-3km.v1") is not None


def test_a_city_instance_is_deleted_with_204_and_an_unknown_one_answers_404(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    deleted = instances_app.client.delete("/api/v1/city-instances/geneva-3km")
    unknown = instances_app.client.delete("/api/v1/city-instances/geneva-3km")

    assert deleted.status_code == 204
    assert instances_app.client.get("/api/v1/instance-versions/geneva-3km.v1").status_code == 404
    assert (unknown.status_code, unknown.json()["code"]) == (404, "city_instance_not_found")


def test_an_unknown_version_answers_404(instances_app: CityInstancesApp) -> None:
    path = "/api/v1/instance-versions/none.v1"

    responses = [
        instances_app.client.get(path),
        instances_app.client.patch(path, json={}),
        instances_app.client.delete(path),
    ]

    assert [item.status_code for item in responses] == [404, 404, 404]
    assert {item.json()["code"] for item in responses} == {"instance_version_not_found"}


def test_the_menu_lists_instances_and_their_versions(instances_app: CityInstancesApp) -> None:
    assert instances_app.client.get("/api/v1/city-instances").json() == {"items": []}
    create(instances_app)

    body = instances_app.client.get("/api/v1/city-instances").json()

    assert body == {
        "items": [
            {
                "id": "geneva-3km",
                "name": "Geneva 3 km",
                "dataset_id": "geneva-2026-11-26",
                "versions": [
                    {
                        "id": "geneva-3km.v1",
                        "number": 1,
                        "status": "draft",
                        "state": "draft",
                        "pricing_version_count": 0,
                    }
                ],
            }
        ]
    }


def test_discarding_the_only_draft_answers_204_and_deletes_the_instance(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    response = instances_app.client.delete("/api/v1/instance-versions/geneva-3km.v1")

    assert response.status_code == 204
    assert response.content == b""
    assert instances_app.client.get("/api/v1/city-instances").json() == {"items": []}
    assert instances_app.client.get("/api/v1/instance-versions/geneva-3km.v1").status_code == 404


VERSION = "/api/v1/instance-versions/geneva-3km.v1"
BUILDS = f"{VERSION}/builds"
STEPS = ["area", "hubs", "routes", "travellers_and_bikes"]


def valid_draft(app: CityInstancesApp) -> dict[str, Any]:
    """The package defaults tie the trip distance and the grouping distance: move one."""
    create(app)
    response = app.client.patch(VERSION, json={"min_od_distance_m": 900})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_a_draft_carries_its_build_plan_of_four_steps(instances_app: CityInstancesApp) -> None:
    created = create(instances_app)

    for body in (created, instances_app.client.get(VERSION).json()):
        plan = body["build_plan"]
        assert [item["step"] for item in plan["steps"]] == STEPS
        assert [item["number"] for item in plan["steps"]] == [1, 2, 3, 4]
        assert [item["period_id"] for item in plan["steps"]] == [
            None,
            None,
            "geneva-3km.v1.mon-08",
            "geneva-3km.v1.mon-08",
        ]
        assert all(len(item["input_key"]) == 64 for item in plan["steps"])
        assert {item["action"] for item in plan["steps"]} == {"rebuilt"}
        assert all(item["causes"] == [] for item in plan["steps"])
        assert all(item["last_duration_s"] is None for item in plan["steps"])
        assert plan["build_verdict"] == {"allowed": True, "reasons": []}


def test_a_patch_answers_the_plan_of_the_edited_draft(instances_app: CityInstancesApp) -> None:
    before = create(instances_app)["build_plan"]["steps"]

    after = instances_app.client.patch(VERSION, json={"seed": 7}).json()["build_plan"]["steps"]

    assert [a["input_key"] == b["input_key"] for a, b in zip(before, after, strict=True)] == [
        True,
        True,
        True,
        False,
    ]


def test_a_plan_without_a_fingerprint_has_no_keys_and_says_why() -> None:
    app = CityInstancesApp(with_fingerprint=False)
    app.fingerprints.record(FAKE_FINGERPRINT, SERVER_TIME)
    created = create(app)

    plan = created["build_plan"]

    assert [item["input_key"] for item in plan["steps"]] == [None] * 4
    assert {item["action"] for item in plan["steps"]} == {"rebuilt"}
    assert plan["build_verdict"]["allowed"] is False
    assert [item["component"] for item in plan["build_verdict"]["reasons"]] == ["package"]


def test_the_verdict_names_each_missing_component(instances_app: CityInstancesApp) -> None:
    create(instances_app)
    instances_app.status.value = unavailable(ComponentName.RUNNER, ComponentName.TRIP_PLANNER)

    verdict = instances_app.client.get(VERSION).json()["build_plan"]["build_verdict"]

    assert verdict == {
        "allowed": False,
        "reasons": [
            {"component": "runner", "reason": "runner is down."},
            {"component": "trip_planner", "reason": "trip_planner is down."},
        ],
    }


def test_a_build_answers_202_with_the_run_and_its_location(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 202
    assert response.headers["location"] == "/api/v1/runs/run-1"
    run = response.json()
    assert (run["id"], run["kind"], run["state"]) == ("run-1", "build", "queued")
    assert run["subject"] == {"type": "instance_version", "id": "geneva-3km.v1"}
    assert [item["step"] for item in run["steps"]] == STEPS
    assert {item["state"] for item in run["steps"]} == {"pending"}


def test_a_build_seals_the_version_and_its_state_follows_the_run(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)

    def read() -> tuple[str, str, str]:
        version = instances_app.client.get(VERSION).json()
        listed = instances_app.client.get("/api/v1/city-instances").json()["items"][0]["versions"]
        return version["status"], version["state"], listed[0]["state"]

    seen = [read()]
    for state in (RunState.RUNNING, RunState.SUCCEEDED):
        instances_app.runs.update("run-1", partial(replace, state=state))
        seen.append(read())

    assert seen == [
        ("sealed", "queued", "queued"),
        ("sealed", "building", "building"),
        ("sealed", "ready", "ready"),
    ]


def test_a_version_carries_the_id_of_its_latest_build_run(
    instances_app: CityInstancesApp,
) -> None:
    created = valid_draft(instances_app)
    assert created["build_run_id"] is None

    instances_app.client.post(BUILDS)

    assert instances_app.client.get(VERSION).json()["build_run_id"] == "run-1"
    listed = instances_app.client.get("/api/v1/city-instances").json()["items"][0]["versions"]
    assert "build_run_id" not in listed[0]


@pytest.mark.parametrize(("state", "expected"), [("failed", "failed"), ("cancelled", "cancelled")])
def test_the_state_of_a_version_is_its_failed_or_cancelled_build(
    instances_app: CityInstancesApp, state: str, expected: str
) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)
    instances_app.runs.update("run-1", lambda run: replace(run, state=RunState(state)))

    assert instances_app.client.get(VERSION).json()["state"] == expected


def test_a_draft_that_breaks_a_rule_answers_409_rule_broken_with_both_values(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "rule_broken"
    assert body["failures"] == [
        {
            "rule": "min_trip_distance_above_grouping",
            "passed": False,
            "values": [
                {"name": "minimum trip distance", "value": 500.0, "unit": "m"},
                {"name": "grouping distance", "value": 500.0, "unit": "m"},
            ],
        }
    ]
    assert instances_app.client.get(VERSION).json()["status"] == "draft"


def test_a_second_build_answers_409_run_active_with_the_run(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 409
    assert (response.json()["code"], response.json()["run_id"]) == ("run_active", "run-1")


def test_a_built_version_answers_409_already_built(instances_app: CityInstancesApp) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)
    instances_app.runs.update("run-1", lambda run: replace(run, state=RunState.SUCCEEDED))

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 409
    assert response.json()["code"] == "already_built"


def test_a_failed_build_is_queued_again_by_the_same_post(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)
    instances_app.runs.update("run-1", lambda run: replace(run, state=RunState.FAILED))

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 202
    assert response.headers["location"] == "/api/v1/runs/run-2"


def test_a_missing_component_answers_503_with_its_reasons_and_nothing_is_sealed(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)
    instances_app.status.value = unavailable(ComponentName.RUNNER)

    response = instances_app.client.post(BUILDS)

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "component_unavailable"
    assert body["reasons"] == [{"component": "runner", "reason": "runner is down."}]
    assert instances_app.client.get(VERSION).json()["status"] == "draft"


def test_building_an_unknown_version_answers_404(instances_app: CityInstancesApp) -> None:
    response = instances_app.client.post("/api/v1/instance-versions/nope.v1/builds")

    assert response.status_code == 404
    assert response.json()["code"] == "instance_version_not_found"


def build_with_failures(app: CityInstancesApp, folder: Path, failures: list[dict[str, str]]) -> str:
    create(app)
    app.client.patch("/api/v1/instance-versions/geneva-3km.v1", json={"min_od_distance_m": 900})
    return build_fake_city(app.rig, folder, failures)


def test_a_built_version_reports_five_headline_counts_and_the_routes_summary(
    instances_app: CityInstancesApp, tmp_path: Path
) -> None:
    run_id = build_with_failures(
        instances_app,
        tmp_path,
        [
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
        ],
    )

    body = instances_app.client.get("/api/v1/instance-versions/geneva-3km.v1").json()

    assert list(body["counts"]) == [
        "stops",
        "bike_stations",
        "hubs",
        "hub_pairs_with_routes",
        "travellers",
    ]
    assert body["counts"]["stops"] == {
        "value": 30,
        "unit": "stops",
        "source": "input",
        "group": "headline",
    }
    assert body["counts"]["hub_pairs_with_routes"]["value"] == 23
    assert all(
        (item["source"], item["group"]) == ("input", "headline") for item in body["counts"].values()
    )
    assert body["routes"] == {
        "queries": 48,
        "queries_failed": 2,
        "failure_pct": pytest.approx(100 * 2 / 48),
        "pairs_without_public_transport": 1,
        "pairs_without_car": 1,
        "retries": 3,
        "run_id": run_id,
    }


def test_a_version_that_is_not_built_has_no_counts_and_no_routes(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)

    body = instances_app.client.get("/api/v1/instance-versions/geneva-3km.v1").json()

    assert body["counts"] is None
    assert body["routes"] is None


def test_a_sealed_version_carries_the_instant_it_was_saved_and_a_draft_none(
    instances_app: CityInstancesApp,
) -> None:
    draft = valid_draft(instances_app)
    assert draft["sealed_at"] is None

    instances_app.client.post(BUILDS)
    body = instances_app.client.get(VERSION).json()

    assert body["status"] == "sealed"
    assert datetime.fromisoformat(body["sealed_at"]) == instances_app.clock.now()


def test_a_draft_answers_its_creation_instant_and_the_package_defaults(
    instances_app: CityInstancesApp,
) -> None:
    created = create(instances_app)

    patched = instances_app.client.patch(VERSION, json={"radius_m": 4000, "seed": 7}).json()
    fetched = instances_app.client.get(VERSION).json()

    for body in (created, patched, fetched):
        assert datetime.fromisoformat(body["created_at"]) == SERVER_TIME
        # The values `POST /city-instances` from the package defaults starts with.
        assert body["package_defaults"] == created["parameters"]
    assert patched["parameters"]["radius_m"] == 4000


def test_a_sealed_version_answers_null_package_defaults(
    instances_app: CityInstancesApp,
) -> None:
    valid_draft(instances_app)
    instances_app.client.post(BUILDS)

    body = instances_app.client.get(VERSION).json()

    assert body["package_defaults"] is None
    assert datetime.fromisoformat(body["created_at"]) == SERVER_TIME


def test_a_draft_answers_null_package_defaults_while_no_package_is_recorded() -> None:
    app = CityInstancesApp(with_fingerprint=False)
    app.fingerprints.record(FAKE_FINGERPRINT, SERVER_TIME)
    create(app)
    app.fingerprints.clear()

    body = app.client.get(VERSION).json()

    assert body["package_defaults"] is None
