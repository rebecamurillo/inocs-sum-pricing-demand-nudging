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


PRICING_MODEL = "/api/test-control/pricing-model"


def test_the_pricing_model_settings_are_written_as_sent(faked: Faked) -> None:
    response = faked.client.put(
        PRICING_MODEL,
        json={
            "fail_at": {"step": "routes", "code": "trip_planner_unreachable"},
            "hold_at": "hubs",
            "routes_pace_ms": 50,
        },
    )

    assert response.status_code == 204
    assert faked.settings.read()["pricing_model"] == {
        "fail_at": {"step": "routes", "code": "trip_planner_unreachable"},
        "hold_at": "hubs",
        "routes_pace_ms": 50,
    }


ROUTE_FAILURE = {
    "origin_hub": "H1",
    "destination_hub": "H2",
    "query": "pt_bike",
    "kind": "technical",
    "message": "timeout",
}


def test_failed_route_queries_are_written_as_sent(faked: Faked) -> None:
    response = faked.client.put(PRICING_MODEL, json={"route_failures": [ROUTE_FAILURE]})

    assert response.status_code == 204
    assert faked.settings.read()["pricing_model"]["route_failures"] == [ROUTE_FAILURE]  # type: ignore[index]


@pytest.mark.parametrize("field", ["query", "kind"])
def test_a_failed_route_query_of_an_unknown_kind_is_refused(faked: Faked, field: str) -> None:
    response = faked.client.put(
        PRICING_MODEL, json={"route_failures": [{**ROUTE_FAILURE, field: "other"}]}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"].startswith(f"route_failures.0.{field}")


def test_the_licence_kind_is_stored_only_when_given(faked: Faked) -> None:
    faked.client.put(PRICING_MODEL, json={"licence_kind": "limited"})
    assert faked.settings.read()["pricing_model"]["licence_kind"] == "limited"  # type: ignore[index]

    faked.client.put(PRICING_MODEL, json={})

    assert "licence_kind" not in faked.settings.read()["pricing_model"]  # type: ignore[operator]


def test_the_pricing_model_step_can_be_failed_through_the_route(faked: Faked) -> None:
    body = {"fail_at": {"step": "pricing_model", "code": "solver_size_limited"}}

    assert faked.client.put(PRICING_MODEL, json=body).status_code == 204
    assert faked.settings.read()["pricing_model"]["fail_at"] == body["fail_at"]  # type: ignore[index]


def test_an_empty_body_sets_the_defaults_of_the_pricing_model(faked: Faked) -> None:
    faked.client.put(PRICING_MODEL, json={"hold_at": "area"})

    response = faked.client.put(PRICING_MODEL, json={})

    assert response.status_code == 204
    assert faked.settings.read()["pricing_model"] == {
        "fail_at": None,
        "hold_at": None,
        "routes_pace_ms": 0,
    }


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"fail_at": {"step": "routes", "code": "nonsense"}}, "fail_at.code"),
        ({"fail_at": {"step": "nowhere", "code": "stage_error"}}, "fail_at.step"),
        ({"hold_at": "nowhere"}, "hold_at"),
        ({"routes_pace_ms": -1}, "routes_pace_ms"),
    ],
)
def test_a_pricing_model_setting_that_is_not_valid_is_refused(
    faked: Faked, body: dict[str, object], field: str
) -> None:
    response = faked.client.put(PRICING_MODEL, json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert response.json()["errors"][0]["field"].startswith(field)
    assert "pricing_model" not in faked.settings.read()


def test_a_run_is_released_and_a_reset_forgets_the_release_and_the_settings(
    faked: Faked,
) -> None:
    faked.client.put(PRICING_MODEL, json={"hold_at": "routes"})

    first = faked.client.post("/api/test-control/runs/run-1/release")
    again = faked.client.post("/api/test-control/runs/run-1/release")

    assert (first.status_code, again.status_code) == (204, 204)
    assert faked.settings.read()["released_runs"] == ["run-1"]
    faked.client.post("/api/test-control/reset")
    assert "released_runs" not in faked.settings.read()
    assert "pricing_model" not in faked.settings.read()


def test_the_simulation_rule_is_stored_only_when_given(faked: Faked) -> None:
    staged = {"version": 2, "price_weight": 0.6, "time_weight": 0.4}
    assert faked.client.put(PRICING_MODEL, json={"simulation_rule": staged}).status_code == 204
    assert faked.settings.read()["pricing_model"]["simulation_rule"] == staged  # type: ignore[index]

    faked.client.put(PRICING_MODEL, json={})

    assert "simulation_rule" not in faked.settings.read()["pricing_model"]  # type: ignore[operator]


@pytest.mark.parametrize(
    "rule",
    [
        {"version": 1, "price_weight": 0.6, "time_weight": 0.4},
        {"version": 2, "price_weight": 1.5, "time_weight": 0.4},
        {"version": 2, "price_weight": 0.6, "time_weight": -0.1},
        {"version": 2, "price_weight": 0.6},
    ],
)
def test_a_staged_rule_below_version_2_or_with_a_weight_outside_0_to_1_is_refused(
    faked: Faked, rule: dict[str, object]
) -> None:
    response = faked.client.put(PRICING_MODEL, json={"simulation_rule": rule})

    assert response.status_code == 422
    assert "simulation_rule" in response.json()["errors"][0]["field"]
