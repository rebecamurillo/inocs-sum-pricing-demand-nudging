from datetime import timedelta

import pytest

from pricing_demo.domain.run_recovery import (
    INTERRUPTED_CODE,
    INTERRUPTED_REASON,
    MAX_ATTEMPTS,
    STALE_AFTER,
    is_stale,
    recover_interrupted,
)
from pricing_demo.domain.runs import RunState, StepName, StepState
from tests.support.runs import T0, later, make_run, step

NOW = later(1000)


def running_run(heartbeat_age: float | None, attempt: int = 1):  # type: ignore[no-untyped-def]
    return make_run(
        "r1",
        state=RunState.RUNNING,
        attempt=attempt,
        started_at=T0,
        worker_id="w-1",
        child_pid=77,
        heartbeat_at=None if heartbeat_age is None else NOW - timedelta(seconds=heartbeat_age),
        steps=(
            step(1, StepName.AREA, StepState.DONE, started_at=T0, finished_at=later(5)),
            step(2, StepName.HUBS, StepState.RUNNING, started_at=later(5), progress_done=2),
            step(3, StepName.ROUTES),
        ),
    )


def test_the_rule_constants_are_the_documented_ones() -> None:
    assert timedelta(seconds=60) == STALE_AFTER
    assert MAX_ATTEMPTS == 2
    assert INTERRUPTED_CODE == "interrupted"


@pytest.mark.parametrize("age", [0, 59, 60])
def test_a_heartbeat_up_to_sixty_seconds_old_is_not_stale(age: float) -> None:
    assert not is_stale(running_run(age), NOW)


@pytest.mark.parametrize("age", [60.001, 61, 3600])
def test_a_heartbeat_more_than_sixty_seconds_old_is_stale(age: float) -> None:
    assert is_stale(running_run(age), NOW)


def test_a_running_run_without_a_heartbeat_is_stale() -> None:
    assert is_stale(running_run(None), NOW)


@pytest.mark.parametrize("state", [s for s in RunState if s is not RunState.RUNNING])
def test_a_run_that_is_not_running_is_never_stale(state: RunState) -> None:
    assert not is_stale(make_run("r1", state=state, heartbeat_at=later(-1000)), NOW)


def test_a_first_interruption_queues_the_run_again_for_a_second_attempt() -> None:
    run = running_run(61)

    queued = recover_interrupted(run, NOW)

    assert queued.state is RunState.QUEUED
    assert queued.attempt == 2
    assert queued.queued_at == run.queued_at
    assert (queued.worker_id, queued.started_at, queued.heartbeat_at, queued.child_pid) == (
        None,
        None,
        None,
        None,
    )
    assert queued.steps[0] == run.steps[0]
    reset = queued.steps[1]
    assert reset.state is StepState.PENDING
    assert (reset.started_at, reset.finished_at, reset.progress_done, reset.reason) == (
        None,
        None,
        None,
        None,
    )
    assert queued.steps[2] == run.steps[2]


def test_a_second_interruption_fails_the_run_with_the_interrupted_code() -> None:
    run = running_run(61, attempt=2)

    failed = recover_interrupted(run, NOW)

    assert failed.state is RunState.FAILED
    assert failed.finished_at == NOW
    assert failed.failure is not None
    assert failed.failure.code == INTERRUPTED_CODE
    assert failed.failure.reason == "The run was interrupted twice by a stop of the runner"
    assert failed.failure.reason == INTERRUPTED_REASON
    assert failed.failure.step == "hubs"
    assert [s.state for s in failed.steps] == [StepState.DONE, StepState.FAILED, StepState.PENDING]
    assert failed.steps[0] == run.steps[0]
    assert failed.steps[1].reason == INTERRUPTED_REASON
    assert failed.steps[1].finished_at == NOW


def test_a_second_interruption_between_steps_has_no_failed_step() -> None:
    run = make_run(
        "r1",
        state=RunState.RUNNING,
        attempt=2,
        steps=(step(1, StepName.AREA, StepState.DONE), step(2, StepName.HUBS)),
    )

    failed = recover_interrupted(run, NOW)

    assert failed.failure is not None
    assert failed.failure.step is None
    assert [s.state for s in failed.steps] == [StepState.DONE, StepState.PENDING]
