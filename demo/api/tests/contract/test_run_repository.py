"""The RunRepository port: one suite, run against the fake and the PostgreSQL adapter.

The fake always runs. The PostgreSQL param carries the `integration` marker, so it is
deselected (not skipped) in `make check` and runs under `make test-integration`.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

import pytest
from sqlalchemy import Engine, insert

from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.runs import (
    Run,
    RunFailure,
    RunKind,
    RunNotFound,
    RunState,
    StepName,
    StepState,
    request_cancellation,
)
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.persistence.tables import workers
from tests.support.instances import SeedingRunRepository
from tests.support.runs import T0, later, make_run, step


class StoredRuns(RunRepository, RunQueue, Protocol):
    """What both adapters implement: the API's port and the worker's."""


def _no_worker_row(worker_id: str) -> None:
    """The fake keeps no workers table."""


@dataclass
class Store:
    repository: StoredRuns
    record_worker_heartbeat: Callable[[datetime], None]
    # PostgreSQL's runs.worker_id refers to workers.id: the row must exist before a claim.
    register_worker: Callable[[str], None] = _no_worker_row


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

    def register(worker_id: str) -> None:
        with migrated_database.begin() as connection:
            connection.execute(
                insert(workers).values(
                    id=worker_id, host="h", pid=1, started_at=T0, heartbeat_at=T0
                )
            )

    return Store(SeedingRunRepository(migrated_database), record, register)


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


def test_update_applies_the_change_to_the_stored_run_and_returns_it(store: Store) -> None:
    store.repository.add(make_run("r1", state=RunState.RUNNING, started_at=T0))

    updated = store.repository.update("r1", lambda run: request_cancellation(run, later(7)))

    assert updated.cancel_requested_at == later(7)
    assert store.repository.get("r1") == updated


def test_update_of_an_unknown_run_raises_run_not_found(store: Store) -> None:
    with pytest.raises(RunNotFound):
        store.repository.update("missing", lambda run: run)


def test_update_stores_nothing_when_the_change_raises(store: Store) -> None:
    run = make_run("r1", state=RunState.RUNNING, started_at=T0)
    store.repository.add(run)

    def refuse(_: Run) -> Run:
        raise ValueError("refused")

    with pytest.raises(ValueError, match="refused"):
        store.repository.update("r1", refuse)

    assert store.repository.get("r1") == run


def test_update_writes_the_steps_of_the_changed_run(store: Store) -> None:
    store.repository.add(make_run("r1", state=RunState.RUNNING))

    updated = store.repository.update(
        "r1",
        lambda run: replace(
            run,
            steps=(
                replace(run.steps[0], state=StepState.DONE, counts={"stops": 4}),
                *run.steps[1:],
            ),
        ),
    )

    assert store.repository.get("r1") == updated
    assert updated.steps[0].counts == {"stops": 4}


def test_claim_next_takes_the_oldest_queued_run_and_sets_it_running(store: Store) -> None:
    store.register_worker("w-1")
    store.repository.add(make_run("late", queued_at=later(30), subject_id="late.v1"))
    store.repository.add(make_run("early", queued_at=later(10), subject_id="early.v1"))

    claimed = store.repository.claim_next("w-1", later(40))

    assert claimed is not None
    assert claimed.id == "early"
    assert (claimed.state, claimed.worker_id) == (RunState.RUNNING, "w-1")
    assert (claimed.started_at, claimed.heartbeat_at) == (later(40), later(40))
    assert store.repository.get("early") == claimed
    late = store.repository.get("late")
    assert late is not None
    assert late.state is RunState.QUEUED


def test_claim_next_on_an_empty_queue_is_none(store: Store) -> None:
    store.register_worker("w-1")
    store.repository.add(make_run("a", state=RunState.RUNNING))

    assert store.repository.claim_next("w-1", later(1)) is None


def test_a_claimed_run_is_not_claimed_again(store: Store) -> None:
    store.register_worker("w-1")
    store.register_worker("w-2")
    store.repository.add(make_run("a"))

    assert store.repository.claim_next("w-1", later(1)) is not None
    assert store.repository.claim_next("w-2", later(2)) is None


def test_heartbeat_run_writes_only_the_heartbeat_of_a_running_run(store: Store) -> None:
    run = make_run("r1", state=RunState.RUNNING, started_at=T0, heartbeat_at=T0)
    store.repository.add(run)

    store.repository.heartbeat_run("r1", later(5))

    assert store.repository.get("r1") == replace(run, heartbeat_at=later(5))


def test_heartbeat_run_leaves_a_run_that_is_not_running_alone(store: Store) -> None:
    queued = make_run("q1", subject_id="q.v1")
    done = make_run("s1", state=RunState.SUCCEEDED, subject_id="s.v1", heartbeat_at=T0)
    store.repository.add(queued)
    store.repository.add(done)

    store.repository.heartbeat_run("q1", later(5))
    store.repository.heartbeat_run("s1", later(5))
    store.repository.heartbeat_run("missing", later(5))

    assert store.repository.get("q1") == queued
    assert store.repository.get("s1") == done


def test_a_cancellation_after_a_claim_keeps_the_claim(store: Store) -> None:
    store.register_worker("w-1")
    store.repository.add(make_run("r1"))
    claimed = store.repository.claim_next("w-1", later(3))
    assert claimed is not None

    store.repository.update("r1", lambda run: request_cancellation(run, later(4)))

    stored = store.repository.get("r1")
    assert stored is not None
    assert (stored.worker_id, stored.started_at, stored.heartbeat_at) == ("w-1", later(3), later(3))
    assert stored.cancel_requested_at == later(4)


def test_a_heartbeat_and_a_cancellation_request_both_survive(store: Store) -> None:
    store.repository.add(make_run("r1", state=RunState.RUNNING, started_at=T0, heartbeat_at=T0))

    store.repository.heartbeat_run("r1", later(5))
    store.repository.update("r1", lambda run: request_cancellation(run, later(6)))

    stored = store.repository.get("r1")
    assert stored is not None
    assert (stored.heartbeat_at, stored.cancel_requested_at) == (later(5), later(6))


def test_running_runs_lists_only_running_runs_in_queue_order(store: Store) -> None:
    store.repository.add(
        make_run("b", state=RunState.RUNNING, queued_at=later(2), subject_id="b.v1")
    )
    store.repository.add(
        make_run("a", state=RunState.RUNNING, queued_at=later(1), subject_id="a.v1")
    )
    store.repository.add(make_run("q", subject_id="q.v1"))

    assert [run.id for run in store.repository.running_runs()] == ["a", "b"]
