from datetime import timedelta
from itertools import product

import pytest

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.runs import (
    STEP_NUMBERS,
    InvalidRunTransition,
    InvalidStepTransition,
    RunFailure,
    RunKind,
    RunState,
    StepName,
    StepState,
    cancel,
    cancel_queued,
    cancel_running,
    ensure_run_transition,
    fail,
    queue_positions,
    request_cancellation,
    requeue_after_interruption,
    start,
    succeed,
    transition_step,
)
from tests.support.runs import T0, later, make_run, step

ALLOWED_RUN_PAIRS = {
    (RunState.QUEUED, RunState.RUNNING),
    (RunState.QUEUED, RunState.CANCELLED),
    (RunState.RUNNING, RunState.SUCCEEDED),
    (RunState.RUNNING, RunState.FAILED),
    (RunState.RUNNING, RunState.CANCELLED),
}
FAILURE = RunFailure(step="routes", code="otp_unreachable", reason="The trip planner is down.")
NOW = later(60)


def move(state: RunState, to: RunState):  # type: ignore[no-untyped-def]
    run = make_run("r1", state=state)
    match to:
        case RunState.RUNNING:
            return start(run, NOW, "worker-1")
        case RunState.SUCCEEDED:
            return succeed(run, NOW)
        case RunState.FAILED:
            return fail(run, NOW, FAILURE)
        case RunState.CANCELLED:
            return cancel(run, NOW)
    return None


@pytest.mark.parametrize(("origin", "target"), list(product(RunState, RunState)))
def test_a_run_moves_only_along_the_allowed_transitions(origin: RunState, target: RunState) -> None:
    if target is RunState.QUEUED:
        # No general move leads back to queued: only the named restart operation does.
        with pytest.raises(InvalidRunTransition):
            ensure_run_transition(origin, target)
        return
    if (origin, target) in ALLOWED_RUN_PAIRS:
        assert move(origin, target).state is target
    else:
        with pytest.raises(InvalidRunTransition):
            move(origin, target)


def test_the_transition_errors_are_domain_errors() -> None:
    assert issubclass(InvalidRunTransition, DomainError)
    assert issubclass(InvalidStepTransition, DomainError)


def test_starting_records_the_worker_the_start_time_and_the_first_heartbeat() -> None:
    run = start(make_run("r1"), NOW, "worker-1")

    assert (run.started_at, run.heartbeat_at, run.worker_id) == (NOW, NOW, "worker-1")


def test_finishing_sets_the_finish_time() -> None:
    running = make_run("r1", state=RunState.RUNNING, started_at=T0)

    assert succeed(running, NOW).finished_at == NOW
    assert cancel(running, NOW).finished_at == NOW


def test_a_failed_run_keeps_its_failure() -> None:
    failed = fail(make_run("r1", state=RunState.RUNNING), NOW, FAILURE)

    assert failed.failure == FAILURE
    assert failed.finished_at == NOW


def test_the_restart_operation_moves_a_running_run_back_to_queued_for_another_attempt() -> None:
    running = make_run(
        "r1",
        state=RunState.RUNNING,
        attempt=1,
        started_at=T0,
        heartbeat_at=T0,
        worker_id="worker-1",
        child_pid=42,
        steps=(
            step(1, StepName.AREA, StepState.DONE),
            step(2, StepName.HUBS, StepState.RUNNING, started_at=T0),
        ),
    )

    queued = requeue_after_interruption(running)

    assert queued.state is RunState.QUEUED
    assert queued.attempt == 2
    assert (queued.started_at, queued.heartbeat_at, queued.worker_id, queued.child_pid) == (
        None,
        None,
        None,
        None,
    )
    assert [s.state for s in queued.steps] == [StepState.DONE, StepState.PENDING]
    assert queued.steps[1].started_at is None


@pytest.mark.parametrize("state", [s for s in RunState if s is not RunState.RUNNING])
def test_the_restart_operation_refuses_every_other_state(state: RunState) -> None:
    with pytest.raises(InvalidRunTransition):
        requeue_after_interruption(make_run("r1", state=state))


def test_cancelling_a_queued_run_cancels_its_pending_steps_and_sets_the_finish_time() -> None:
    queued = make_run(
        "r1",
        steps=(
            step(1, StepName.AREA, StepState.KEPT),
            step(2, StepName.HUBS),
            step(3, StepName.ROUTES),
        ),
    )

    cancelled = cancel_queued(queued, NOW)

    assert cancelled.state is RunState.CANCELLED
    assert cancelled.finished_at == NOW
    assert [s.state for s in cancelled.steps] == [
        StepState.KEPT,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]


@pytest.mark.parametrize("state", [s for s in RunState if s is not RunState.QUEUED])
def test_cancel_queued_refuses_a_run_that_is_not_queued(state: RunState) -> None:
    with pytest.raises(InvalidRunTransition):
        cancel_queued(make_run("r1", state=state), NOW)


def test_a_cancellation_request_is_recorded_once() -> None:
    running = make_run("r1", state=RunState.RUNNING)

    first = request_cancellation(running, NOW)
    second = request_cancellation(first, later(120))

    assert first.cancel_requested_at == NOW
    assert second == first
    assert second.state is RunState.RUNNING


