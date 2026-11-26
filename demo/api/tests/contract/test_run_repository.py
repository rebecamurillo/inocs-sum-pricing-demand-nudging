"""The RunRepository port: one suite, run against the fake and the PostgreSQL adapter.

The fake always runs. The PostgreSQL param carries the `integration` marker, so it is
deselected (not skipped) in `make check` and runs under `make test-integration`.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime

import pytest
from sqlalchemy import Engine, insert

from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.runs import (
    Run,
    RunFailure,
    RunKind,
    RunState,
    StepName,
    StepState,
)
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.tables import workers
from tests.support.runs import T0, later, make_run, step


@dataclass
class Store:
    repository: RunRepository
    record_worker_heartbeat: Callable[[datetime], None]


def fake_store() -> Iterator[Store]:
    repository = InMemoryRunRepository()
    yield Store(repository, repository.record_worker_heartbeat)


@pytest.fixture
def postgres_store(migrated_database: Engine) -> Store:
    counter = 0

    def record(at: datetime) -> None:
        nonlocal counter
        counter += 1
        with migrated_database.begin() as connection:
            connection.execute(
                insert(workers).values(
                    id=f"worker-{counter}", host="h", pid=counter, started_at=T0, heartbeat_at=at
                )
            )

    return Store(PostgresRunRepository(migrated_database), record)


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Iterator[Store]:
    if request.param == "fake":
        yield from fake_store()
    else:
        yield request.getfixturevalue("postgres_store")


def test_a_run_is_read_back_with_its_steps(store: Store) -> None:
    run = make_run(
        "r1",
        steps=(
            step(1, StepName.AREA, StepState.DONE, counts={"hubs": 3}, progress_done=1),
            step(2, StepName.HUBS, log_excerpt="hubs done", period="geneva-3km.v1.mon-08"),
        ),
    )

    store.repository.add(run)

    assert store.repository.get("r1") == run


def test_every_kind_of_run_is_read_back(store: Store) -> None:
    pricing = make_run("p1", kind=RunKind.PRICING, state=RunState.RUNNING, worker_id=None)
    simulation = make_run("s1", kind=RunKind.SIMULATION, subject_id="geneva-3km.v1.B")

    store.repository.add(pricing)
    store.repository.add(simulation)

    assert store.repository.get("p1") == pricing
    assert store.repository.get("s1") == simulation


def test_an_unknown_id_is_none(store: Store) -> None:
    assert store.repository.get("missing") is None


def test_runs_are_listed_by_state_in_queue_order(store: Store) -> None:
    store.repository.add(make_run("c", queued_at=later(30), subject_id="c.v1"))
    store.repository.add(make_run("a", queued_at=later(10), subject_id="a.v1"))
    store.repository.add(
        make_run("b", state=RunState.RUNNING, queued_at=later(20), subject_id="b.v1")
    )
    store.repository.add(
        make_run("d", state=RunState.SUCCEEDED, queued_at=later(5), subject_id="d.v1")
    )

    listed = store.repository.list_by_states([RunState.QUEUED, RunState.RUNNING])

    assert [run.id for run in listed] == ["a", "b", "c"]
    assert [run.id for run in store.repository.list_by_states([RunState.SUCCEEDED])] == ["d"]
    assert store.repository.list_by_states([]) == []
    assert all(run.steps for run in listed)


def test_the_latest_worker_heartbeat_is_the_most_recent(store: Store) -> None:
    assert store.repository.latest_worker_heartbeat() is None

    store.record_worker_heartbeat(later(5))
    store.record_worker_heartbeat(later(50))
    store.record_worker_heartbeat(later(20))

    assert store.repository.latest_worker_heartbeat() == later(50)


def test_a_cancelled_queued_run_is_saved_with_its_steps(store: Store) -> None:
    run = make_run("r1")
    store.repository.add(run)
    cancelled = replace(
        run,
        state=RunState.CANCELLED,
        finished_at=later(9),
        steps=tuple(replace(item, state=StepState.CANCELLED) for item in run.steps),
    )

    store.repository.save(cancelled)

    assert store.repository.get("r1") == cancelled


def test_a_cancellation_request_is_saved(store: Store) -> None:
    run = make_run("r1", state=RunState.RUNNING, started_at=T0)
    store.repository.add(run)
    requested: Run = replace(run, cancel_requested_at=later(7))

    store.repository.save(requested)

    stored = store.repository.get("r1")
    assert stored is not None
    assert stored.cancel_requested_at == later(7)


def test_a_failure_is_saved_and_read_back(store: Store) -> None:
    run = make_run("r1", state=RunState.RUNNING)
    store.repository.add(run)
    failed = replace(
        run,
        state=RunState.FAILED,
        failure=RunFailure("routes", "otp_unreachable", "The trip planner is down."),
        failure_pct=12.5,
    )

    store.repository.save(failed)

    assert store.repository.get("r1") == failed


def test_saving_an_unknown_run_raises(store: Store) -> None:
    with pytest.raises(KeyError):
        store.repository.save(make_run("missing"))
