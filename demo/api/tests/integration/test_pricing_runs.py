"""A pricing run end to end on PostgreSQL: the API's use case queues it, the worker's loop pieces
run it with the fake solver and the real artefact store on a temporary folder."""

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.ingest_step import StepIngestion
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.collect_unreferenced import CollectUnreferenced
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.run_build_step import BuildStepExecutor
from pricing_demo.application.use_cases.run_pricing_step import PricingModelStepExecutor
from pricing_demo.application.use_cases.run_pricing_version import RunPricingVersion
from pricing_demo.application.use_cases.run_simulation_step import TravellerSimulationStepExecutor
from pricing_demo.application.use_cases.simulate_pricing_version import SimulatePricingVersion
from pricing_demo.domain.build_plan import BUILD_STEPS
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.derived_result import DERIVATION_VERSION
from pricing_demo.domain.pricing_keys import KEPT_SOLVE_REASON
from pricing_demo.domain.pricing_versions import IsShowcase, SimulationCurrent, new_draft_goals
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus
from pricing_demo.domain.traveller_simulation import SimulationRule
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.fakes.feed_shapes import FakeFeedShapes
from pricing_demo.infrastructure.fakes.graph_fingerprints import (
    FAKE_GRAPH_MANIFEST,
    FakeGraphFingerprints,
)
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from pricing_demo.infrastructure.fakes.simulation_rule import FakeSimulationRule
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.ids import UuidV7Source
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.build_sources import PostgresBuildSources
from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.package_fingerprints import (
    PostgresPackageFingerprints,
)
from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from pricing_demo.infrastructure.persistence.route_failures import PostgresRouteFailures
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.showcase import PostgresShowcase
from pricing_demo.infrastructure.persistence.simulations import PostgresSimulations
from pricing_demo.infrastructure.persistence.solves import PostgresSolves
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.infrastructure.worker_build_sources import WorkerBuildSources
from tests.support.builds import all_available
from tests.support.runs import T0

pytestmark = pytest.mark.integration

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
SLUG = "geneva-3km"
INSTANCE_VERSION = f"{SLUG}.v1"
PERIOD = f"{INSTANCE_VERSION}.mon-08"
FINGERPRINT = FAKE_FINGERPRINT.fingerprint


@dataclass
class Rig:
    engine: Engine
    clock: FixedClock
    runs: PostgresRunRepository
    artifacts: PostgresArtifacts
    settings: PostgresFakeSettings
    pricing: PostgresPricingVersions
    solves: PostgresSolves
    simulations: PostgresSimulations
    run_pricing: RunPricingVersion
    simulate_version: SimulatePricingVersion
    process: ProcessNextRun
    collect: CollectUnreferenced

    def version(self, **changes: float) -> str:
        goals = new_draft_goals(None).replacing(changes)
        return self.pricing.create_draft(INSTANCE_VERSION, None, goals, PERIOD, None, T0).id

    def run(self, version: str) -> Run:
        """Queue the version's pricing run, have the worker process it, return it as stored."""
        queued = self.run_pricing.execute(version)
        assert self.process.execute() is True
        self.clock.advance(timedelta(seconds=10))
        return self.stored(queued.id)

    def stored(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        assert run is not None
        return run

    def rows(self, table: str) -> list[tuple[object, ...]]:
        with self.engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table}"))]

    def count(self, table: str) -> int:
        return len(self.rows(table))

    def key_of(self, version: str) -> str:
        found = self.solves.solve_key_of(version, PERIOD)
        assert found is not None
        return found

    def links(self, version: str) -> dict[str, str]:
        return {
            item.price_scheme: item.simulation_key for item in self.simulations.links_of(version)
        }


