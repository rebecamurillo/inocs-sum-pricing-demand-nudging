from tests.unit.interface.http.conftest import Faked


def test_a_component_is_set_unavailable_then_reset(faked: Faked) -> None:
    put = faked.client.put(
        "/api/test-control/components/trip_planner",
        json={"available": False, "reason": "No answer from OpenTripPlanner."},
    )
    assert put.status_code == 204
    assert faked.client.get("/api/v1/system-status").json()["can_start_runs"] is False

    reset = faked.client.post("/api/test-control/reset")

    assert reset.status_code == 204
    assert faked.client.get("/api/v1/system-status").json()["can_start_runs"] is True


def test_setting_a_component_without_a_reason_to_unavailable_is_refused(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/solver", json={"available": False, "reason": None}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_component_status"


def test_a_component_that_is_not_faked_cannot_be_set(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/storage",
        json={"available": False, "reason": "Down."},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "component_not_controllable"
    assert faked.client.get("/api/v1/system-status").json()["can_read_stored_results"] is True


def test_an_unknown_component_name_is_refused(faked: Faked) -> None:
    response = faked.client.put("/api/test-control/components/database", json={"available": True})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "name"
