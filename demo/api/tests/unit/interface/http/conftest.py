from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import FakeControl, FakeProbe
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.interface.http.app import create_app
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router
from tests.support.runs import later

API_VERSION = "0.1.0"
SERVER_TIME = later(100)

AppFactory = Callable[[GetSystemStatus], TestClient]


class Faked:
    """An app built from fakes, with the control that sets what the fakes answer."""

    def __init__(self) -> None:
        self.control = FakeControl()
        self.use_case = GetSystemStatus(
            [
                FakeProbe(ComponentName.STORAGE),
                self.control.probe(ComponentName.PRICING_MODEL),
                self.control.probe(ComponentName.SOLVER),
                self.control.probe(ComponentName.TRIP_PLANNER),
            ]
        )
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[build_system_status_router(self.use_case, API_VERSION)],
                test_control=build_test_control_router(self.control),
            ),
            raise_server_exceptions=False,
        )


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
                routers=[build_system_status_router(use_case, API_VERSION)],
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
