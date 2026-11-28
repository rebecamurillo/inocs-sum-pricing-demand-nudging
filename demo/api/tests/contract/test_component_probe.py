"""The ComponentProbe port: one suite, run against every implementation.

Each implementation provides two set-ups, the component working and the component made
unavailable, and the same assertions hold for the fake and the real adapters. The fake and the
cases that need no outside service always run; the others run under the marker of what they
need: `integration` for the throwaway PostgreSQL, `live` for the package, the solver and a
running OpenTripPlanner. The real package has no unavailable set-up: it cannot be uninstalled
for the length of a test.
"""

import socket
import time
from collections.abc import Callable

import pytest

from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.domain.system_status import ComponentName, ComponentState, ComponentStatus
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe

ANSWER_WITHIN_S = 5.0
UNREACHABLE_DATABASE = "postgresql+psycopg://user:secret@127.0.0.1:1/missing"

SetUp = Callable[[pytest.FixtureRequest], ComponentProbe]


def closed_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def fake_working(_: pytest.FixtureRequest) -> ComponentProbe:
    return FakeProbe(ComponentName.TRIP_PLANNER, InMemoryFakeSettings())


def fake_unavailable(_: pytest.FixtureRequest) -> ComponentProbe:
    settings = InMemoryFakeSettings()
    settings.set_component("solver", "unavailable", "No Gurobi licence was found.")
    return FakeProbe(ComponentName.SOLVER, settings)


def fake_limited(_: pytest.FixtureRequest) -> ComponentProbe:
    settings = InMemoryFakeSettings()
    settings.set_component("solver", "limited", "Size-limited Gurobi licence.")
    return FakeProbe(ComponentName.SOLVER, settings)


def storage_working(request: pytest.FixtureRequest) -> ComponentProbe:
    return StorageProbe(request.getfixturevalue("migrated_database"))


def storage_unavailable(_: pytest.FixtureRequest) -> ComponentProbe:
    return StorageProbe(create_db_engine(UNREACHABLE_DATABASE))


def package_working(_: pytest.FixtureRequest) -> ComponentProbe:
    return PackageProbe()


def solver_working(_: pytest.FixtureRequest) -> ComponentProbe:
    return SolverProbe()


def solver_unavailable(request: pytest.FixtureRequest) -> ComponentProbe:
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    monkeypatch.setenv("GRB_LICENSE_FILE", "/nonexistent/gurobi.lic")
    return SolverProbe()


def trip_planner_working(_: pytest.FixtureRequest) -> ComponentProbe:
    return OtpProbe(Settings().otp_url)


def trip_planner_unavailable(_: pytest.FixtureRequest) -> ComponentProbe:
    return OtpProbe(f"http://127.0.0.1:{closed_local_port()}/otp/gtfs/v1")


def case(name: str, set_up: SetUp, *marks: pytest.MarkDecorator) -> object:
    return pytest.param(set_up, id=name, marks=marks)


integration = pytest.mark.integration
live = pytest.mark.live

WORKING = [
    case("fake", fake_working),
    case("storage", storage_working, integration),
    case("package", package_working, live),
    case("solver", solver_working, live),
    case("trip-planner", trip_planner_working, live),
]
UNAVAILABLE = [
    case("fake", fake_unavailable),
    case("storage", storage_unavailable),
    case("solver", solver_unavailable, live),
    case("trip-planner", trip_planner_unavailable),
]


LIMITED = [case("fake", fake_limited)]


@pytest.fixture(params=WORKING)
def working_probe(request: pytest.FixtureRequest) -> ComponentProbe:
    set_up: SetUp = request.param
    return set_up(request)


@pytest.fixture(params=UNAVAILABLE)
def unavailable_probe(request: pytest.FixtureRequest) -> ComponentProbe:
    set_up: SetUp = request.param
    return set_up(request)


@pytest.fixture(params=LIMITED)
def limited_probe(request: pytest.FixtureRequest) -> ComponentProbe:
    set_up: SetUp = request.param
    return set_up(request)


@pytest.fixture(params=[*WORKING, *UNAVAILABLE, *LIMITED])
def probe(request: pytest.FixtureRequest) -> ComponentProbe:
    set_up: SetUp = request.param
    return set_up(request)


def test_checking_reports_the_probes_own_component_and_never_raises(probe: ComponentProbe) -> None:
    status = probe.check()

    assert isinstance(status, ComponentStatus)
    assert status.name == probe.component


def test_a_working_component_is_available_without_a_reason(working_probe: ComponentProbe) -> None:
    status = working_probe.check()

    assert (status.state, status.reason) == (ComponentState.AVAILABLE, None)


def test_an_unavailable_component_says_why(unavailable_probe: ComponentProbe) -> None:
    status = unavailable_probe.check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason


def test_a_limited_solver_says_why(limited_probe: ComponentProbe) -> None:
    status = limited_probe.check()

    assert limited_probe.component is ComponentName.SOLVER
    assert status.state is ComponentState.LIMITED
    assert status.reason


def test_a_probe_answers_within_a_bound(probe: ComponentProbe) -> None:
    started = time.monotonic()

    probe.check()

    assert time.monotonic() - started < ANSWER_WITHIN_S


def test_a_probe_can_be_checked_again(probe: ComponentProbe) -> None:
    first = probe.check()
    second = probe.check()

    assert (second.name, second.state) == (first.name, first.state)
