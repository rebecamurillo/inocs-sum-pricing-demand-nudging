"""The composition root: adapters, then use cases, then routers, then the application.

A new feature adds its lines here and its router module; `create_app` does not change.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from sqlalchemy import Engine

from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.infrastructure.clock import SystemClock
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.fakes.component_probe import FakeControl
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.metadata import metadata
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from pricing_demo.infrastructure.persistence.truncate import truncate_all
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe
from pricing_demo.interface.http.app import Lifespan, create_app
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router


class _E2ESeam:
    """What the e2e suite changes: the fakes' answers, and the stored data on reset."""

    def __init__(self, control: FakeControl, engine: Engine) -> None:
        self._control = control
        self._engine = engine

    def set_component(self, name: ComponentName, available: bool, reason: str | None) -> None:
        self._control.set_component(name, available, reason)

    def reset(self) -> None:
        self._control.reset()
        truncate_all(self._engine, metadata)


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

    storage = StorageProbe(engine)
    probes: list[ComponentProbe]
    test_control = None
    if settings.adapters == "fake":
        control = FakeControl()
        probes = [
            storage,
            control.probe(ComponentName.PRICING_MODEL),
            control.probe(ComponentName.SOLVER),
            control.probe(ComponentName.TRIP_PLANNER),
        ]
        test_control = build_test_control_router(_E2ESeam(control, engine))
    else:
        probes = [storage, PackageProbe(), SolverProbe(), OtpProbe(settings.otp_url)]

    get_system_status = GetSystemStatus(probes)
    run_repository = PostgresRunRepository(engine)
    clock = SystemClock()

    return create_app(
        api_version=api_version,
        routers=[
            build_system_status_router(get_system_status, api_version),
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
