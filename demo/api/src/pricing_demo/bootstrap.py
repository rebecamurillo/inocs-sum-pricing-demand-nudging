"""The composition root: adapters, then use cases, then routers, then the application.

A new feature adds its lines here and its router module; `create_app` does not change.
"""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from sqlalchemy import Engine

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.compare_pricing_versions import ComparePricingVersions
from pricing_demo.application.use_cases.create_city_instance import CreateCityInstance
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.create_pricing_version import CreatePricingVersion
from pricing_demo.application.use_cases.delete_city_instance import DeleteCityInstance
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.delete_pricing_version import DeletePricingVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.get_pricing_result import GetPricingResult
from pricing_demo.application.use_cases.get_pricing_version import GetPricingVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_showcase import GetShowcase
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_city_datasets import ListCityDatasets
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.list_hub_pair_results import ListHubPairResults
from pricing_demo.application.use_cases.list_hub_pairs import ListHubPairs
from pricing_demo.application.use_cases.list_hub_results import ListHubResults
from pricing_demo.application.use_cases.list_hubs import ListHubs
from pricing_demo.application.use_cases.list_place_names import ListPlaceNames
from pricing_demo.application.use_cases.list_pricing_version_simulations import (
    ListPricingVersionSimulations,
)
from pricing_demo.application.use_cases.list_pricing_versions import ListPricingVersions
from pricing_demo.application.use_cases.list_route_failures import ListRouteFailures
from pricing_demo.application.use_cases.list_route_options import ListRouteOptions
from pricing_demo.application.use_cases.list_route_pairs import ListRoutePairs
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.application.use_cases.list_stations import ListStations
from pricing_demo.application.use_cases.mark_showcase import MarkShowcase
from pricing_demo.application.use_cases.quote_trip import QuoteTrip
from pricing_demo.application.use_cases.run_pricing_version import RunPricingVersion
from pricing_demo.application.use_cases.simulate_pricing_version import SimulatePricingVersion
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.application.use_cases.update_pricing_version import UpdatePricingVersion
from pricing_demo.domain.city_datasets import GENEVA_SLUG, dataset_id_for
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.clock import SystemClock
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.ids import UuidV7Source
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.build_sources import PostgresBuildSources
from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.metadata import metadata
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
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from pricing_demo.infrastructure.persistence.trip_reads import PostgresTripReads
from pricing_demo.infrastructure.persistence.truncate import truncate_all
from pricing_demo.interface.http.app import Lifespan, create_app
from pricing_demo.interface.http.routers.city_datasets import build_city_datasets_router
from pricing_demo.interface.http.routers.city_instances import build_city_instances_router
from pricing_demo.interface.http.routers.comparisons import build_comparisons_router
from pricing_demo.interface.http.routers.place_names import build_place_names_router
from pricing_demo.interface.http.routers.pricing_versions import build_pricing_versions_router
from pricing_demo.interface.http.routers.route_options import build_route_options_router
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.showcase import build_showcase_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router
from pricing_demo.interface.http.routers.trip_quotes import build_trip_quotes_router


class _E2ESeam:
    """What the e2e suite changes: the fakes' settings, and the stored data on reset.

    The settings are a row of `fake_settings`: the worker's fake probes read it.
    """

    def __init__(
        self,
        fake_settings: PostgresFakeSettings,
        engine: Engine,
        datasets: PostgresCityDatasets,
        clock: Clock,
    ) -> None:
        self._fake_settings = fake_settings
        self._engine = engine
        self._datasets = datasets
        self._clock = clock

    def set_component(self, name: ComponentName, state: ComponentState, reason: str | None) -> None:
        if name not in PROBED_COMPONENTS:
            raise ComponentNotControllable(f"The {name} component is not faked.")
        ComponentStatus(name, state, reason)  # refuses an answer the domain refuses
        self._fake_settings.set_component(name.value, state.value, reason)

    def insert_city_dataset(self) -> str:
        now = self._clock.now()
        prefix = f"{GENEVA_SLUG}-{now.date().isoformat()}"
        dataset_id = dataset_id_for(
            GENEVA_SLUG, now.date(), self._datasets.ids_starting_with(prefix)
        )
        self._datasets.add(fake_city_dataset(dataset_id, now))
        return dataset_id

    def set_pricing_model(self, settings: Mapping[str, object]) -> None:
        self._fake_settings.set_pricing_model(settings)

    def release_run(self, run_id: str) -> None:
        self._fake_settings.release_run(run_id)

    def reset(self) -> None:
        truncate_all(self._engine, metadata)
        self._fake_settings.write_defaults()


def _dispose_on_shutdown(engine: Engine) -> Lifespan:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    return lifespan


