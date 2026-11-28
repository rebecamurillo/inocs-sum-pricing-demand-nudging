"""The RouteFailures port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from tests.support.runs import T0, make_run, step

PERIOD = "geneva-3km.v1.mon-08"


@dataclass
class Store:
    failures: RouteFailures
    # PostgreSQL keeps a foreign key on the run, its step and its period.
    add_run: Callable[[str], None]


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Store:
    if request.param == "fake":
        return Store(InMemoryRouteFailures(), lambda run_id: None)
    from pricing_demo.infrastructure.persistence.route_failures import PostgresRouteFailures
    from tests.support.instances import SeedingRunRepository

    engine: Engine = request.getfixturevalue("migrated_database")
    repository = SeedingRunRepository(engine)

    def add_run(run_id: str) -> None:
        repository.add(
            make_run(
                run_id,
                subject_id=f"geneva-3km.v{int(run_id[-1]) + 1}",
                steps=(step(1, StepName.AREA), step(3, StepName.ROUTES, period=PERIOD)),
            )
        )

    return Store(PostgresRouteFailures(engine), add_run)


def failure(origin: str, destination: str, query: str = "pt_bike") -> RouteFailure:
    return RouteFailure(origin, destination, query, "technical", "timeout", 4)  # type: ignore[arg-type]


def test_a_failure_is_read_back_with_its_run_and_step(store: Store) -> None:
    store.add_run("run-1")

    store.failures.add("run-1", 3, PERIOD, failure("H1", "H2"), T0)

    assert store.failures.of_run("run-1") == [(failure("H1", "H2"), PERIOD)]
    assert store.failures.of_step("run-1", 3) == [failure("H1", "H2")]
    assert store.failures.of_step("run-1", 1) == []


def test_the_failures_are_ordered_by_origin_destination_and_query(store: Store) -> None:
    store.add_run("run-1")
    for item in (failure("H2", "H1"), failure("H1", "H6", "car"), failure("H1", "H6")):
        store.failures.add("run-1", 3, PERIOD, item, T0)

    assert [item for item, _ in store.failures.of_run("run-1")] == [
        failure("H1", "H6", "car"),
        failure("H1", "H6"),
        failure("H2", "H1"),
    ]


def test_the_failures_of_one_run_are_not_those_of_another(store: Store) -> None:
    store.add_run("run-1")
    store.add_run("run-2")
    store.failures.add("run-1", 3, PERIOD, failure("H1", "H2"), T0)

    assert store.failures.of_run("run-2") == []


def test_clearing_a_step_removes_its_failures_only(store: Store) -> None:
    store.add_run("run-1")
    store.add_run("run-2")
    store.failures.add("run-1", 3, PERIOD, failure("H1", "H2"), T0)
    store.failures.add("run-2", 3, PERIOD, failure("H1", "H2"), T0)

    store.failures.clear("run-1", 3)

    assert store.failures.of_run("run-1") == []
    assert len(store.failures.of_run("run-2")) == 1
