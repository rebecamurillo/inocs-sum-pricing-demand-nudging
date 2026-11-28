from typing import Any

import pytest

from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.runs import (
    RunFailure,
    RunKind,
    RunState,
    StepName,
    StepState,
)
from tests.support.runs import T0, later, make_run, step
from tests.unit.interface.http.conftest import RunsApp

SERVER_TIME = "2026-11-26T10:01:40Z"


def iso(seconds: float) -> str:
    return later(seconds).isoformat().replace("+00:00", "Z")


def test_a_queued_build_run_has_the_documented_shape(runs_app: RunsApp) -> None:
    runs_app.repository.add(
        make_run(
            "r1",
            queued_at=later(10),
            steps=(
                step(1, StepName.AREA, StepState.KEPT, reason="Reused from geneva-3km.v0."),
                step(
                    2,
                    StepName.HUBS,
                    StepState.RUNNING,
                    started_at=later(20),
                    counts={"hubs": 3},
                    progress_done=1,
                    progress_total=4,
                ),
                step(3, StepName.ROUTES, period="geneva-3km.v1.mon-08"),
            ),
        )
    )
    runs_app.repository.record_worker_heartbeat(later(90))

    response = runs_app.client.get("/api/v1/runs/r1")

    assert response.status_code == 200
    assert response.json() == {
        "id": "r1",
        "kind": "build",
        "subject": {"type": "instance_version", "id": "geneva-3km.v1"},
        "state": "queued",
        "attempt": 1,
        "queued_at": iso(10),
        "started_at": None,
        "finished_at": None,
        "server_time": SERVER_TIME,
        "queue_position": 1,
        "runner": {"alive": True, "last_heartbeat_at": iso(90)},
        "steps": [
            {
                "step": "area",
                "number": 1,
                "period": None,
                "state": "kept",
                "started_at": None,
                "finished_at": None,
                "counts": {},
                "progress": None,
                "last_duration_s": None,
                "reason": "Reused from geneva-3km.v0.",
            },
            {
                "step": "hubs",
                "number": 2,
                "period": None,
                "state": "running",
                "started_at": iso(20),
                "finished_at": None,
                "counts": {"hubs": 3},
                "progress": {"done": 1, "total": 4},
                "last_duration_s": None,
                "reason": None,
            },
            {
                "step": "routes",
                "number": 3,
                "period": "geneva-3km.v1.mon-08",
                "state": "pending",
                "started_at": None,
                "finished_at": None,
                "counts": {},
                "progress": None,
                "last_duration_s": None,
                "reason": None,
            },
        ],
        "failure": None,
        "failure_pct": None,
    }


def test_a_failed_pricing_run_carries_its_failure_and_a_dead_runner(runs_app: RunsApp) -> None:
    runs_app.repository.add(
        make_run(
            "p1",
            kind=RunKind.PRICING,
            state=RunState.FAILED,
            attempt=2,
            started_at=later(5),
            finished_at=later(40),
            heartbeat_at=later(39),
            failure=RunFailure("pricing_model", "solver_failed", "The solver stopped."),
            failure_pct=3.0,
        )
    )

    body: dict[str, Any] = runs_app.client.get("/api/v1/runs/p1").json()

    assert body["subject"] == {"type": "pricing_version", "id": "geneva-3km.v1.A"}
    assert body["steps"][0]["step"] == "pricing_model"
    assert body["steps"][0]["number"] == 5
    assert body["failure"] == {
        "step": "pricing_model",
        "code": "solver_failed",
        "reason": "The solver stopped.",
    }
    assert body["runner"] == {"alive": False, "last_heartbeat_at": iso(39)}
    assert body["queue_position"] is None
    assert body["attempt"] == 2
    # failure_pct is reported on a build only; it is null on every other kind.
    assert body["failure_pct"] is None


def test_a_build_reports_its_failure_percentage(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("b1", state=RunState.SUCCEEDED, failure_pct=2.5))

    assert runs_app.client.get("/api/v1/runs/b1").json()["failure_pct"] == 2.5