def create_application(settings: Settings) -> FastAPI:
    """Choose the adapters and wire them. Nothing here connects to anything."""
    api_version = version("pricing_demo")
    engine = create_db_engine(settings.database_url)

    clock = SystemClock()
    # The API probes storage only; the worker probes the rest and reports it.
    datasets = PostgresCityDatasets(engine)
    get_system_status = GetSystemStatus(
        StorageProbe(engine), PostgresComponentReports(engine), datasets, clock
    )
    test_control = None
    if settings.adapters == "fake":
        test_control = build_test_control_router(
            _E2ESeam(PostgresFakeSettings(engine), engine, datasets, clock)
        )
    run_repository = PostgresRunRepository(engine)
    instances = PostgresCityInstances(engine)
    builds = PostgresBuilds(engine)
    pricing_versions = PostgresPricingVersions(engine)
    durations = StepDurations(pricing_versions, instances)
    simulations = PostgresSimulations(engine)
    artifacts = PostgresArtifacts(engine)
    read_model = PostgresReadModel(engine)
    route_failures = PostgresRouteFailures(engine)
    built = BuiltCounts(artifacts, read_model, route_failures)
    planning = BuildPlanning(
        instances,
        datasets,
        artifacts,
        PostgresBuildSources(engine),
        builds,
        get_system_status.execute,
    )

    fingerprints = PostgresPackageFingerprints(engine)
    solves = PostgresSolves(engine)
    lookup = ResultLookup(pricing_versions, solves, simulations)
    showcase = PostgresShowcase(engine)
    trips = PostgresTripReads(engine)
    get_result = GetPricingResult(
        lookup,
        simulations,
        instances,
        datasets,
        artifacts,
        fingerprints,
        get_system_status.execute,
    )
    return create_app(
        api_version=api_version,
        routers=[
            build_system_status_router(get_system_status),
            build_city_datasets_router(ListCityDatasets(datasets)),
            build_city_instances_router(
                CreateCityInstance(
                    instances,
                    datasets,
                    fingerprints,
                    clock,
                    planning,
                    built,
                ),
                ListCityInstances(instances, builds, pricing_versions),
                CreateInstanceVersion(instances, datasets, clock, planning, built, fingerprints),
                GetInstanceVersion(instances, datasets, planning, built, fingerprints),
                UpdateInstanceVersion(instances, datasets, planning, built, fingerprints),
                DeleteInstanceVersion(builds),
                DeleteCityInstance(builds),
                BuildInstanceVersion(instances, datasets, builds, planning, UuidV7Source(), clock),
                GetRun(run_repository, clock, durations),
                ListStations(instances, artifacts, read_model),
                ListHubs(instances, artifacts, read_model),
                ListHubPairs(instances, artifacts, read_model),
                ListRoutePairs(instances, artifacts, read_model),
            ),
            build_pricing_versions_router(
                CreatePricingVersion(instances, builds, pricing_versions, clock),
                ListPricingVersions(instances, pricing_versions),
                GetPricingVersion(instances, pricing_versions),
                UpdatePricingVersion(instances, pricing_versions),
                DeletePricingVersion(pricing_versions),
                RunPricingVersion(
                    pricing_versions,
                    get_system_status.execute,
                    UuidV7Source(),
                    clock,
                ),
                GetRun(run_repository, clock, durations),
                SimulatePricingVersion(
                    pricing_versions,
                    simulations,
                    get_system_status.execute,
                    UuidV7Source(),
                    clock,
                ),
                ListPricingVersionSimulations(
                    pricing_versions, simulations, get_system_status.execute
                ),
                get_result,
                ListHubPairResults(lookup, solves, artifacts, read_model),
                ListHubResults(lookup, artifacts, read_model),
            ),
            build_comparisons_router(
                ComparePricingVersions(pricing_versions, get_result, solves, instances)
            ),
            build_trip_quotes_router(QuoteTrip(lookup, pricing_versions, solves, trips)),
            build_place_names_router(ListPlaceNames(instances, trips)),
            build_route_options_router(ListRouteOptions(instances, trips)),
            build_showcase_router(
                MarkShowcase(lookup, showcase, clock),
                GetShowcase(
                    showcase,
                    lookup,
                    instances,
                    simulations,
                    datasets,
                    artifacts,
                    read_model,
                    solves,
                    get_system_status.execute,
                ),
            ),
            build_runs_router(
                ListRuns(run_repository, clock, durations),
                GetRun(run_repository, clock, durations),
                GetRunLog(run_repository),
                CancelRun(run_repository, clock, durations),
                ListRouteFailures(run_repository, route_failures),
            ),
        ],
        test_control=test_control,
        lifespan=_dispose_on_shutdown(engine),
    )
