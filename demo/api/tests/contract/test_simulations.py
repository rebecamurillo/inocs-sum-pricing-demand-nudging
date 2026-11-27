"""The Simulations port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.simulations import (
    SimulationLink,
    Simulations,
    StoredSimulation,
)
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.read_model import OptionStationDeltaRow, StationBikesRow
from pricing_demo.domain.traveller_simulation import (
    BalancedScore,
    FlatPrice,
    SimulationInstance,
    SimulationOption,
    SimulationOutputs,
    SimulationPair,
)
from pricing_demo.infrastructure.fakes.pricing_versions import FakePricingVersions
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.simulations import InMemorySimulations
from tests.support.runs import T0, later

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"


def outputs() -> SimulationOutputs:
    instance = SimulationInstance(
        (SimulationPair("A", "B", 10), SimulationPair("B", "A", 4)),
        (
            SimulationOption("1b", "A", "B", "pt_bike", 600, 0, 1),
            SimulationOption("2p", "A", "B", "pt_only", 900, 60),
            SimulationOption("3c", "A", "B", "car", 500, 0, 0, 4.0, 1.0),
            SimulationOption("4p", "B", "A", "pt_only", 900, 60),
        ),
        (StationBikesRow("s1", 5, 3), StationBikesRow("s2", 5, 0)),
        (OptionStationDeltaRow("1b", "s1", -1), OptionStationDeltaRow("1b", "s2", 1)),
    )
    return BalancedScore().simulate(instance, FlatPrice(1.0, 2.0, 2.8))


def stored(key: str, kind: str = "flat", at: datetime = T0) -> StoredSimulation:
    return StoredSimulation(
        key=key,
        instance_key="i" * 64,
        period_id=PERIOD,
        outputs=outputs(),
        scheme_kind=kind,  # type: ignore[arg-type]
        solve_key=None if kind == "flat" else "s" * 64,
        flat_price_kind="per_ride" if kind == "flat" else None,
        flat_price_amount_chf=1.0 if kind == "flat" else None,
        pt_fare_chf=2.0,
        car_parking_fee_chf=2.8,
        demonstrator_version="0.1.0",
        duration_s=0.25,
        created_at=at,
    )


def link(version: str, key: str, scheme: str = "flat", at: datetime = T0) -> SimulationLink:
    return SimulationLink(version, PERIOD, scheme, "balanced-score", 1, key, at)


@dataclass
class Env:
    simulations: Simulations
    pricing: PricingVersions
    new_version: Callable[[str], str]
    # The number of child rows of a simulation: modes, choices, pairs, stations.
    children: Callable[[str], tuple[int, int, int, int]]
    created_at: Callable[[str], datetime | None]


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def env(request: pytest.FixtureRequest) -> Iterator[Env]:
    if request.param == "fake":
        runs = InMemoryRunRepository()
        simulations = InMemorySimulations()
        pricing = FakePricingVersions(runs, simulations=simulations)

        def new_fake_version(letter: str) -> str:
            return pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id

        def fake_children(key: str) -> tuple[int, int, int, int]:
            found = simulations.get(key)
            if found is None:
                return (0, 0, 0, 0)
            out = found.outputs
            return (
                len(out.travellers_per_mode),
                len(out.options),
                len(out.unserved_per_pair),
                len(out.stations_end),
            )

        def fake_created(key: str) -> datetime | None:
            found = simulations.get(key)
            return None if found is None else found.created_at

        yield Env(simulations, pricing, new_fake_version, fake_children, fake_created)
        return
    from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
    from pricing_demo.infrastructure.persistence.simulations import PostgresSimulations
    from tests.support.pricing_versions import insert_pricing_version

    engine: Engine = request.getfixturevalue("migrated_database")

    def new_stored_version(letter: str) -> str:
        return insert_pricing_version(engine, VERSION, letter, status="sealed")

    def count(table: str, key: str) -> int:
        with engine.connect() as connection:
            return int(
                connection.execute(
                    text(f"SELECT count(*) FROM {table} WHERE simulation_key = :key"),
                    {"key": key},
                ).scalar_one()
            )

    def children(key: str) -> tuple[int, int, int, int]:
        return (
            count("simulation_modes", key),
            count("simulation_choices", key),
            count("simulation_pairs", key),
            count("simulation_stations", key),
        )

    def created(key: str) -> datetime | None:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT created_at FROM simulations WHERE simulation_key = :key"),
                {"key": key},
            ).scalar()

    yield Env(
        PostgresSimulations(engine),
        PostgresPricingVersions(engine),
        new_stored_version,
        children,
        created,
    )


def test_a_stored_simulation_has_its_child_rows_and_its_link(env: Env) -> None:
    version = env.new_version("A")
    out = outputs()

    env.simulations.store([stored("sim-1")], [link(version, "sim-1")])

    assert env.simulations.is_stored("sim-1") is True
    assert env.simulations.is_stored("sim-2") is False
    assert env.children("sim-1") == (3, len(out.options), len(out.unserved_per_pair), 2)
    assert env.simulations.links_of(version) == [link(version, "sim-1")]


def test_a_stored_key_is_left_as_it_is_and_the_new_link_is_added(env: Env) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.simulations.store([stored("sim-1", at=T0)], [link(first, "sim-1")])

    env.simulations.store([stored("sim-1", at=later(30))], [link(second, "sim-1")])

    assert env.created_at("sim-1") == T0
    assert env.children("sim-1")[0] == 3
    assert [item.simulation_key for item in env.simulations.links_of(first)] == ["sim-1"]
    assert [item.simulation_key for item in env.simulations.links_of(second)] == ["sim-1"]


def test_a_link_to_a_stored_simulation_needs_no_new_simulation(env: Env) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.simulations.store([stored("sim-1")], [link(first, "sim-1")])

    env.simulations.store([], [link(second, "sim-1")])

    assert [item.simulation_key for item in env.simulations.links_of(second)] == ["sim-1"]


def test_a_version_has_a_link_per_scheme_and_a_new_key_replaces_the_link_of_its_scheme(
    env: Env,
) -> None:
    version = env.new_version("A")
    env.simulations.store(
        [stored("sim-flat"), stored("sim-model", "model_prices")],
        [link(version, "sim-flat"), link(version, "sim-model", "model_prices")],
    )

    env.simulations.store([stored("sim-flat-2", at=later(5))], [link(version, "sim-flat-2")])

    keys = {item.price_scheme: item.simulation_key for item in env.simulations.links_of(version)}
    assert keys == {"flat": "sim-flat-2", "model_prices": "sim-model"}


def test_a_failed_store_leaves_no_simulation_and_no_link(env: Env) -> None:
    version = env.new_version("A")

    with pytest.raises((KeyError, IntegrityError)):
        env.simulations.store(
            [stored("sim-1")], [link(version, "sim-1"), link(version, "missing", "model_prices")]
        )

    assert env.simulations.is_stored("sim-1") is False
    assert env.children("sim-1") == (0, 0, 0, 0)
    assert env.simulations.links_of(version) == []


def test_the_unlinked_simulations_are_removed_with_their_children(env: Env) -> None:
    version = env.new_version("A")
    env.simulations.store(
        [stored("sim-kept"), stored("sim-lost", "model_prices")], [link(version, "sim-kept")]
    )

    removed = env.simulations.remove_unlinked()

    assert removed == 1
    assert env.simulations.is_stored("sim-kept") is True
    assert env.simulations.is_stored("sim-lost") is False
    assert env.children("sim-lost") == (0, 0, 0, 0)
    assert env.children("sim-kept")[0] == 3
    assert env.simulations.remove_unlinked() == 0


def test_deleting_a_version_removes_its_links_and_frees_a_simulation_nobody_else_uses(
    env: Env,
) -> None:
    first, second = env.new_version("A"), env.new_version("B")
    env.simulations.store(
        [stored("sim-shared"), stored("sim-own", "model_prices")],
        [link(first, "sim-shared"), link(first, "sim-own", "model_prices")],
    )
    env.simulations.store([], [link(second, "sim-shared")])

    env.pricing.delete(first)

    assert env.simulations.links_of(first) == []
    assert env.simulations.remove_unlinked() == 1
    assert env.simulations.is_stored("sim-shared") is True
    assert env.simulations.is_stored("sim-own") is False


def test_the_links_come_in_scheme_order(env: Env) -> None:
    version = env.new_version("A")
    other = replace(link(version, "sim-2", "model_prices"), rule_version=2)
    env.simulations.store(
        [stored("sim-1"), stored("sim-2", "model_prices")],
        [link(version, "sim-1"), other],
    )

    found = env.simulations.links_of(version)

    assert [(item.price_scheme, item.rule_version) for item in found] == [
        ("flat", 1),
        ("model_prices", 2),
    ]


def test_the_linked_simulations_carry_their_rule_parameters_in_link_order(env: Env) -> None:
    version = env.new_version("A")
    other = replace(link(version, "sim-2", "model_prices"), rule_version=2)
    env.simulations.store(
        [stored("sim-1"), stored("sim-2", "model_prices")],
        [link(version, "sim-1"), other],
    )

    found = env.simulations.linked_of(version)

    assert [(item.price_scheme, item.rule_id, item.rule_version) for item in found] == [
        ("flat", "balanced-score", 1),
        ("model_prices", "balanced-score", 2),
    ]
    assert [item.simulation_key for item in found] == ["sim-1", "sim-2"]
    assert [item.created_at for item in found] == [T0, T0]
    assert all(item.rule_parameters == {"price_weight": 0.5, "time_weight": 0.5} for item in found)
    assert env.simulations.linked_of("geneva-3km.v1.Z") == []


def test_a_stored_simulation_summarises_itself(env: Env) -> None:
    version = env.new_version("A")
    out = outputs()
    env.simulations.store(
        [stored("sim-1", "model_prices")], [link(version, "sim-1", "model_prices")]
    )

    summary = env.simulations.summary_of("sim-1")

    assert summary is not None
    assert (summary.key, summary.price_scheme) == ("sim-1", "model_prices")
    assert (summary.rule_id, summary.rule_version) == ("balanced-score", 1)
    assert dict(summary.rule_parameters) == dict(out.parameters)
    assert dict(summary.travellers_per_mode) == dict(out.travellers_per_mode)
    assert summary.travellers == sum(out.travellers_per_mode.values()) + out.unserved
    assert (summary.displaced, summary.unserved) == (out.displaced, out.unserved)
    assert summary.bike_rides == out.bike_rides
    assert summary.bike_revenue_chf == out.bike_revenue_chf
    assert summary.stations_empty == len(out.stations_empty)
    assert summary.stations_full == len(out.stations_full)
    assert summary.created_at == T0
    assert env.simulations.summary_of("other") is None
