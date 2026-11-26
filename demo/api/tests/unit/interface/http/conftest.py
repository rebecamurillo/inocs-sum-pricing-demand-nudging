from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe, fixed_probe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.interface.http.app import create_app
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router
from tests.support.runs import later

API_VERSION = "0.1.0"
SERVER_TIME = later(100)

AppFactory = Callable[[GetSystemStatus], TestClient]


class MemorySeam:
    """The test-control seam on in-memory settings, with the rules of the real one."""

    def __init__(self, settings: InMemoryFakeSettings) -> None:
        self.settings = settings

    def set_component(self, name: ComponentName, state: ComponentState, reason: str | None) -> None:
        if name not in PROBED_COMPONENTS:
            raise ComponentNotControllable(f"The {name} component is not faked.")
        ComponentStatus(name, state, reason)
        self.settings.set_component(name.value, state.value, reason)

    def reset(self) -> None:
        self.settings.write_defaults()


class Faked:
    """An app built from fakes. `worker_reports()` does what the worker does at each cycle:
    its fake probes read the settings the test-control routes wrote and report them."""

    def __init__(self) -> None:
        self.settings = InMemoryFakeSettings()
        self.reports = InMemoryComponentReports()
        self.clock = FixedClock(SERVER_TIME)
        self.reports.worker_heartbeats["w-1"] = SERVER_TIME
        self.use_case = GetSystemStatus(
            fixed_probe(ComponentStatus.ready(ComponentName.STORAGE)), self.reports, self.clock
        )
        self._report = ReportComponents(
            [FakeProbe(name, self.settings) for name in PROBED_COMPONENTS],
            self.reports,
            "w-1",
            self.clock,
        )
        self.report_cycle()
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[build_system_status_router(self.use_case)],
                test_control=build_test_control_router(MemorySeam(self.settings)),
            ),
            raise_server_exceptions=False,
        )

    def report_cycle(self) -> None:
        self._report.execute()


@pytest.fixture
def faked() -> Faked:
    return Faked()


@pytest.fixture
def client_for() -> AppFactory:
    """A client for an app whose use case is the one given."""

    def build(use_case: GetSystemStatus) -> TestClient:
        return TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[build_system_status_router(use_case)],
            ),
            raise_server_exceptions=False,
        )

    return build


class RunsApp:
    """An app with the run routes on an in-memory repository and a fixed clock."""

    def __init__(self) -> None:
        self.repository = InMemoryRunRepository()
        self.clock = FixedClock(SERVER_TIME)
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[
                    build_runs_router(
                        ListRuns(self.repository, self.clock),
                        GetRun(self.repository, self.clock),
                        GetRunLog(self.repository),
                        CancelRun(self.repository, self.clock),
                    )
                ],
            ),
            raise_server_exceptions=False,
        )


@pytest.fixture
def runs_app() -> RunsApp:
    return RunsApp()
