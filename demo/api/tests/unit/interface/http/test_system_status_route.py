from tests.unit.interface.http.conftest import Faked

ALLOWED = {"allowed": True, "reasons": []}


def test_every_component_is_available_and_every_action_can_start_by_default(faked: Faked) -> None:
    response = faked.client.get("/api/v1/system-status")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "components": [
            {"name": "storage", "state": "available", "reason": None},
            {"name": "runner", "state": "available", "reason": None},
            {"name": "solver", "state": "available", "reason": None},
            {"name": "package", "state": "available", "reason": None},
            {"name": "trip_planner", "state": "available", "reason": None},
            {"name": "city_data", "state": "available", "reason": None},
        ],
        "can_build_instances": ALLOWED,
        "can_run_pricing": ALLOWED,
        "can_simulate": ALLOWED,
    }


def test_an_unavailable_trip_planner_refuses_builds_only_and_says_why(faked: Faked) -> None:
    faked.client.put(
        "/api/test-control/components/trip_planner",
        json={"state": "unavailable", "reason": "No answer from OpenTripPlanner."},
    )
    faked.report_cycle()

    body = faked.client.get("/api/v1/system-status").json()

    assert body["components"][4] == {
        "name": "trip_planner",
        "state": "unavailable",
        "reason": "No answer from OpenTripPlanner.",
    }
    assert body["can_build_instances"] == {
        "allowed": False,
        "reasons": [{"component": "trip_planner", "reason": "No answer from OpenTripPlanner."}],
    }
    assert body["can_run_pricing"] == ALLOWED
    assert body["can_simulate"] == ALLOWED


def test_a_limited_solver_refuses_pricing_runs_only(faked: Faked) -> None:
    faked.client.put(
        "/api/test-control/components/solver",
        json={"state": "limited", "reason": "Size-limited licence."},
    )
    faked.report_cycle()

    body = faked.client.get("/api/v1/system-status").json()

    assert body["components"][2]["state"] == "limited"
    assert body["can_run_pricing"]["reasons"] == [
        {"component": "solver", "reason": "Size-limited licence."}
    ]
    assert body["can_build_instances"] == ALLOWED
    assert body["can_simulate"] == ALLOWED


def test_the_answer_has_no_trace_of_the_old_shape(faked: Faked) -> None:
    body = faked.client.get("/api/v1/system-status").json()

    assert set(body) == {"components", "can_build_instances", "can_run_pricing", "can_simulate"}


def test_without_a_city_data_set_builds_are_refused_with_that_reason(
    faked_without_city_data: Faked,
) -> None:
    body = faked_without_city_data.client.get("/api/v1/system-status").json()

    assert body["components"][5] == {
        "name": "city_data",
        "state": "unavailable",
        "reason": "No city data is imported yet",
    }
    assert body["can_build_instances"] == {
        "allowed": False,
        "reasons": [{"component": "city_data", "reason": "No city data is imported yet"}],
    }
    assert body["can_run_pricing"] == ALLOWED
    assert body["can_simulate"] == ALLOWED
