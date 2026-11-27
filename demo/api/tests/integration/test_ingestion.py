"""The ingestion on PostgreSQL: one transaction, a rerun that only ingests, and the rows of
the failed queries."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.domain.read_model import HubRow, StationRow
from pricing_demo.domain.runs import RunState, StepName, StepState
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from tests.integration.test_builds import READ_MODEL_TABLES, Rig, rig  # noqa: F401

pytestmark = pytest.mark.integration

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


def test_a_batch_whose_last_table_breaks_a_key_leaves_nothing_behind(rig: Rig) -> None:  # noqa: F811
    queued = rig.build.execute(rig.draft())
    rig.process.execute()
    key = rig.run_of(queued.id).steps[0].input_key or ""
    with rig.engine.begin() as connection:
        for table in READ_MODEL_TABLES:
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(text("UPDATE artifacts SET counts = NULL, ingested_at = NULL"))
    model = PostgresReadModel(rig.engine)
    hub = HubRow("H1", "label", 1.0, 2.0, None, (), (), ())
    # The same hub twice breaks the primary key of `hubs`, which is written after `stations`.
    broken = IngestionBatch(
        key,
        StepName.AREA,
        {"stops": 1},
        stations=[StationRow("s1", "pt", "Stop", 46.2, 6.1)],
        hubs=[hub, hub],
    )

    with pytest.raises(IntegrityError):
        model.ingest(broken)

    assert {table: rig.rows(table) for table in READ_MODEL_TABLES} == {
        table: [] for table in READ_MODEL_TABLES
    }
    assert model.is_ingested(key) is False
    assert model.counts_of([key]) == {}


def test_ingesting_the_same_key_twice_does_not_duplicate(rig: Rig) -> None:  # noqa: F811
    queued = rig.build.execute(rig.draft())
    rig.process.execute()
    key = rig.run_of(queued.id).steps[0].input_key or ""
    model = PostgresReadModel(rig.engine)
    stations = model.stations(key)
    batch = IngestionBatch(
        key, StepName.AREA, {"stops": 30, "bike_stations": 12}, stations=stations
    )

    model.ingest(batch)
    model.ingest(batch)

    assert len(rig.rows("stations")) == 42
    assert model.stations(key) == stations


def test_a_failed_ingestion_fails_the_step_and_the_next_build_only_ingests(rig: Rig) -> None:  # noqa: F811
    version = rig.draft()
    rig.ingestion.failures = 1
    failed = rig.build.execute(version)

    rig.process.execute()

    run = rig.run_of(failed.id)
    assert run.state is RunState.FAILED
    assert (run.failure.step, run.failure.code) == ("area", "stage_error")  # type: ignore[union-attr]
    assert run.steps[0].state is StepState.FAILED
    key = run.steps[0].input_key or ""
    artifact = rig.artifacts.get(key)
    assert artifact is not None
    assert (rig.data_dir / artifact.path / "stations.json").is_file()
    assert rig.rows("stations") == []
    assert rig.artifacts.links_of(version) == {}
    assert PostgresReadModel(rig.engine).is_ingested(key) is False

    rig.preparation.steps.clear()
    resumed = rig.build.execute(version)
    rig.process.execute()

    steps = rig.run_of(resumed.id).steps
    assert rig.run_of(resumed.id).state is RunState.SUCCEEDED
    assert [item.state for item in steps] == [StepState.DONE] * 4
    assert rig.preparation.steps == [
        StepName.HUBS,
        StepName.ROUTES,
        StepName.TRAVELLERS_AND_BIKES,
    ]
    assert steps[0].counts == {"stops": 30, "bike_stations": 12}
    assert len(rig.rows("stations")) == 42
    assert len(rig.rows("artifacts")) == 4


def test_the_failed_queries_are_rows_with_run_step_and_period(rig: Rig) -> None:  # noqa: F811
    version = rig.draft()
    rig.settings.set_pricing_model({"route_failures": FAILURES})
    queued = rig.build.execute(version)

    rig.process.execute()

    with rig.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT f.run_id, s.step, f.instance_period_id, f.origin_hub, f.query, f.kind,"
                " f.message, f.attempts FROM route_failures f JOIN run_steps s"
                " ON s.id = f.run_step_id ORDER BY f.origin_hub, f.destination_hub"
            )
        ).all()
    period = f"{version}.mon-08"
    assert [tuple(row) for row in rows] == [
        (queued.id, "routes", period, "H1", "pt_bike", "technical", "timeout", 4),
        (queued.id, "routes", period, "H1", "car", "no_route", "no car route", 1),
    ]
    run = rig.run_of(queued.id)
    assert run.failure_pct == pytest.approx(100 * 2 / 48)
    assert run.steps[2].counts["queries_failed"] == 2
    assert len(rig.rows("hub_pairs")) == 23


def test_deleting_a_run_deletes_its_failed_queries(rig: Rig) -> None:  # noqa: F811
    rig.settings.set_pricing_model({"route_failures": FAILURES})
    queued = rig.build.execute(rig.draft())
    rig.process.execute()
    assert len(rig.rows("route_failures")) == 2

    with rig.engine.begin() as connection:
        connection.execute(text("DELETE FROM run_steps WHERE run_id = :run"), {"run": queued.id})
        connection.execute(text("DELETE FROM runs WHERE id = :run"), {"run": queued.id})

    assert rig.rows("route_failures") == []


def test_a_kept_routes_step_keeps_the_failures_of_the_run_that_produced_them(
    rig: Rig,  # noqa: F811
) -> None:
    first = rig.draft()
    rig.settings.set_pricing_model({"route_failures": FAILURES})
    produced = rig.build.execute(first)
    rig.process.execute()
    second = rig.draft(2, first)

    queued = rig.build.execute(second)
    rig.process.execute()

    run = rig.run_of(queued.id)
    assert run.steps[2].state is StepState.KEPT
    assert run.failure_pct == pytest.approx(100 * 2 / 48)
    routes_key = rig.artifacts.links_of(second)[StepName.ROUTES]
    artifact = rig.artifacts.get(routes_key)
    assert artifact is not None
    assert artifact.run_id == produced.id