@pytest.fixture
def rig(migrated_database: Engine, tmp_path: Path) -> Rig:
    engine = migrated_database
    clock = FixedClock(T0)
    waiter = FakeWaiter(clock)
    datasets = PostgresCityDatasets(engine)
    datasets.add(DATASET)
    PostgresPackageFingerprints(engine).record(FAKE_FINGERPRINT, T0)
    workers = PostgresWorkerRegistry(engine)
    workers.register("w-1", "host", 1, T0, FINGERPRINT)
    reports = PostgresComponentReports(engine)
    reports.write(
        ComponentStatus.ready(ComponentName.TRIP_PLANNER),
        "w-1",
        T0,
        {"graph_manifest": FAKE_GRAPH_MANIFEST},
    )
    instances = PostgresCityInstances(engine)
    artifacts = PostgresArtifacts(engine)
    runs = PostgresRunRepository(engine)
    builds = PostgresBuilds(engine)
    pricing = PostgresPricingVersions(engine)
    solves = PostgresSolves(engine)
    simulations = PostgresSimulations(engine)
    read_model = PostgresReadModel(engine)
    route_failures = PostgresRouteFailures(engine)
    settings = PostgresFakeSettings(engine)
    files = LocalArtifactStore(tmp_path)
    sources = WorkerBuildSources(lambda: FINGERPRINT, FakeGraphFingerprints(tmp_path / "graph"))
    build_executor = BuildStepExecutor(
        FakeCityPreparation(settings, waiter),
        files,
        artifacts,
        runs,
        instances,
        datasets,
        sources,
        clock,
        StepIngestion(files, read_model, route_failures, FakeFeedShapes(frozenset({"1"}))),
        read_model,
        route_failures,
    )
    model = PricingModelStepExecutor(
        FakePricingSolver(settings),
        FakeProbe(ComponentName.SOLVER, settings),
        reports,
        "w-1",
        files,
        artifacts,
        solves,
        pricing,
        runs,
        sources,
        clock,
        read_model,
    )
    rule_source = FakeSimulationRule(settings).current
    simulation = TravellerSimulationStepExecutor(
        rule_source,
        pricing,
        artifacts,
        solves,
        simulations,
        read_model,
        runs,
        clock,
        "0.1.0",
    )
    registry = StepRegistry()
    for step in BUILD_STEPS:
        registry.register(step, build_executor, build_executor)
    registry.register(StepName.PRICING_MODEL, model, model)
    registry.register(StepName.TRAVELLER_SIMULATION, simulation, simulation)
    process = ProcessNextRun(
        runs, registry, workers, WorkerIdentity("w-1", "host", 1, T0), clock, waiter
    )
    planning = BuildPlanning(
        instances, datasets, artifacts, PostgresBuildSources(engine), builds, all_available
    )

    def current_status() -> SystemStatus:
        # The worker's heartbeat records the rule it reads from the fake settings.
        return replace(
            all_available(),
            simulation_rule=SimulationRule.of(FakeSimulationRule(settings).current()),
        )

    parameters = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
    version = InstanceVersion(
        INSTANCE_VERSION,
        SLUG,
        1,
        None,
        "draft",
        parameters.replacing({"min_od_distance_m": 900}),
        T0,
    )
    instances.create(
        CityInstance(SLUG, "Geneva 3 km", DATASET.id, 2, T0),
        version,
        first_period(version.id, DATASET),
    )
    BuildInstanceVersion(instances, datasets, builds, planning, UuidV7Source(), clock).execute(
        version.id
    )
    assert process.execute() is True
    clock.advance(timedelta(seconds=10))
    return Rig(
        engine,
        clock,
        runs,
        artifacts,
        settings,
        pricing,
        solves,
        simulations,
        RunPricingVersion(pricing, all_available, UuidV7Source(), clock),
        SimulatePricingVersion(pricing, simulations, current_status, UuidV7Source(), clock),
        process,
        CollectUnreferenced(artifacts, files, runs, simulations),
    )


def test_a_pricing_run_solves_ingests_the_solve_and_stores_both_simulations(rig: Rig) -> None:
    version = rig.version()

    run = rig.run(version)

    assert run.state is RunState.SUCCEEDED
    assert [item.state for item in run.steps] == [StepState.DONE, StepState.DONE]
    key = rig.key_of(version)
    assert run.steps[0].input_key == key
    assert rig.count("solves") == 1
    assert rig.count("solve_rows") > 0
    assert rig.count("solve_ods") == 24
    pricing_artifacts = [row for row in rig.rows("artifacts") if row[1] == "pricing_model"]
    assert len(pricing_artifacts) == 1
    assert rig.count("simulations") == 2
    assert set(rig.links(version)) == {"model_prices", "flat"}
    assert rig.count("pricing_version_simulations") == 2
    with rig.engine.connect() as connection:
        schemes = set(connection.execute(text("SELECT price_scheme FROM simulations")).scalars())
        offered = connection.execute(
            text("SELECT count(*) FROM solve_rows WHERE type = 'PT+Bike'")
        ).scalar_one()
        every_bike = connection.execute(
            text("SELECT count(*) FROM route_options WHERE mode = 'pt_bike'")
        ).scalar_one()
    assert schemes == {"model_prices", "flat"}
    # PT+Bike rows exist for the offered options only; the others have a row for every option.
    assert 0 < offered < every_bike


