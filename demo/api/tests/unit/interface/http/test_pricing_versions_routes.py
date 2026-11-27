from dataclasses import replace
from datetime import timedelta

import pytest

from pricing_demo.domain.runs import RunKind, RunState, StepState
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus
from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule
from tests.support.builds import unavailable
from tests.support.pricing_versions import built_in_memory, sealed_pricing_version
from tests.support.simulations import simulate_under
from tests.unit.interface.http.conftest import CityInstancesApp

VERSION = "geneva-3km.v1"
LIST = f"/api/v1/instance-versions/{VERSION}/pricing-versions"


def built(app: CityInstancesApp) -> None:
    built_in_memory(app.rig)


def test_a_draft_is_created_with_201_and_its_location(instances_app: CityInstancesApp) -> None:
    built(instances_app)

    response = instances_app.client.post(LIST, json={})

    assert response.status_code == 201
    assert response.headers["Location"] == "/api/v1/pricing-versions/geneva-3km.v1.A"
    body = response.json()
    assert [body[key] for key in ("id", "letter", "name", "status", "state")] == [
        "geneva-3km.v1.A",
        "A",
        "Version A",
        "draft",
        "draft",
    ]
    assert body["goals"] == {
        "cost_bike_chf": 0.6,
        "lowest_price_chf": 0.6,
        "ridership_weight": 8.0,
        "station_balance_weight": 0.5,
        "pt_fare_chf": 2.0,
        "car_parking_fee_chf": 2.8,
        "max_displayed_options": 10.0,
        "flat_price_kind": "per_ride",
        "flat_price_per_ride_chf": 1.0,
    }
    assert [period["id"] for period in body["periods"]] == ["geneva-3km.v1.mon-08"]
    assert body["instance_version_id"] == VERSION
    assert all(rule["passed"] for rule in body["rules"])


