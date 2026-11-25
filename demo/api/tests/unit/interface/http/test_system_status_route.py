from tests.unit.interface.http.conftest import API_VERSION, Faked


def test_every_component_is_reported_as_available_by_default(faked: Faked) -> None:
    response = faked.client.get("/api/v1/system-status")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "api_version": API_VERSION,
        "components": [
            {"name": "storage", "available": True, "reason": None},
            {"name": "pricing_model", "available": True, "reason": None},
            {"name": "solver", "available": True, "reason": None},
            {"name": "trip_planner", "available": True, "reason": None},
        ],
        "can_read_stored_results": True,
        "can_start_runs": True,
    }


def test_an_unavailable_component_blocks_runs_and_says_why(faked: Faked) -> None:
    faked.client.put(
        "/api/test-control/components/solver",
        json={"available": False, "reason": "No Gurobi licence was found."},
    )

    body = faked.client.get("/api/v1/system-status").json()

    assert body["components"][2] == {
        "name": "solver",
        "available": False,
        "reason": "No Gurobi licence was found.",
    }
    assert body["can_read_stored_results"] is True
    assert body["can_start_runs"] is False
