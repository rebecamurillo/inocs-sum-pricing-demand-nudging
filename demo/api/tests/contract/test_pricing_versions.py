"""The PricingVersions port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator
from dataclasses import dataclass, replace

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.builds import RunActive
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    InstanceVersionNotFound,
    VersionSealed,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.pricing_versions import (
    PricingVersion,
    PricingVersionNotFound,
    UnknownBasedOn,
    new_draft_goals,
)
from pricing_demo.domain.runs import RunKind, RunState
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.pricing_versions import FakePricingVersions
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from tests.support.runs import T0, later, make_run

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"
GOALS = new_draft_goals(None)


@dataclass
class Env:
    pricing: PricingVersions
    runs: RunRepository
    instances: CityInstances
    engine: Engine | None = None

    def draft(self, name: str | None = None) -> str:
        return self.pricing.create_draft(VERSION, name, GOALS, PERIOD, None, T0).id

    def seal(self, version_id: str) -> None:
        if isinstance(self.pricing, FakePricingVersions):
            self.pricing.seal(version_id, T0)
            return
        from sqlalchemy import text

        assert self.engine is not None
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE pricing_versions SET status = 'sealed', sealed_at = :at WHERE id = :id"
                ),
                {"at": T0, "id": version_id},
            )

    def run(self, run_id: str, version_id: str, state: RunState, at: int = 1) -> None:
        self.runs.add(
            make_run(
                run_id,
                kind=RunKind.PRICING,
                subject_id=version_id,
                state=state,
                queued_at=later(at),
            )
        )


def stored(env: "Env", version_id: str) -> PricingVersion:
    version = env.pricing.get(version_id)
    assert version is not None
    return version


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def env(request: pytest.FixtureRequest) -> Iterator[Env]:
    draft = InstanceVersion(VERSION, "geneva-3km", 1, None, "sealed", PARAMETERS, T0, T0)
    instance = CityInstance("geneva-3km", "Geneva 3 km", DATASET.id, 2, T0)
    if request.param == "fake":
        runs = InMemoryRunRepository()
        instances = InMemoryCityInstances()
        instances.create(instance, replace(draft, status="draft"), first_period(VERSION, DATASET))
        yield Env(FakePricingVersions(runs, instances), runs, instances)
        return
    from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
    from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
    from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
    from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresCityDatasets(engine).add(DATASET)
    stored = PostgresCityInstances(engine)
    stored.create(instance, replace(draft, status="draft"), first_period(VERSION, DATASET))
    yield Env(PostgresPricingVersions(engine), PostgresRunRepository(engine), stored, engine)


def test_letters_follow_creation_and_are_never_reused(env: Env) -> None:
    first, second, third = env.draft(), env.draft("Cheaper"), env.draft()

    env.pricing.delete(second)

    assert [first, third] == ["geneva-3km.v1.A", "geneva-3km.v1.C"]
    assert env.draft() == "geneva-3km.v1.D"
    assert [item.version.letter for item in env.pricing.list_for(VERSION)] == ["A", "C", "D"]


def test_a_draft_is_stored_with_its_goals_name_and_period(env: Env) -> None:
    env.pricing.create_draft(VERSION, None, GOALS, PERIOD, None, T0)
    version = env.pricing.create_draft(VERSION, "Named", GOALS, PERIOD, "geneva-3km.v1.A", T0)

    stored = env.pricing.get(version.id)

    assert stored == version
    assert (stored.name, stored.status, stored.based_on_id) == ("Named", "draft", "geneva-3km.v1.A")
    assert stored.goals == GOALS
    assert env.pricing.period_ids(version.id) == [PERIOD]
    assert env.pricing.get("geneva-3km.v1.Z") is None
    assert env.pricing.get(env.draft().replace(".C", ".X")) is None


def test_the_first_default_name_is_version_and_the_letter(env: Env) -> None:
    assert stored(env, env.draft()).name == "Version A"


def test_a_draft_needs_an_instance_version(env: Env) -> None:
    with pytest.raises(InstanceVersionNotFound):
        env.pricing.create_draft("nope.v1", None, GOALS, "nope.v1.mon-08", None, T0)


def test_a_copy_needs_its_source_on_the_same_instance_version(env: Env) -> None:
    source = env.draft()
    env.pricing.delete(source)

    for based_on in (source, "geneva-2km.v1.A"):
        with pytest.raises(UnknownBasedOn):
            env.pricing.create_draft(VERSION, None, GOALS, PERIOD, based_on, T0)
    assert env.pricing.list_for(VERSION) == []


def test_letters_run_on_past_z(env: Env) -> None:
    for _ in range(27):
        last = env.draft()

    assert last == "geneva-3km.v1.AA"
    assert [item.version.letter for item in env.pricing.list_for(VERSION)][-2:] == ["Z", "AA"]
    assert env.pricing.letters_by_instance_version([VERSION])[VERSION][-2:] == ["Z", "AA"]


def test_a_change_leaves_the_other_goals_and_stores_values_as_sent(env: Env) -> None:
    version = env.draft()

    updated = env.pricing.update_draft(version, {"cost_bike_chf": -2, "max_displayed_options": 0})

    assert (updated.goals.cost_bike_chf, updated.goals.max_displayed_options) == (-2, 0)
    assert updated.goals.ridership_weight == GOALS.ridership_weight
    assert env.pricing.get(version) == updated


def test_a_sealed_version_does_not_change_and_an_unknown_one_is_not_found(env: Env) -> None:
    version = env.draft()
    env.seal(version)

    with pytest.raises(VersionSealed):
        env.pricing.update_draft(version, {"cost_bike_chf": 1})
    with pytest.raises(PricingVersionNotFound):
        env.pricing.update_draft("geneva-3km.v1.Q", {})


def test_the_previous_sealed_version_is_the_highest_letter_that_is_sealed(env: Env) -> None:
    first, second, third = env.draft(), env.draft(), env.draft()
    assert env.pricing.previous_sealed(VERSION) is None
    env.seal(first)
    env.seal(second)

    previous = env.pricing.previous_sealed(VERSION)

    assert previous is not None
    assert previous.id == second
    assert stored(env, third).status == "draft"


def test_the_state_is_derived_from_the_status_and_the_last_run(env: Env) -> None:
    draft, running, done = env.draft(), env.draft(), env.draft()
    env.seal(running)
    env.seal(done)
    env.run("r-old", done, RunState.FAILED, at=1)
    env.run("r-new", done, RunState.SUCCEEDED, at=2)
    env.run("r-run", running, RunState.RUNNING)

    states = {item.version.id: item.state for item in env.pricing.list_for(VERSION)}

    assert states == {draft: "draft", running: "running", done: "result"}


def test_deleting_removes_the_version_its_periods_and_its_finished_runs(env: Env) -> None:
    version = env.draft()
    env.seal(version)
    env.run("r1", version, RunState.FAILED)
    env.run("r2", version, RunState.SUCCEEDED, at=2)

    env.pricing.delete(version)

    assert env.pricing.get(version) is None
    assert env.pricing.period_ids(version) == []
    assert env.runs.get("r1") is None
    assert env.runs.get("r2") is None


@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING])
def test_a_version_with_an_active_run_is_not_deleted(env: Env, state: RunState) -> None:
    version = env.draft()
    env.seal(version)
    env.run("r1", version, state)

    with pytest.raises(RunActive) as refusal:
        env.pricing.delete(version)

    assert refusal.value.run_id == "r1"
    assert env.pricing.get(version) is not None


def test_deleting_an_unknown_version_is_not_found(env: Env) -> None:
    with pytest.raises(PricingVersionNotFound):
        env.pricing.delete("geneva-3km.v1.A")


def test_a_copy_of_a_deleted_version_loses_its_source(env: Env) -> None:
    source = env.draft()
    copy = env.pricing.create_draft(VERSION, None, GOALS, PERIOD, source, T0)

    env.pricing.delete(source)

    assert stored(env, copy.id).based_on_id is None


def test_the_letters_of_each_instance_version(env: Env) -> None:
    env.draft()
    env.draft()

    assert env.pricing.letters_by_instance_version([VERSION, "other.v1"]) == {VERSION: ["A", "B"]}
    assert env.pricing.letters_by_instance_version([]) == {}