def test_a_pricing_run_stores_one_result_summary_and_a_kept_solve_reuses_it(rig: Rig) -> None:
    first = rig.version()
    rig.run(first)

    assert rig.count("result_summaries") == 1
    key = rig.key_of(first)
    stored = rig.solves.summary_of(key, DERIVATION_VERSION)
    assert stored is not None
    assert stored.numbers.numbers["ridership"].source == "model"
    assert stored.package_summary is not None
    with rig.engine.connect() as connection:
        residual = connection.execute(
            text("SELECT objective_residual FROM result_summaries")
        ).scalar_one()
    assert residual == stored.numbers.objective_residual

    second = rig.version(flat_price_per_ride_chf=2.5)
    run = rig.run(second)

    assert run.steps[0].state is StepState.KEPT
    assert rig.count("result_summaries") == 1
    assert rig.solves.summary_of(key, DERIVATION_VERSION) == stored


def test_the_showcased_version_is_not_deleted_and_another_is(rig: Rig) -> None:
    first, second = rig.version(), rig.version(flat_price_per_ride_chf=2.5)
    rig.run(first)
    rig.run(second)
    PostgresShowcase(rig.engine).mark(first, PERIOD, T0)

    with pytest.raises(IsShowcase):
        rig.pricing.delete(first)
    rig.pricing.delete(second)

    assert rig.count("solves") == 1
    assert rig.count("showcase") == 1
    assert rig.links(first) != {}


def test_a_version_that_differs_only_in_its_flat_price_keeps_the_solve_and_adds_a_flat_simulation(
    rig: Rig,
) -> None:
    first = rig.version()
    second = rig.version(flat_price_per_ride_chf=2.5)
    rig.run(first)

    run = rig.run(second)

    assert run.state is RunState.SUCCEEDED
    assert run.steps[0].state is StepState.KEPT
    assert run.steps[0].reason == KEPT_SOLVE_REASON
    assert rig.key_of(second) == rig.key_of(first)
    assert rig.count("solves") == 2
    assert len([row for row in rig.rows("artifacts") if row[1] == "pricing_model"]) == 1
    assert rig.links(second)["flat"] != rig.links(first)["flat"]
    assert rig.links(second)["model_prices"] == rig.links(first)["model_prices"]
    assert rig.count("simulations") == 3


def test_a_version_with_the_same_flat_price_fare_and_parking_fee_shares_the_flat_simulation(
    rig: Rig,
) -> None:
    first = rig.version()
    third = rig.version(cost_bike_chf=1.4, ridership_weight=3.0)
    rig.run(first)

    run = rig.run(third)

    assert run.steps[0].state is StepState.DONE
    assert rig.key_of(third) != rig.key_of(first)
    assert rig.links(third)["flat"] == rig.links(first)["flat"]
    assert rig.count("simulations") == 3
    flat_key = rig.links(first)["flat"]
    with rig.engine.connect() as connection:
        linked = connection.execute(
            text("SELECT count(*) FROM pricing_version_simulations WHERE simulation_key = :key"),
            {"key": flat_key},
        ).scalar_one()
    assert linked == 2


def test_a_failure_of_the_solver_stores_nothing_and_run_again_succeeds(rig: Rig) -> None:
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "pricing_model", "code": "solver_no_solution"}}
    )
    version = rig.version()

    failed = rig.run(version)

    assert failed.state is RunState.FAILED
    assert (failed.steps[0].state, failed.steps[1].state) == (StepState.FAILED, StepState.PENDING)
    assert failed.failure is not None
    assert failed.failure.code == "solver_no_solution"
    for table in ("solves", "solve_rows", "solve_ods", "simulations"):
        assert rig.count(table) == 0
    assert [row for row in rig.rows("artifacts") if row[1] == "pricing_model"] == []
    rig.settings.set_pricing_model(None)

    again = rig.run(version)

    assert again.state is RunState.SUCCEEDED
    assert [item.state for item in again.steps] == [StepState.DONE, StepState.DONE]
    assert rig.count("solves") == 1
    assert rig.count("simulations") == 2


