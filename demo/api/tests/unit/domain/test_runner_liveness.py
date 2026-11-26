from datetime import timedelta

import pytest

from pricing_demo.domain.runner_liveness import LIVENESS_WINDOW, Runner, is_alive, runner_of
from pricing_demo.domain.runs import RunState
from tests.support.runs import T0, later, make_run

SERVER_TIME = later(1000)


def test_the_window_is_thirty_seconds() -> None:
    assert timedelta(seconds=30) == LIVENESS_WINDOW


def test_a_heartbeat_of_exactly_thirty_seconds_is_alive() -> None:
    assert is_alive(SERVER_TIME - timedelta(seconds=30), SERVER_TIME)


def test_a_heartbeat_older_by_a_millisecond_is_not_alive() -> None:
    assert not is_alive(SERVER_TIME - timedelta(seconds=30, milliseconds=1), SERVER_TIME)


def test_a_current_heartbeat_is_alive() -> None:
    assert is_alive(SERVER_TIME, SERVER_TIME)


def test_no_heartbeat_is_not_alive() -> None:
    assert not is_alive(None, SERVER_TIME)


def test_a_running_run_reads_its_own_heartbeat_and_not_the_workers() -> None:
    run = make_run("r1", state=RunState.RUNNING, heartbeat_at=later(900))

    assert runner_of(run, SERVER_TIME, SERVER_TIME) == Runner(False, later(900))


def test_a_running_run_with_a_recent_heartbeat_is_alive() -> None:
    run = make_run("r1", state=RunState.RUNNING, heartbeat_at=later(990))

    assert runner_of(run, None, SERVER_TIME) == Runner(True, later(990))


def test_a_queued_run_reads_the_latest_heartbeat_of_a_worker() -> None:
    run = make_run("r1", heartbeat_at=None)

    assert runner_of(run, later(985), SERVER_TIME) == Runner(True, later(985))
    assert runner_of(run, later(900), SERVER_TIME) == Runner(False, later(900))


def test_a_queued_run_with_no_worker_has_no_heartbeat_and_is_not_alive() -> None:
    assert runner_of(make_run("r1"), None, SERVER_TIME) == Runner(False, None)


@pytest.mark.parametrize("state", [RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED])
def test_a_finished_run_is_never_alive_and_carries_its_last_heartbeat(state: RunState) -> None:
    run = make_run("r1", state=state, heartbeat_at=SERVER_TIME)

    assert runner_of(run, SERVER_TIME, SERVER_TIME) == Runner(False, SERVER_TIME)


def test_a_finished_run_without_heartbeat_carries_none() -> None:
    run = make_run("r1", state=RunState.CANCELLED, queued_at=T0)

    assert runner_of(run, SERVER_TIME, SERVER_TIME) == Runner(False, None)
