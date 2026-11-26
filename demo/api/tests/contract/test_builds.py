"""The Builds port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.builds import DraftChanged, RunActive
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    InstanceVersionNotFound,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.runs import Run, RunState, RunStep, StepName, StepState
from pricing_demo.infrastructure.fakes.builds import InMemoryBuilds
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from tests.support.runs import T0, later, make_run, step

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
PERIOD = "geneva-3km.v1.mon-08"


@dataclass
class Env:
    builds: Builds
    runs: RunRepository
    instances: CityInstances

    def version(
        self, slug: str = "geneva-3km", radius: float = 3000.0, dataset: str | None = None
    ) -> str:
        draft = InstanceVersion(
            f"{slug}.v1", slug, 1, None, "draft", replace(PARAMETERS, radius_m=radius), T0
        )
        self.instances.create(
            CityInstance(slug, slug, dataset or DATASET.id, 2, T0),
            draft,
            first_period(draft.id, DATASET),
        )
        return draft.id

    def build_run(self, run_id: str, version: str = "geneva-3km.v1", **fields: Any) -> Run:
        run = make_run(run_id, subject_id=version, **fields)
        self.runs.add(run)
        return run


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def env(request: pytest.FixtureRequest) -> Iterator[Env]:
    if request.param == "fake":
        runs = InMemoryRunRepository()
        instances = InMemoryCityInstances()
        yield Env(InMemoryBuilds(runs, instances), runs, instances)
        return
    from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
    from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
    from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
    from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresCityDatasets(engine).add(DATASET)
    yield Env(PostgresBuilds(engine), PostgresRunRepository(engine), PostgresCityInstances(engine))


def queued_run(run_id: str, version: str = "geneva-3km.v1", at: int = 0) -> Run:
    steps = tuple(
        step(position, name, period=PERIOD if position > 2 else None, input_key=f"key-{position}")
        for position, name in enumerate(
            (
                StepName.AREA,
                StepName.HUBS,
                StepName.ROUTES,
                StepName.TRAVELLERS_AND_BIKES,
            ),
            start=1,
        )
    )
    return make_run(run_id, subject_id=version, queued_at=later(at), steps=steps)


def test_a_version_with_no_build_has_no_latest_run_and_no_state(env: Env) -> None:
    version = env.version()

    assert env.builds.latest_build_run(version) is None
    assert env.builds.latest_build_states([version]) == {}
    assert env.builds.latest_build_states([]) == {}


def test_the_latest_build_run_is_the_one_queued_last(env: Env) -> None:
    version = env.version()
    env.build_run("r1", version, state=RunState.FAILED, queued_at=later(1))
    env.build_run("r3", version, state=RunState.CANCELLED, queued_at=later(3))
    env.build_run("r2", version, state=RunState.FAILED, queued_at=later(2))

    latest = env.builds.latest_build_run(version)

    assert latest is not None
    assert (latest.id, latest.state, len(latest.steps)) == ("r3", RunState.CANCELLED, 4)


def test_the_latest_states_are_read_per_version(env: Env) -> None:
    first = env.version("geneva-3km")
    second = env.version("lyon")
    env.version("paris")
    env.build_run("r1", first, state=RunState.FAILED, queued_at=later(1))
    env.build_run("r2", first, state=RunState.SUCCEEDED, queued_at=later(2))
    env.build_run("r3", second, state=RunState.RUNNING, queued_at=later(3))

    states = env.builds.latest_build_states([first, second, "paris.v1"])

    assert states == {first: RunState.SUCCEEDED, second: RunState.RUNNING}


def test_queueing_a_build_seals_the_draft_and_stores_the_run_with_its_steps(env: Env) -> None:
    version = env.version()

    env.builds.queue_build(queued_run("r1"), later(5))

    sealed = env.instances.get_version(version)
    assert sealed is not None
    assert (sealed.status, sealed.sealed_at) == ("sealed", later(5))
    stored = env.runs.get("r1")
    assert stored == queued_run("r1")
    assert [(item.position, item.period, item.input_key) for item in stored.steps] == [
        (1, None, "key-1"),
        (2, None, "key-2"),
        (3, PERIOD, "key-3"),
        (4, PERIOD, "key-4"),
    ]


def test_queueing_a_build_without_a_seal_leaves_the_version_as_it_is(env: Env) -> None:
    version = env.version()

    env.builds.queue_build(queued_run("r1"), None)

    stored = env.instances.get_version(version)
    assert stored is not None
    assert (stored.status, stored.sealed_at) == ("draft", None)
    assert env.runs.get("r1") is not None


def test_a_draft_is_sealed_when_its_values_are_still_the_ones_checked(env: Env) -> None:
    version = env.version()
    checked = env.instances.get_version(version).parameters  # type: ignore[union-attr]

    env.builds.queue_build(queued_run("r1"), later(5), checked=checked)

    stored = env.instances.get_version(version)
    assert stored is not None
    assert stored.status == "sealed"
    assert env.runs.get("r1") is not None


def test_a_draft_edited_after_its_check_is_not_sealed_and_no_run_is_stored(env: Env) -> None:
    version = env.version()
    checked = env.instances.get_version(version).parameters  # type: ignore[union-attr]
    env.instances.update_draft_parameters(version, {"radius_m": 2500.0})

    with pytest.raises(DraftChanged):
        env.builds.queue_build(queued_run("r1"), later(5), checked=checked)

    stored = env.instances.get_version(version)
    assert stored is not None
    assert (stored.status, stored.parameters.radius_m) == ("draft", 2500.0)
    assert env.runs.get("r1") is None


def test_a_version_deleted_before_its_build_is_queued_is_not_found(env: Env) -> None:
    version = env.version()
    env.instances.delete_draft(version)

    with pytest.raises(InstanceVersionNotFound):
        env.builds.queue_build(queued_run("r1"), later(5))

    assert env.runs.get("r1") is None


@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING])
def test_a_version_with_an_active_run_refuses_a_second_and_seals_nothing(
    env: Env, state: RunState
) -> None:
    version = env.version()
    env.build_run("r1", version, state=state, queued_at=later(1))

    with pytest.raises(RunActive) as refusal:
        env.builds.queue_build(queued_run("r2"), later(5))

    assert refusal.value.run_id == "r1"
    assert env.runs.get("r2") is None
    stored = env.instances.get_version(version)
    assert stored is not None
    assert (stored.status, stored.sealed_at) == ("draft", None)


def test_a_version_whose_last_run_ended_takes_another(env: Env) -> None:
    version = env.version()
    env.build_run("r1", version, state=RunState.FAILED, queued_at=later(1))

    env.builds.queue_build(queued_run("r2", at=2), None)

    latest = env.builds.latest_build_run(version)
    assert latest is not None
    assert latest.id == "r2"


def done_step(name: StepName, position: int, seconds: float, ended: int) -> RunStep:
    return step(
        position,
        name,
        StepState.DONE,
        started_at=later(ended - seconds),
        finished_at=later(ended),
    )


def test_the_last_duration_is_unknown_until_a_step_of_that_name_is_done(env: Env) -> None:
    env.version()
    env.build_run(
        "r1",
        state=RunState.FAILED,
        steps=(
            step(1, StepName.AREA, StepState.FAILED, started_at=T0, finished_at=later(9)),
            step(2, StepName.HUBS),
        ),
    )

    assert env.builds.last_duration_s(StepName.AREA, DATASET.id, 3000.0) is None
    assert env.builds.last_duration_s(StepName.HUBS, DATASET.id, 3000.0) is None


def test_the_last_duration_is_that_of_the_most_recent_done_step(env: Env) -> None:
    env.version()
    env.build_run("r1", state=RunState.SUCCEEDED, steps=(done_step(StepName.AREA, 1, 4.0, 10),))
    env.build_run(
        "r2",
        state=RunState.SUCCEEDED,
        queued_at=later(20),
        steps=(done_step(StepName.AREA, 1, 2.5, 30),),
    )

    assert env.builds.last_duration_s(StepName.AREA, DATASET.id, 3000.0) == 2.5


def test_the_last_duration_is_of_the_same_data_set_and_radius(env: Env) -> None:
    env.version("geneva-3km", radius=3000.0)
    env.version("geneva-4km", radius=4000.0)
    env.build_run(
        "r1",
        "geneva-4km.v1",
        state=RunState.SUCCEEDED,
        steps=(done_step(StepName.AREA, 1, 7.0, 10),),
    )

    assert env.builds.last_duration_s(StepName.AREA, DATASET.id, 3000.0) is None
    assert env.builds.last_duration_s(StepName.AREA, DATASET.id, 4000.0) == 7.0
    assert env.builds.last_duration_s(StepName.AREA, "another-data-set", 4000.0) is None


def test_a_step_that_was_kept_has_no_duration(env: Env) -> None:
    env.version()
    env.build_run(
        "r1",
        state=RunState.SUCCEEDED,
        steps=(step(1, StepName.AREA, StepState.KEPT, finished_at=later(3)),),
    )

    assert env.builds.last_duration_s(StepName.AREA, DATASET.id, 3000.0) is None