@pytest.mark.parametrize("state", [s for s in RunState if s is not RunState.RUNNING])
def test_a_cancellation_is_requested_only_of_a_running_run(state: RunState) -> None:
    with pytest.raises(InvalidRunTransition):
        request_cancellation(make_run("r1", state=state), NOW)


TERMINAL_STEP_STATES = (StepState.DONE, StepState.KEPT, StepState.FAILED, StepState.CANCELLED)
ALLOWED_STEP_PAIRS = {
    (StepState.PENDING, StepState.RUNNING),
    (StepState.PENDING, StepState.KEPT),
    (StepState.PENDING, StepState.CANCELLED),
    (StepState.RUNNING, StepState.DONE),
    (StepState.RUNNING, StepState.FAILED),
    (StepState.RUNNING, StepState.CANCELLED),
}


@pytest.mark.parametrize(("origin", "target"), list(product(StepState, StepState)))
def test_a_step_moves_only_along_the_allowed_transitions(
    origin: StepState, target: StepState
) -> None:
    current = step(1, StepName.AREA, origin)

    if (origin, target) in ALLOWED_STEP_PAIRS:
        assert transition_step(current, target, NOW).state is target
    else:
        with pytest.raises(InvalidStepTransition):
            transition_step(current, target, NOW)


@pytest.mark.parametrize("origin", TERMINAL_STEP_STATES)
def test_a_step_never_leaves_a_final_state(origin: StepState) -> None:
    for target in StepState:
        with pytest.raises(InvalidStepTransition):
            transition_step(step(1, StepName.AREA, origin), target, NOW)


def test_a_step_records_when_it_starts_and_when_it_ends() -> None:
    started = transition_step(step(1, StepName.AREA), StepState.RUNNING, T0)
    ended = transition_step(started, StepState.DONE, NOW)

    assert (started.started_at, started.finished_at) == (T0, None)
    assert (ended.started_at, ended.finished_at) == (T0, NOW)


def test_the_step_numbers_follow_the_pipeline() -> None:
    assert {name.value: number for name, number in STEP_NUMBERS.items()} == {
        "area": 1,
        "hubs": 2,
        "routes": 3,
        "travellers_and_bikes": 4,
        "pricing_model": 5,
        "traveller_simulation": 5,
    }
    assert set(STEP_NUMBERS) == set(StepName)


def test_the_queue_position_is_the_rank_by_queue_time_among_queued_runs() -> None:
    first = make_run("b", queued_at=later(10))
    second = make_run("a", queued_at=later(20))
    third = make_run("c", queued_at=later(20))
    running = make_run("d", state=RunState.RUNNING, queued_at=T0)
    finished = make_run("e", state=RunState.SUCCEEDED, queued_at=T0 - timedelta(hours=1))

    assert queue_positions([third, running, second, first, finished]) == {"b": 1, "a": 2, "c": 3}


def test_the_kind_of_a_run_is_one_of_three() -> None:
    assert {kind.value for kind in RunKind} == {"build", "pricing", "simulation"}


def test_the_restart_operation_clears_the_reset_steps_times_progress_and_reason() -> None:
    running = make_run(
        "r1",
        state=RunState.RUNNING,
        started_at=T0,
        steps=(
            step(1, StepName.AREA, StepState.DONE, started_at=T0, finished_at=later(5)),
            step(
                2,
                StepName.HUBS,
                StepState.RUNNING,
                started_at=later(5),
                finished_at=later(6),
                progress_done=3,
                progress_total=9,
                reason="half way",
            ),
        ),
    )

    queued = requeue_after_interruption(running)

    assert queued.steps[0] == running.steps[0]
    reset = queued.steps[1]
    assert reset.state is StepState.PENDING
    assert (reset.started_at, reset.finished_at) == (None, None)
    assert (reset.progress_done, reset.progress_total, reset.reason) == (None, None, None)


def test_cancelling_a_running_run_cancels_the_running_and_pending_steps_and_keeps_done_ones() -> (
    None
):
    running = make_run(
        "r1",
        state=RunState.RUNNING,
        started_at=T0,
        steps=(
            step(1, StepName.AREA, StepState.DONE, started_at=T0, finished_at=later(5)),
            step(2, StepName.HUBS, StepState.KEPT),
            step(3, StepName.ROUTES, StepState.RUNNING, started_at=later(5)),
            step(4, StepName.TRAVELLERS_AND_BIKES),
        ),
    )

    cancelled = cancel_running(running, NOW)

    assert cancelled.state is RunState.CANCELLED
    assert cancelled.finished_at == NOW
    assert [s.state for s in cancelled.steps] == [
        StepState.DONE,
        StepState.KEPT,
        StepState.CANCELLED,
        StepState.CANCELLED,
    ]
    assert cancelled.steps[0] == running.steps[0]
    assert cancelled.steps[2].finished_at == NOW


@pytest.mark.parametrize("state", [s for s in RunState if s is not RunState.RUNNING])
def test_cancelling_a_run_that_is_not_running_is_refused_by_cancel_running(
    state: RunState,
) -> None:
    with pytest.raises(InvalidRunTransition):
        cancel_running(make_run("r1", state=state), NOW)