def test_a_named_draft_based_on_another_copies_its_goals(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    first = instances_app.client.post(LIST, json={}).json()
    instances_app.client.patch(f"/api/v1/pricing-versions/{first['id']}", json={"pt_fare_chf": 3})

    response = instances_app.client.post(LIST, json={"name": "Copy", "based_on": first["id"]})

    body = response.json()
    assert (body["letter"], body["name"], body["based_on_id"]) == ("B", "Copy", first["id"])
    assert body["goals"]["pt_fare_chf"] == 3


def test_a_version_that_is_not_built_answers_409(instances_app: CityInstancesApp) -> None:
    instances_app.rig.add_draft()

    response = instances_app.client.post(LIST, json={})

    assert (response.status_code, response.json()["code"]) == (409, "instance_not_built")


def test_an_unknown_instance_version_and_an_unknown_based_on(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)

    missing = instances_app.client.post("/api/v1/instance-versions/x.v1/pricing-versions", json={})
    unknown = instances_app.client.post(LIST, json={"based_on": "geneva-3km.v1.Q"})

    assert (missing.status_code, missing.json()["code"]) == (404, "instance_version_not_found")
    assert (unknown.status_code, unknown.json()["code"]) == (422, "unknown_based_on")
    assert instances_app.client.post(LIST, json={"nope": 1}).status_code == 422


def test_a_change_answers_the_rule_results_and_keeps_the_value(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    path = "/api/v1/pricing-versions/geneva-3km.v1.A"

    response = instances_app.client.patch(
        path, json={"lowest_price_chf": -0.5, "max_displayed_options": 0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["goals"]["lowest_price_chf"] == -0.5
    assert [rule["message"] for rule in body["rules"] if not rule["passed"]] == [
        "Lowest price of a ride must be 0 or more: now -0.5",
        "Options shown per hub pair must be at least 1: now 0",
    ]
    assert instances_app.client.get(path).json()["goals"]["lowest_price_chf"] == -0.5


def test_a_patch_refuses_what_is_not_a_goal_or_a_number(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    path = "/api/v1/pricing-versions/geneva-3km.v1.A"

    assert instances_app.client.patch(path, json={"letter": "Z"}).status_code == 422
    assert instances_app.client.patch(path, json={"pt_fare_chf": "2"}).status_code == 422


def test_a_sealed_version_answers_409_version_sealed(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    sealed_pricing_version(instances_app.rig, "geneva-3km.v1.A", RunState.SUCCEEDED)

    response = instances_app.client.patch(
        "/api/v1/pricing-versions/geneva-3km.v1.A", json={"pt_fare_chf": 1}
    )

    assert (response.status_code, response.json()["code"]) == (409, "version_sealed")


def test_the_list_and_the_read_carry_the_state(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    instances_app.client.post(LIST, json={})
    sealed_pricing_version(instances_app.rig, "geneva-3km.v1.B", RunState.RUNNING)

    listed = instances_app.client.get(LIST).json()["items"]

    assert [(item["letter"], item["state"]) for item in listed] == [
        ("A", "draft"),
        ("B", "running"),
    ]
    one = instances_app.client.get("/api/v1/pricing-versions/geneva-3km.v1.B")
    assert one.json()["state"] == "running"
    assert instances_app.client.get("/api/v1/pricing-versions/x.A").status_code == 404
    assert (
        instances_app.client.get("/api/v1/instance-versions/x.v1/pricing-versions").status_code
        == 404
    )


def test_a_delete_answers_204_then_404_and_409_while_a_run_is_active(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    instances_app.client.post(LIST, json={})
    sealed_pricing_version(instances_app.rig, "geneva-3km.v1.B", RunState.QUEUED)

    active = instances_app.client.delete("/api/v1/pricing-versions/geneva-3km.v1.B")
    gone = instances_app.client.delete("/api/v1/pricing-versions/geneva-3km.v1.A")

    assert (active.status_code, active.json()["code"]) == (409, "run_active")
    assert gone.status_code == 204
    assert instances_app.client.get("/api/v1/pricing-versions/geneva-3km.v1.A").status_code == 404
    assert (
        instances_app.client.delete("/api/v1/pricing-versions/geneva-3km.v1.A").status_code == 404
    )


def test_the_menu_lists_the_letters_of_each_version(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    instances_app.client.post(LIST, json={})

    (item,) = instances_app.client.get("/api/v1/city-instances").json()["items"]

    (version,) = item["versions"]
    assert (version["pricing_version_count"], version["pricing_version_letters"]) == (2, ["A", "B"])


def test_deleting_a_version_or_an_instance_with_pricing_versions_needs_the_flag(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    instances_app.client.post(LIST, json={})
    version = f"/api/v1/instance-versions/{VERSION}"
    instance = "/api/v1/city-instances/geneva-3km"

    for path in (version, instance):
        refused = instances_app.client.delete(path)
        assert (refused.status_code, refused.json()["code"]) == (409, "has_pricing_versions")
        assert refused.json()["pricing_version_ids"] == ["geneva-3km.v1.A", "geneva-3km.v1.B"]
        assert instances_app.client.get(version).status_code == 200

    assert (
        instances_app.client.delete(instance + "?including_pricing_versions=true").status_code
        == 204
    )
    assert instances_app.client.get(version).status_code == 404
    assert instances_app.client.get(LIST).status_code == 404


def test_the_flag_also_deletes_a_version(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    path = f"/api/v1/instance-versions/{VERSION}?including_pricing_versions=true"

    assert instances_app.client.delete(path).status_code == 204
    assert instances_app.client.get("/api/v1/pricing-versions/geneva-3km.v1.A").status_code == 404


def runs_path(version_id: str) -> str:
    return f"/api/v1/pricing-versions/{version_id}/runs"


def a_draft(app: CityInstancesApp) -> str:
    built(app)
    return str(app.client.post(LIST, json={}).json()["id"])


def test_running_a_draft_answers_202_with_the_run_and_its_location(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)

    response = instances_app.client.post(runs_path(version))

    assert response.status_code == 202
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/runs/{body['id']}"
    assert (body["kind"], body["state"]) == ("pricing", "queued")
    assert body["subject"] == {"type": "pricing_version", "id": version}
    assert [(item["step"], item["state"]) for item in body["steps"]] == [
        ("pricing_model", "pending"),
        ("traveller_simulation", "pending"),
    ]
    sealed = instances_app.client.get(f"/api/v1/pricing-versions/{version}").json()
    assert (sealed["status"], sealed["state"]) == ("sealed", "queued")


def test_an_unknown_version_answers_404(instances_app: CityInstancesApp) -> None:
    response = instances_app.client.post(runs_path("geneva-3km.v1.Q"))

    assert (response.status_code, response.json()["code"]) == (404, "pricing_version_not_found")


def test_a_draft_that_breaks_a_rule_answers_409_naming_each_value_and_seals_nothing(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)
    instances_app.client.patch(
        f"/api/v1/pricing-versions/{version}", json={"pt_fare_chf": -1, "max_displayed_options": 0}
    )

    response = instances_app.client.post(runs_path(version))

    assert (response.status_code, response.json()["code"]) == (409, "rule_broken")
    failures = response.json()["pricing_failures"]
    assert [(item["field"], item["value"]) for item in failures] == [
        ("pt_fare_chf", -1),
        ("max_displayed_options", 0),
    ]
    assert all("now" in item["message"] for item in failures)
    assert instances_app.client.get(f"/api/v1/pricing-versions/{version}").json()["status"] == (
        "draft"
    )


def test_a_version_with_an_active_run_answers_409_run_active_with_the_run(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)
    first = instances_app.client.post(runs_path(version)).json()

    response = instances_app.client.post(runs_path(version))

    assert (response.status_code, response.json()["code"]) == (409, "run_active")
    assert response.json()["run_id"] == first["id"]


def test_a_version_whose_last_run_succeeded_answers_409_already_run(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)
    instances_app.rig.pricing.seal(version, instances_app.clock.now())
    sealed_pricing_version(instances_app.rig, version, RunState.SUCCEEDED)

    response = instances_app.client.post(runs_path(version))

    assert (response.status_code, response.json()["code"]) == (409, "already_run")


def test_a_failed_run_is_run_again_with_the_same_request(instances_app: CityInstancesApp) -> None:
    version = a_draft(instances_app)
    instances_app.rig.pricing.seal(version, instances_app.clock.now())
    sealed_pricing_version(instances_app.rig, version, RunState.FAILED)

    response = instances_app.client.post(runs_path(version))

    assert response.status_code == 202
    assert response.json()["state"] == "queued"


def test_a_component_the_run_needs_blocks_it_with_503_naming_the_reasons(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)
    instances_app.status.value = SystemStatus.of(
        [
            ComponentStatus.limited(ComponentName.SOLVER, "Size-limited Gurobi licence.")
            if name is ComponentName.SOLVER
            else ComponentStatus.ready(name)
            for name in ComponentName
        ]
    )

    response = instances_app.client.post(runs_path(version))

    assert (response.status_code, response.json()["code"]) == (503, "component_unavailable")
    assert response.json()["reasons"] == [
        {"component": "solver", "reason": "Size-limited Gurobi licence."}
    ]
    assert instances_app.client.get(f"/api/v1/pricing-versions/{version}").json()["status"] == (
        "draft"
    )


SIMULATIONS = "/api/v1/pricing-versions/{}/simulations"
V1 = BalancedScore()
V2 = BalancedScore(0.6, 0.4, rule_version=2)


def a_result(app: CityInstancesApp, current: BalancedScore | None = V2) -> str:
    """A sealed version whose pricing run succeeded and whose simulations used rule v1, with a
    live worker that records `current`."""
    version = a_draft(app)
    sealed_pricing_version(app.rig, version, RunState.SUCCEEDED)
    simulate_under(app.rig.simulations, version, f"{VERSION}.mon-08", V1)
    app.status.value = replace(
        app.status.value,
        simulation_rule=None if current is None else SimulationRule.of(current),
    )
    return version


def test_simulating_a_version_answers_202_with_the_run_and_its_location(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert response.status_code == 202
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/runs/{body['id']}"
    assert (body["kind"], body["state"]) == ("simulation", "queued")
    assert body["subject"] == {"type": "pricing_version", "id": version}
    assert [(item["step"], item["state"], item["period"]) for item in body["steps"]] == [
        ("traveller_simulation", "pending", f"{VERSION}.mon-08")
    ]


def test_simulating_an_unknown_version_answers_404(instances_app: CityInstancesApp) -> None:
    response = instances_app.client.post(SIMULATIONS.format("geneva-3km.v1.Q"))

    assert (response.status_code, response.json()["code"]) == (404, "pricing_version_not_found")


def test_simulating_a_version_with_an_active_run_answers_409_run_active_with_the_run(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    first = instances_app.client.post(SIMULATIONS.format(version)).json()

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert (response.status_code, response.json()["code"]) == (409, "run_active")
    assert response.json()["run_id"] == first["id"]


@pytest.mark.parametrize("state", [RunState.FAILED, RunState.CANCELLED])
def test_simulating_a_version_without_a_succeeded_pricing_run_answers_409_no_result(
    instances_app: CityInstancesApp, state: RunState
) -> None:
    version = a_draft(instances_app)
    sealed_pricing_version(instances_app.rig, version, state)

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert (response.status_code, response.json()["code"]) == (409, "no_result")


def test_simulating_a_draft_answers_409_no_result_and_queues_nothing(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert (response.status_code, response.json()["code"]) == (409, "no_result")
    assert [run.kind for run in instances_app.runs.list_by_states(list(RunState))] == [
        RunKind.BUILD
    ]


def test_simulating_a_version_already_simulated_with_the_current_rule_answers_409(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    simulate_under(instances_app.rig.simulations, version, f"{VERSION}.mon-08", V2)

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert (response.status_code, response.json()["code"]) == (409, "simulation_current")


def test_without_a_worker_a_simulation_is_refused_with_503_naming_the_reasons(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    instances_app.status.value = unavailable(ComponentName.RUNNER)

    response = instances_app.client.post(SIMULATIONS.format(version))

    assert (response.status_code, response.json()["code"]) == (503, "component_unavailable")
    assert [item["component"] for item in response.json()["reasons"]] == ["runner"]


def test_a_missing_solver_and_trip_planner_do_not_refuse_a_simulation(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    instances_app.status.value = replace(
        unavailable(ComponentName.SOLVER, ComponentName.TRIP_PLANNER),
        simulation_rule=SimulationRule.of(V2),
    )

    assert instances_app.client.post(SIMULATIONS.format(version)).status_code == 202


def test_the_simulations_of_a_version_are_listed_with_their_rule_and_whether_it_is_current(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    simulate_under(instances_app.rig.simulations, version, f"{VERSION}.mon-08", V2)

    response = instances_app.client.get(SIMULATIONS.format(version))

    assert response.status_code == 200
    items = response.json()["items"]
    assert [
        (item["period_id"], item["price_scheme"], item["rule_id"], item["rule_version"])
        for item in items
    ] == [
        (f"{VERSION}.mon-08", "flat", "balanced-score", 1),
        (f"{VERSION}.mon-08", "flat", "balanced-score", 2),
        (f"{VERSION}.mon-08", "model_prices", "balanced-score", 1),
        (f"{VERSION}.mon-08", "model_prices", "balanced-score", 2),
    ]
    assert [item["rule_current"] for item in items] == [False, True, False, True]
    assert items[0]["rule_parameters"] == {"price_weight": 0.5, "time_weight": 0.5}
    assert items[1]["rule_parameters"] == {"price_weight": 0.6, "time_weight": 0.4}
    assert set(items[0]) == {
        "period_id",
        "price_scheme",
        "rule_id",
        "rule_version",
        "rule_parameters",
        "rule_current",
        "simulation_key",
        "created_at",
    }
    assert items[0]["simulation_key"].startswith(version)


def test_no_simulation_is_current_without_a_live_worker(instances_app: CityInstancesApp) -> None:
    version = a_result(instances_app, current=None)

    items = instances_app.client.get(SIMULATIONS.format(version)).json()["items"]

    assert len(items) == 2
    assert [item["rule_current"] for item in items] == [False, False]


def test_a_version_without_simulations_lists_nothing_and_an_unknown_one_is_404(
    instances_app: CityInstancesApp,
) -> None:
    version = a_draft(instances_app)

    empty = instances_app.client.get(SIMULATIONS.format(version))
    unknown = instances_app.client.get(SIMULATIONS.format("geneva-3km.v1.Q"))

    assert (empty.status_code, empty.json()) == (200, {"items": []})
    assert (unknown.status_code, unknown.json()["code"]) == (404, "pricing_version_not_found")


def test_the_version_stays_a_result_while_a_simulation_run_is_queued(
    instances_app: CityInstancesApp,
) -> None:
    version = a_result(instances_app)
    instances_app.client.post(SIMULATIONS.format(version))

    body = instances_app.client.get(f"/api/v1/pricing-versions/{version}").json()

    assert body["state"] == "result"
    assert instances_app.client.post(runs_path(version)).json()["code"] == "already_run"


def test_a_patch_stores_a_name_and_refuses_a_blank_one(instances_app: CityInstancesApp) -> None:
    built(instances_app)
    instances_app.client.post(LIST, json={})
    path = "/api/v1/pricing-versions/geneva-3km.v1.A"

    renamed = instances_app.client.patch(path, json={"name": "  Cheaper  "})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Cheaper"
    assert instances_app.client.get(path).json()["name"] == "Cheaper"
    for blank in ("", "   "):
        assert instances_app.client.patch(path, json={"name": blank}).status_code == 422
    assert instances_app.client.get(path).json()["name"] == "Cheaper"


def test_kept_from_names_the_version_the_kept_values_came_from(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)
    first = instances_app.client.post(LIST, json={}).json()
    assert first["kept_from"] is None
    sealed_pricing_version(instances_app.rig, first["id"], RunState.SUCCEEDED)

    second = instances_app.client.post(LIST, json={}).json()
    copy = instances_app.client.post(LIST, json={"based_on": second["id"]}).json()

    assert second["kept_from"] == {"id": first["id"], "letter": "A"}
    assert copy["kept_from"] == {"id": second["id"], "letter": "B"}
    read = instances_app.client.get(f"/api/v1/pricing-versions/{second['id']}").json()
    assert read["kept_from"] == {"id": first["id"], "letter": "A"}


def test_last_duration_is_null_then_the_seconds_of_a_done_pricing_step(
    instances_app: CityInstancesApp,
) -> None:
    built(instances_app)
    instances_app.rig.pricing.read_durations_from(instances_app.rig.instances)
    version = instances_app.client.post(LIST, json={}).json()
    path = f"/api/v1/pricing-versions/{version['id']}"
    assert instances_app.client.get(path).json()["last_duration_s"] is None

    sealed_pricing_version(instances_app.rig, version["id"], RunState.SUCCEEDED)
    instances_app.rig.runs.update(
        _only_run_id(instances_app),
        lambda run: replace(
            run,
            steps=(
                replace(
                    run.steps[0],
                    state=StepState.DONE,
                    started_at=run.queued_at,
                    finished_at=run.queued_at + timedelta(seconds=42),
                ),
            ),
        ),
    )

    assert instances_app.client.get(path).json()["last_duration_s"] == 42
    assert instances_app.client.get(LIST).json()["items"][0]["last_duration_s"] == 42


def _only_run_id(app: CityInstancesApp) -> str:
    (run,) = [r for r in app.rig.runs.list_by_states(list(RunState)) if r.kind is RunKind.PRICING]
    return run.id
