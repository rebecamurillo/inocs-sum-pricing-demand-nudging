from datetime import timedelta

import pytest
from sqlalchemy import Engine

from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from tests.support.instances import SeedingRunRepository
from tests.support.runs import T0, later, make_run, step

pytestmark = pytest.mark.integration

NOW = later(1000)


def running(run_id: str, heartbeat_age: float, attempt: int = 1) -> Run:
    return make_run(
        run_id,
        subject_id=f"{run_id}.v1",
        state=RunState.RUNNING,
        attempt=attempt,
        started_at=T0,
        worker_id="old-worker",
        child_pid=99,
        heartbeat_at=NOW - timedelta(seconds=heartbeat_age),
        steps=(
            step(
                1,
                StepName.AREA,
                StepState.DONE,
                started_at=T0,
                finished_at=later(5),
                counts={"n": 1},
            ),
            step(
                2,
                StepName.HUBS,
                StepState.RUNNING,
                started_at=later(5),
                progress_done=3,
                progress_total=8,
                reason="half way",
            ),
            step(3, StepName.ROUTES),
        ),
    )


@pytest.fixture
def repository(migrated_database: Engine) -> PostgresRunRepository:
    PostgresWorkerRegistry(migrated_database).register("old-worker", "h", 1, T0)
    return SeedingRunRepository(migrated_database)


def recover(repository: PostgresRunRepository) -> list[Run]:
    return RecoverInterruptedRuns(repository, FixedClock(NOW)).execute()


def stored(repository: PostgresRunRepository, run_id: str) -> Run:
    run = repository.get(run_id)
    assert run is not None
    return run


def test_a_run_stale_by_more_than_sixty_seconds_is_queued_again_as_attempt_two(
    repository: PostgresRunRepository,
) -> None:
    original = running("stale", 61)
    repository.add(original)

    assert [run.id for run in recover(repository)] == ["stale"]

    run = stored(repository, "stale")
    assert run.state is RunState.QUEUED
    assert run.attempt == 2
    assert run.queued_at == original.queued_at
    assert (run.worker_id, run.started_at, run.heartbeat_at, run.child_pid) == (None,) * 4
    assert run.steps[0] == original.steps[0]
    reset = run.steps[1]
    assert reset.state is StepState.PENDING
    assert (reset.started_at, reset.finished_at, reset.reason) == (None, None, None)
    assert (reset.progress_done, reset.progress_total) == (None, None)
    assert run.steps[2] == original.steps[2]


def test_a_run_stale_on_its_second_attempt_fails_as_interrupted(
    repository: PostgresRunRepository,
) -> None:
    original = running("twice", 61, attempt=2)
    repository.add(original)

    recover(repository)

    run = stored(repository, "twice")
    assert run.state is RunState.FAILED
    assert run.failure is not None
    assert run.failure.code == "interrupted"
    assert run.failure.reason == "The run was interrupted twice by a stop of the runner"
    assert run.failure.step == "hubs"
    assert run.finished_at == NOW
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.FAILED,
        StepState.PENDING,
    ]
    assert run.steps[0] == original.steps[0]


@pytest.mark.parametrize("age", [59, 60])
def test_a_run_that_is_not_stale_is_left_alone(
    repository: PostgresRunRepository, age: float
) -> None:
    original = running("fresh", age)
    repository.add(original)

    assert recover(repository) == []

    assert stored(repository, "fresh") == original
