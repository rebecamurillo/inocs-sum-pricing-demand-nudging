"""The composition root: adapters, then use cases, then routers, then the application.

A new feature adds its lines here and its router module; `create_app` does not change.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from sqlalchemy import Engine

from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.create_city_instance import CreateCityInstance
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_city_datasets import ListCityDatasets
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
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
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.metadata import metadata
from pricing_demo.infrastructure.persistence.package_fingerprints import (
    PostgresPackageFingerprints,
)
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from pricing_demo.infrastructure.persistence.truncate import truncate_all
from pricing_demo.interface.http.app import Lifespan, create_app
from pricing_demo.interface.http.routers.city_datasets import build_city_datasets_router
from pricing_demo.interface.http.routers.city_instances import build_city_instances_router
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router


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

    return create_app(
        api_version=api_version,
        routers=[
            build_system_status_router(get_system_status),
            build_city_datasets_router(ListCityDatasets(datasets)),
            build_city_instances_router(
                CreateCityInstance(instances, datasets, PostgresPackageFingerprints(engine), clock),
                ListCityInstances(instances),
                CreateInstanceVersion(instances, datasets, clock),
                GetInstanceVersion(instances, datasets),
                UpdateInstanceVersion(instances, datasets),
                DeleteInstanceVersion(instances),
            ),
            build_runs_router(
                ListRuns(run_repository, clock),
                GetRun(run_repository, clock),
                GetRunLog(run_repository),
                CancelRun(run_repository, clock),
            ),
        ],
        test_control=test_control,
        lifespan=_dispose_on_shutdown(engine),
    )
