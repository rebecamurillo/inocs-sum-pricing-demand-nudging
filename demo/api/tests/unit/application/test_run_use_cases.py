import pytest

from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.domain.runs import RunAlreadyFinished, RunNotFound, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from tests.support.runs import T0, later, make_run, step

SERVER_TIME = later(100)


@pytest.fixture
def repository() -> InMemoryRunRepository:
    return InMemoryRunRepository()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(SERVER_TIME)


def test_listing_filters_by_state_and_orders_by_queue_time(
    repository: InMemoryRunRepository, clock: FixedClock
) -> None:
    repository.add(make_run("late", queued_at=later(20)))
    repository.add(make_run("early", queued_at=later(10), subject_id="geneva-5km.v1"))
    repository.add(make_run("running", state=RunState.RUNNING, subject_id="x.v1"))
    repository.add(make_run("done", state=RunState.SUCCEEDED, subject_id="y.v1"))

    views = ListRuns(repository, clock).execute([RunState.QUEUED])

    assert [(v.run.id, v.queue_position) for v in views] == [("early", 1), ("late", 2)]
    assert {v.server_time for v in views} == {SERVER_TIME}


def test_a_listing_without_queued_runs_has_no_queue_position(
    repository: InMemoryRunRepository, clock: FixedClock
) -> None:
    repository.add(make_run("a"))
    repository.add(make_run("b", state=RunState.RUNNING, subject_id="x.v1", heartbeat_at=later(95)))

    views = ListRuns(repository, clock).execute([RunState.RUNNING])

    assert [(v.run.id, v.queue_position, v.runner.alive) for v in views] == [("b", None, True)]


def test_a_queued_run_reads_the_workers_heartbeat(
    repository: InMemoryRunRepository, clock: FixedClock
) -> None:
    repository.add(make_run("a"))
    repository.record_worker_heartbeat(later(80))

    view = GetRun(repository, clock).execute("a")

    assert (view.queue_position, view.runner.alive, view.runner.last_heartbeat_at) == (
        1,
        True,
        later(80),
    )


def test_an_unknown_run_is_not_found(repository: InMemoryRunRepository, clock: FixedClock) -> None:
    with pytest.raises(RunNotFound):
        GetRun(repository, clock).execute("nope")
    with pytest.raises(RunNotFound):
        GetRunLog(repository).execute("nope")
    with pytest.raises(RunNotFound):
        CancelRun(repository, clock).execute("nope")


def test_the_log_joins_the_excerpts_in_step_order(repository: InMemoryRunRepository) -> None:
    repository.add(
        make_run(
            "a",
            steps=(
                step(2, StepName.HUBS, log_excerpt="second"),
                step(1, StepName.AREA, log_excerpt="first"),
                step(3, StepName.ROUTES),
            ),
        )
    )

    assert GetRunLog(repository).execute("a") == "first\nsecond"


def test_cancelling_a_queued_run_ends_it_at_once(
    repository: InMemoryRunRepository, clock: FixedClock
) -> None:
    repository.add(make_run("a"))

    result = CancelRun(repository, clock).execute("a")

    stored = repository.get("a")
    assert stored is not None
    assert result.cancelled_at_once
    assert result.view.run == stored
    assert (stored.state, stored.finished_at) == (RunState.CANCELLED, SERVER_TIME)
    assert {s.state for s in stored.steps} == {StepState.CANCELLED}


def test_cancelling_a_running_run_records_the_request(
    repository: InMemoryRunRepository, clock: FixedClock
) -> None:
    repository.add(make_run("a", state=RunState.RUNNING, started_at=T0))

    first = CancelRun(repository, clock).execute("a")
    clock.advance(later(50) - T0)
    second = CancelRun(repository, clock).execute("a")

    assert not first.cancelled_at_once
    assert first.view.run.state is RunState.RUNNING
    assert second.view.run.cancel_requested_at == SERVER_TIME


@pytest.mark.parametrize("state", [RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED])
def test_a_finished_run_cannot_be_cancelled(
    repository: InMemoryRunRepository, clock: FixedClock, state: RunState
) -> None:
    repository.add(make_run("a", state=state))

    with pytest.raises(RunAlreadyFinished):
        CancelRun(repository, clock).execute("a")
