import pytest

from tests.unit.interface.http.conftest import Faked


def stored(faked: Faked) -> dict[str, dict[str, object]]:
    return faked.settings.read()["components"]  # type: ignore[return-value]


def test_a_component_is_written_to_the_settings_then_reset_to_the_defaults(faked: Faked) -> None:
    put = faked.client.put(
        "/api/test-control/components/trip_planner",
        json={"state": "unavailable", "reason": "No answer from OpenTripPlanner."},
    )

    assert put.status_code == 204
    assert stored(faked)["trip_planner"] == {
        "state": "unavailable",
        "reason": "No answer from OpenTripPlanner.",
    }

    reset = faked.client.post("/api/test-control/reset")

    assert reset.status_code == 204
    assert {name: entry["state"] for name, entry in stored(faked).items()} == {
        "solver": "available",
        "package": "available",
        "trip_planner": "available",
    }


def test_the_solver_can_be_set_limited(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/solver",
        json={"state": "limited", "reason": "Size-limited."},
    )

    assert response.status_code == 204
    assert stored(faked)["solver"] == {"state": "limited", "reason": "Size-limited."}


@pytest.mark.parametrize("name", ["package", "trip_planner"])
def test_limited_is_refused_for_every_component_but_the_solver(faked: Faked, name: str) -> None:
    response = faked.client.put(
        f"/api/test-control/components/{name}", json={"state": "limited", "reason": "Small."}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_status"
    assert "components" not in faked.settings.read() or name not in stored(faked)


def test_setting_a_component_without_a_reason_to_unavailable_is_refused(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/solver", json={"state": "unavailable", "reason": None}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_status"


@pytest.mark.parametrize("name", ["storage", "runner"])
def test_a_component_that_is_not_faked_cannot_be_set(faked: Faked, name: str) -> None:
    response = faked.client.put(
        f"/api/test-control/components/{name}",
        json={"state": "unavailable", "reason": "Down."},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "component_not_controllable"


def test_an_unknown_component_name_is_refused(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/database", json={"state": "available"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "name"


def test_a_city_data_set_is_inserted_and_a_reset_removes_it(
    faked_without_city_data: Faked,
) -> None:
    faked = faked_without_city_data
    assert faked.client.get("/api/v1/system-status").json()["components"][5]["state"] == (
        "unavailable"
    )

    created = faked.client.post("/api/test-control/city-datasets")

    assert created.status_code == 201
    assert created.json() == {"id": "geneva-2026-11-26"}
    body = faked.client.get("/api/v1/system-status").json()
    assert body["components"][5] == {"name": "city_data", "state": "available", "reason": None}
    assert faked.client.post("/api/test-control/city-datasets").json() == {
        "id": "geneva-2026-11-26-2"
    }

    assert faked.client.post("/api/test-control/reset").status_code == 204
    assert faked.client.get("/api/v1/system-status").json()["components"][5]["state"] == (
        "unavailable"
    )


def test_city_data_cannot_be_controlled_like_a_probed_component(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/city_data", json={"state": "available"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "component_not_controllable"
