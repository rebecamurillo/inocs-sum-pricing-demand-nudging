import json
from typing import Any

import pytest

from pricing_demo.domain.instance_rules import RULE_IDS
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


def test_a_sealed_version_answers_409_to_a_patch_and_a_delete(
    instances_app: CityInstancesApp,
) -> None:
    create(instances_app)
    instances_app.instances.seal("geneva-3km.v1", SERVER_TIME)
    path = "/api/v1/instance-versions/geneva-3km.v1"

    patch = instances_app.client.patch(path, json={"seed": 1})
    delete = instances_app.client.delete(path)

    assert (patch.status_code, delete.status_code) == (409, 409)
    assert patch.json()["code"] == delete.json()["code"] == "version_sealed"


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