def test_the_list_is_filtered_by_state_and_ordered_by_queue_time(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("late", queued_at=later(30), subject_id="c.v1"))
    runs_app.repository.add(make_run("early", queued_at=later(10), subject_id="a.v1"))
    runs_app.repository.add(
        make_run("running", state=RunState.RUNNING, queued_at=later(20), subject_id="b.v1")
    )
    runs_app.repository.add(
        make_run("done", state=RunState.SUCCEEDED, queued_at=later(1), subject_id="d.v1")
    )

    response = runs_app.client.get("/api/v1/runs", params={"state": "queued,running"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["early", "running", "late"]
    assert [item["queue_position"] for item in response.json()["items"]] == [1, None, 2]
    assert set(response.json()) == {"items"}


def test_the_list_without_a_filter_holds_every_run(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("a"))
    runs_app.repository.add(make_run("b", state=RunState.CANCELLED))

    assert [i["id"] for i in runs_app.client.get("/api/v1/runs").json()["items"]] == ["a", "b"]


def test_an_unknown_state_is_a_validation_problem(runs_app: RunsApp) -> None:
    response = runs_app.client.get("/api/v1/runs", params={"state": "queued,paused"})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_failed"
    assert [error["field"] for error in response.json()["errors"]] == ["state"]


def test_the_log_is_plain_text_in_step_order(runs_app: RunsApp) -> None:
    runs_app.repository.add(
        make_run(
            "r1",
            steps=(
                step(2, StepName.HUBS, log_excerpt="hubs: 3 found"),
                step(1, StepName.AREA, log_excerpt="area: loaded"),
            ),
        )
    )

    response = runs_app.client.get("/api/v1/runs/r1/log")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "area: loaded\nhubs: 3 found"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/runs/nope"),
        ("GET", "/api/v1/runs/nope/log"),
        ("PUT", "/api/v1/runs/nope/cancellation"),
    ],
)
def test_an_unknown_run_is_a_404_problem(runs_app: RunsApp, method: str, path: str) -> None:
    response = runs_app.client.request(method, path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "run_not_found"


def test_cancellation_queued_answers_200_with_the_cancelled_run(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("r1"))

    response = runs_app.client.put("/api/v1/runs/r1/cancellation")

    assert response.status_code == 200
    body = response.json()
    assert (body["state"], body["finished_at"]) == ("cancelled", SERVER_TIME)
    assert {item["state"] for item in body["steps"]} == {"cancelled"}
    stored = runs_app.repository.get("r1")
    assert stored is not None
    assert stored.state is RunState.CANCELLED


def test_cancellation_running_answers_202_and_records_the_request(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("r1", state=RunState.RUNNING, started_at=T0))

    response = runs_app.client.put("/api/v1/runs/r1/cancellation")

    assert response.status_code == 202
    assert response.headers["location"] == "/api/v1/runs/r1"
    assert response.json()["state"] == "running"
    stored = runs_app.repository.get("r1")
    assert stored is not None
    assert stored.cancel_requested_at == later(100)


def test_cancellation_running_twice_keeps_the_first_request(runs_app: RunsApp) -> None:
    runs_app.repository.add(make_run("r1", state=RunState.RUNNING, started_at=T0))
    runs_app.client.put("/api/v1/runs/r1/cancellation")
    runs_app.clock.set(later(500))

    response = runs_app.client.put("/api/v1/runs/r1/cancellation")

    assert response.status_code == 202
    stored = runs_app.repository.get("r1")
    assert stored is not None
    assert stored.cancel_requested_at == later(100)


@pytest.mark.parametrize("state", [RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED])
def test_cancellation_finished_answers_409_run_finished(runs_app: RunsApp, state: RunState) -> None:
    runs_app.repository.add(make_run("r1", state=state))

    response = runs_app.client.put("/api/v1/runs/r1/cancellation")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "run_finished"


def test_the_contract_declares_the_four_routes_and_the_text_log(runs_app: RunsApp) -> None:
    paths = runs_app.client.get("/api/openapi.json").json()["paths"]

    assert set(paths["/api/v1/runs"]) == {"get"}
    assert set(paths["/api/v1/runs/{run_id}/cancellation"]) == {"put"}
    log = paths["/api/v1/runs/{run_id}/log"]["get"]["responses"]
    assert "text/plain" in log["200"]["content"]
    # Its errors are problem documents like every other route's, not text.
    assert set(log["404"]["content"]) == {"application/problem+json"}
    assert set(log["500"]["content"]) == {"application/problem+json"}
    assert (
        "Location"
        in paths["/api/v1/runs/{run_id}/cancellation"]["put"]["responses"]["202"]["headers"]
    )


def _a_pricing_run(runs_app: RunsApp, run_id: str, queued_at: float, seconds: float | None) -> str:
    """A pricing run of a built version; with `seconds` its pricing model step is done."""
    runs_app.rig.add_draft()
    version = runs_app.rig.pricing.create_draft(
        "geneva-3km.v1",
        None,
        new_draft_goals(None),
        "geneva-3km.v1.mon-08",
        None,
        T0,
    )
    steps = (
        (
            step(
                1,
                StepName.PRICING_MODEL,
                StepState.DONE,
                started_at=later(queued_at),
                finished_at=later(queued_at + seconds),
            ),
        )
        if seconds is not None
        else None
    )
    runs_app.repository.add(
        make_run(
            run_id,
            kind=RunKind.PRICING,
            subject_id=version.id,
            state=RunState.SUCCEEDED if seconds is not None else RunState.QUEUED,
            queued_at=later(queued_at),
            steps=steps,
        )
    )
    return version.id


def test_a_pricing_runs_model_step_carries_the_last_duration_on_its_instance(
    runs_app: RunsApp,
) -> None:
    _a_pricing_run(runs_app, "done", 10, 75)

    # The same version's run again: nothing but the earlier done step is known.
    runs_app.repository.add(
        make_run(
            "again",
            kind=RunKind.PRICING,
            subject_id="geneva-3km.v1.A",
            queued_at=later(500),
        )
    )

    body = runs_app.client.get("/api/v1/runs/again").json()

    assert [(item["step"], item["last_duration_s"]) for item in body["steps"]] == [
        ("pricing_model", 75)
    ]
    listed = runs_app.client.get("/api/v1/runs?state=queued").json()["items"]
    assert listed[0]["steps"][0]["last_duration_s"] == 75


def test_a_pricing_runs_model_step_has_no_duration_before_any_earlier_run(
    runs_app: RunsApp,
) -> None:
    _a_pricing_run(runs_app, "first", 10, None)

    body = runs_app.client.get("/api/v1/runs/first").json()

    assert body["steps"][0]["last_duration_s"] is None


def test_build_steps_keep_a_null_last_duration_next_to_a_pricing_runs_duration(
    runs_app: RunsApp,
) -> None:
    _a_pricing_run(runs_app, "done", 10, 75)
    runs_app.repository.add(make_run("build-2", queued_at=later(600)))

    body = runs_app.client.get("/api/v1/runs/build-2").json()

    assert {item["last_duration_s"] for item in body["steps"]} == {None}