def test_run_again_after_a_cancelled_run_keeps_the_done_solve(rig: Rig) -> None:
    version = rig.version()
    first = rig.run(version)
    assert first.state is RunState.SUCCEEDED
    # A run the person cancelled after its solve: the version has its solve and no result.
    with rig.engine.begin() as connection:
        connection.execute(
            text("UPDATE runs SET state = 'cancelled' WHERE id = :id"), {"id": first.id}
        )
        connection.execute(text("DELETE FROM pricing_version_simulations"))

    again = rig.run(version)

    assert again.state is RunState.SUCCEEDED
    assert again.steps[0].state is StepState.KEPT
    assert again.steps[1].state is StepState.KEPT
    assert set(rig.links(version)) == {"model_prices", "flat"}


def test_deleting_a_version_removes_its_solve_and_links_and_the_collection_frees_the_rest(
    rig: Rig,
) -> None:
    first, second = rig.version(), rig.version(flat_price_per_ride_chf=2.5)
    rig.run(first)
    rig.run(second)

    rig.pricing.delete(first)

    assert rig.count("solves") == 1
    assert rig.links(first) == {}
    assert rig.count("pricing_version_simulations") == 2
    rig.collect.execute()
    # The flat simulation only the first version used goes; the shared solve and the shared
    # model-price simulation stay with the second version.
    assert rig.count("simulations") == 2
    assert len([row for row in rig.rows("artifacts") if row[1] == "pricing_model"]) == 1

    rig.pricing.delete(second)
    rig.collect.execute()

    assert rig.count("solves") == 0
    assert rig.count("solve_rows") == 0
    assert rig.count("solve_ods") == 0
    assert rig.count("simulations") == 0
    assert rig.count("simulation_choices") == 0
    assert [row for row in rig.rows("artifacts") if row[1] == "pricing_model"] == []


def test_a_re_simulation_adds_rows_and_keeps_the_old_ones(rig: Rig) -> None:
    version = rig.version()
    rig.run(version)
    old_links = rig.simulations.links_of(version)
    old_simulations = rig.rows("simulations")
    counts = {table: rig.count(table) for table in ("solves", "solve_rows", "solve_ods")}
    model_artifacts = [row for row in rig.rows("artifacts") if row[1] == "pricing_model"]
    rig.settings.set_pricing_model(
        {"simulation_rule": {"version": 2, "price_weight": 0.6, "time_weight": 0.4}}
    )
    # The solver is not needed: a simulation reads the stored solve.
    rig.settings.set_component("solver", "unavailable", "No licence.")

    queued = rig.simulate_version.execute(version)
    assert rig.process.execute() is True
    run = rig.stored(queued.id)

    assert run.state is RunState.SUCCEEDED
    assert [(item.step, item.state) for item in run.steps] == [
        (StepName.TRAVELLER_SIMULATION, StepState.DONE)
    ]
    links = rig.simulations.linked_of(version)
    assert [(item.price_scheme, item.rule_version) for item in links] == [
        ("flat", 1),
        ("flat", 2),
        ("model_prices", 1),
        ("model_prices", 2),
    ]
    assert [item for item in rig.simulations.links_of(version) if item.rule_version == 1] == (
        old_links
    )
    assert all(row in rig.rows("simulations") for row in old_simulations)
    assert rig.count("simulations") == 4
    assert rig.count("pricing_version_simulations") == 4
    assert all(
        item.rule_parameters == {"price_weight": 0.6, "time_weight": 0.4}
        for item in links
        if item.rule_version == 2
    )
    assert {table: rig.count(table) for table in counts} == counts
    assert [row for row in rig.rows("artifacts") if row[1] == "pricing_model"] == model_artifacts
    with pytest.raises(SimulationCurrent):
        rig.simulate_version.execute(version)
    state = rig.pricing.list_for(INSTANCE_VERSION)[0].state
    assert state == "result"
    rig.collect.execute()
    assert rig.count("simulations") == 4
