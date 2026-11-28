"""The Solves port: one suite, run against the fake and the PostgreSQL adapter. It also pins
what a stored solve means for the artefacts (never collected while referenced) and for the
deletion of a pricing version."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from pricing_demo.application.ports.artifacts import Artifact, Artifacts, StoredFile
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.solves import SolveRef, Solves, StoredResultSummary
from pricing_demo.domain.derived_result import DERIVATION_VERSION, ResultNumbers
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.solves import (
    Solve,
    SolveOd,
    SolveProvenance,
    SolveQuality,
    SolveRow,
)
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.pricing_versions import FakePricingVersions
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.solves import InMemorySolves
from tests.support.runs import T0, later

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"
KEY = "k" * 64


@dataclass
class Env:
    solves: Solves
    artifacts: Artifacts
    pricing: PricingVersions
    new_version: Callable[[str], str]

    def store(
        self,
        version: str,
        key: str = KEY,
        solve: Solve | None = None,
        at: datetime = T0,
        summary: StoredResultSummary | None = None,
    ) -> None:
        self.solves.store(artifact(key), solve or a_solve(), version, PERIOD, at, summary)


def artifact(key: str = KEY) -> Artifact:
    return Artifact(
        input_key=key,
        step=StepName.PRICING_MODEL,
        inputs={"step": "pricing_model"},
        files=(StoredFile("solution.json", "ab" * 32, 10),),
        path=f"artifacts/pricing_model/{key}",
        package_fingerprint=FAKE_FINGERPRINT.fingerprint,
        created_at=T0,
    )


def a_solve(objective: float = 12.5) -> Solve:
    return Solve(
        SolveQuality(2, "OPTIMAL", objective, 0.0, 1.5, 1, False),
        SolveProvenance(
            "11.0.3",
            "full",
            {"Threads": 4, "TimeLimit": 7200},
            FAKE_FINGERPRINT.fingerprint,
            "0.1.0",
            "c" * 64,
            "linux",
        ),
        (
            SolveRow("2p", "A", "B", "PT-Only", 1.0, 3.0, None, 2.0, 0.0, 0.0),
            SolveRow("1b", "A", "B", "PT+Bike", 1.0, 4.0, 1.5, 3.5, 0.0, 0.0),
            SolveRow("car_1", "A", "B", "Car", 1.0, 3.0, None, 6.0, 0.0, 0.0),
        ),
        (SolveOd("A", "B", 0.25), SolveOd("B", "A", 0.0)),
    )


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def env(request: pytest.FixtureRequest) -> Iterator[Env]:
    if request.param == "fake":
        runs = InMemoryRunRepository()
        artifacts = InMemoryArtifacts()
        solves = InMemorySolves(artifacts)
        pricing = FakePricingVersions(runs, solves=solves)

        def new_fake_version(letter: str) -> str:
            return pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id

        yield Env(solves, artifacts, pricing, new_fake_version)
        return
    from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
    from pricing_demo.infrastructure.persistence.package_fingerprints import (
        PostgresPackageFingerprints,
    )
    from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
    from pricing_demo.infrastructure.persistence.solves import PostgresSolves
    from tests.support.pricing_versions import insert_pricing_version

    engine: Engine = request.getfixturevalue("migrated_database")
    PostgresPackageFingerprints(engine).record(FAKE_FINGERPRINT, T0)

    def new_stored_version(letter: str) -> str:
        return insert_pricing_version(engine, VERSION, letter, status="sealed")

    yield Env(
        PostgresSolves(engine), PostgresArtifacts(engine), PostgresPricingVersions(engine),
        new_stored_version,
    )  # fmt: skip


def test_a_stored_solve_is_known_by_its_key_and_gives_its_rows_in_arc_order(env: Env) -> None:
    version = env.new_version("A")
    assert env.solves.is_stored(KEY) is False

    env.store(version)

    assert env.solves.is_stored(KEY) is True
    assert env.solves.is_stored("other") is False
    assert [row.arc_id for row in env.solves.rows(KEY)] == ["1b", "2p", "car_1"]
    assert env.solves.rows(KEY) == sorted(a_solve().rows, key=lambda row: row.arc_id)
    assert env.solves.rows("other") == []
    assert env.solves.solve_key_of(version, PERIOD) == KEY
    assert env.solves.solve_key_of(version, "elsewhere") is None


def test_a_solve_is_found_by_its_id_and_an_unknown_id_is_not(env: Env) -> None:
    version = env.new_version("A")
    env.store(version)

    assert env.solves.find(f"{version}.mon-08") == SolveRef(
        f"{version}.mon-08", version, PERIOD, KEY
    )
    assert env.solves.find(f"{version}.tue-08") is None
    assert env.solves.find("other") is None


def test_the_version_keeps_the_quality_and_provenance_of_its_solve(env: Env) -> None:
    version = env.new_version("A")

    env.store(version)

    record = env.solves.solve_of(version, PERIOD)
    assert record is not None
    assert record.key == KEY
    assert record.quality == a_solve().quality
    assert record.provenance == a_solve().provenance
    assert record.created_at == T0


def test_a_second_version_with_the_same_key_gets_its_own_row_over_the_shared_artefact(
    env: Env,
) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.store(first)

    env.solves.link_stored(KEY, second, PERIOD, later(5))

    assert env.solves.solve_key_of(second, PERIOD) == KEY
    record = env.solves.solve_of(second, PERIOD)
    assert record is not None
    assert (record.quality, record.provenance) == (a_solve().quality, a_solve().provenance)
    assert record.created_at == later(5)
    assert len(env.solves.rows(KEY)) == 3


def test_linking_a_key_no_solve_has_is_refused(env: Env) -> None:
    version = env.new_version("A")

    with pytest.raises(KeyError):
        env.solves.link_stored("nope", version, PERIOD, T0)
    assert env.solves.solve_key_of(version, PERIOD) is None


def test_storing_a_key_that_is_stored_adds_only_the_versions_row(env: Env) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.store(first)

    env.store(second, solve=a_solve(objective=99.0))

    assert env.solves.solve_key_of(second, PERIOD) == KEY
    assert len(env.solves.rows(KEY)) == 3
    record = env.solves.solve_of(first, PERIOD)
    assert record is not None
    assert record.quality.objective_value == 12.5


def test_a_new_solve_of_the_same_version_and_period_replaces_the_old_row(env: Env) -> None:
    version = env.new_version("A")
    env.store(version)

    env.store(version, key="n" * 64, at=later(9))

    assert env.solves.solve_key_of(version, PERIOD) == "n" * 64


def test_a_failed_store_leaves_no_artefact_no_rows_and_no_solve(env: Env) -> None:
    version = env.new_version("A")
    twice = Solve(a_solve().quality, a_solve().provenance, (*a_solve().rows, a_solve().rows[0]))

    with pytest.raises((ValueError, IntegrityError)):
        env.store(version, solve=twice)

    assert env.solves.is_stored(KEY) is False
    assert env.artifacts.get(KEY) is None
    assert env.solves.solve_key_of(version, PERIOD) is None


def test_an_artefact_a_solve_references_is_never_collected(env: Env) -> None:
    version = env.new_version("A")
    env.store(version)

    assert KEY not in {item.input_key for item in env.artifacts.unreferenced()}
    assert env.artifacts.remove(KEY) is False
    assert env.solves.is_stored(KEY) is True


def test_deleting_the_version_removes_its_solve_and_frees_the_artefact_and_its_rows(
    env: Env,
) -> None:
    version = env.new_version("A")
    env.store(version)

    env.pricing.delete(version)

    assert env.solves.solve_key_of(version, PERIOD) is None
    assert KEY in {item.input_key for item in env.artifacts.unreferenced()}
    assert env.artifacts.remove(KEY) is True
    assert env.solves.is_stored(KEY) is False
    assert env.solves.rows(KEY) == []


def test_the_artefact_stays_while_another_version_still_points_to_it(env: Env) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.store(first)
    env.solves.link_stored(KEY, second, PERIOD, T0)

    env.pricing.delete(first)

    assert KEY not in {item.input_key for item in env.artifacts.unreferenced()}
    assert env.solves.is_stored(KEY) is True
    assert env.solves.solve_key_of(second, PERIOD) == KEY


def a_summary(
    key: str = KEY,
    version: int = DERIVATION_VERSION,
    package: dict[str, object] | None = None,
    residual: float | None = 0.25,
) -> StoredResultSummary:
    numbers = ResultNumbers(
        {"ridership": Number(4, "travellers", "model", "headline")}, (), (), None, residual
    )
    return StoredResultSummary(key, version, numbers, package, T0)


def test_a_summary_stored_with_the_solve_is_read_back(env: Env) -> None:
    version = env.new_version("A")
    summary = a_summary(package={"Obj Value": 12.5})

    env.store(version, summary=summary)

    assert env.solves.summary_of(KEY, DERIVATION_VERSION) == summary
    assert env.solves.summary_of(KEY, DERIVATION_VERSION + 1) is None
    assert env.solves.summary_of("other", DERIVATION_VERSION) is None


def test_a_solve_without_a_summary_has_none(env: Env) -> None:
    env.store(env.new_version("A"))

    assert env.solves.summary_of(KEY, DERIVATION_VERSION) is None
    assert env.solves.package_summary_of(KEY) is None


def test_storing_a_key_again_keeps_its_first_summary(env: Env) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.store(first, summary=a_summary(residual=0.1))

    env.store(second, summary=a_summary(residual=0.9))

    found = env.solves.summary_of(KEY, DERIVATION_VERSION)
    assert found is not None
    assert found.numbers.objective_residual == 0.1


def test_a_summary_is_added_to_a_stored_solve_once(env: Env) -> None:
    env.store(env.new_version("A"))

    env.solves.store_summary(a_summary(residual=0.1))
    env.solves.store_summary(a_summary(residual=0.9))

    found = env.solves.summary_of(KEY, DERIVATION_VERSION)
    assert found is not None
    assert found.numbers.objective_residual == 0.1


def test_a_summary_for_a_solve_that_is_not_stored_is_refused(env: Env) -> None:
    with pytest.raises((KeyError, IntegrityError)):
        env.solves.store_summary(a_summary("nope"))


def test_the_package_summary_comes_from_any_derivation_version_of_the_key(env: Env) -> None:
    env.store(env.new_version("A"), summary=a_summary(package={"Obj Value": 12.5}))

    assert env.solves.package_summary_of(KEY) == {"Obj Value": 12.5}
    env.solves.store_summary(a_summary(version=DERIVATION_VERSION + 1, package=None))
    assert env.solves.package_summary_of(KEY) == {"Obj Value": 12.5}
