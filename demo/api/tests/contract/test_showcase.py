"""The Showcase port, and the refusal to delete the showcased pricing version: one suite, run
against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.showcase import Showcase, ShowcaseMark
from pricing_demo.domain.pricing_versions import IsShowcase, new_draft_goals
from pricing_demo.infrastructure.fakes.pricing_versions import FakePricingVersions
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.showcase import InMemoryShowcase
from tests.support.runs import T0, later

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"


@dataclass
class Env:
    showcase: Showcase
    pricing: PricingVersions

    def version(self) -> str:
        if isinstance(self.pricing, FakePricingVersions):
            return self.pricing.create_draft(
                VERSION, None, new_draft_goals(None), PERIOD, None, T0
            ).id
        raise AssertionError("the PostgreSQL env makes its versions itself")


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def env(request: pytest.FixtureRequest) -> Iterator[tuple[Env, list[str]]]:
    if request.param == "fake":
        showcase = InMemoryShowcase()
        pricing = FakePricingVersions(InMemoryRunRepository(), showcase=showcase)
        fake = Env(showcase, pricing)
        yield fake, [fake.version(), fake.version()]
        return
    from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
    from pricing_demo.infrastructure.persistence.showcase import PostgresShowcase
    from tests.support.pricing_versions import insert_pricing_version

    engine: Engine = request.getfixturevalue("migrated_database")
    versions = [insert_pricing_version(engine, VERSION, letter, "sealed") for letter in "AB"]
    yield Env(PostgresShowcase(engine), PostgresPricingVersions(engine)), versions


Rig = tuple[Env, list[str]]


def test_nothing_is_marked_at_first(env: Rig) -> None:
    assert env[0].showcase.current() is None


def test_a_mark_is_read_back_and_a_new_mark_replaces_it(env: Rig) -> None:
    rig, (first, second) = env

    rig.showcase.mark(first, PERIOD, T0)
    assert rig.showcase.current() == ShowcaseMark(first, PERIOD, T0)

    rig.showcase.mark(second, PERIOD, later(5))
    assert rig.showcase.current() == ShowcaseMark(second, PERIOD, later(5))


def test_the_showcased_version_is_not_deleted_and_another_is(env: Rig) -> None:
    rig, (first, second) = env
    rig.showcase.mark(first, PERIOD, T0)

    with pytest.raises(IsShowcase):
        rig.pricing.delete(first)
    rig.pricing.delete(second)

    assert rig.pricing.get(first) is not None
    assert rig.pricing.get(second) is None
    assert rig.showcase.current() is not None


def test_a_version_that_is_no_longer_marked_is_deleted(env: Rig) -> None:
    rig, (first, second) = env
    rig.showcase.mark(first, PERIOD, T0)
    rig.showcase.mark(second, PERIOD, later(1))

    rig.pricing.delete(first)

    assert rig.pricing.get(first) is None
