import httpx
import pytest

from pricing_demo.domain.system_status import ComponentState
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.storage_probe import StorageProbe
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe

OTP_URL = "http://otp.test/otp/gtfs/v1"


def otp_probe(handler: httpx.MockTransport) -> OtpProbe:
    return OtpProbe(OTP_URL, transport=handler)


def test_the_trip_planner_is_available_when_it_answers() -> None:
    probe = otp_probe(httpx.MockTransport(lambda request: httpx.Response(200, json={})))

    assert probe.check().state is ComponentState.AVAILABLE


def test_the_trip_planner_asks_a_graphql_query() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    otp_probe(httpx.MockTransport(handler)).check()

    assert seen[0].method == "POST"
    assert str(seen[0].url) == OTP_URL
    assert b"query" in seen[0].content


def test_the_trip_planner_is_unavailable_on_an_error_status() -> None:
    status = otp_probe(httpx.MockTransport(lambda request: httpx.Response(503))).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == f"{OTP_URL} answered HTTP 503."


def test_the_trip_planner_reports_a_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    status = otp_probe(httpx.MockTransport(handler)).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == f"No answer from {OTP_URL} within 2 s."


def test_the_trip_planner_reports_a_refused_connection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    status = otp_probe(httpx.MockTransport(handler)).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == f"{OTP_URL} is not reachable: Connection refused"


def test_the_storage_is_unavailable_when_the_database_does_not_answer() -> None:
    engine = create_db_engine("postgresql+psycopg://user:secret@127.0.0.1:1/missing")

    status = StorageProbe(engine).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason is not None
    assert status.reason.startswith("The database does not answer: ")
    assert "secret" not in status.reason


def test_the_solver_is_not_available_without_a_licence_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRB_LICENSE_FILE", "/nonexistent/gurobi.lic")

    status = SolverProbe().check()

    assert status.state is not ComponentState.AVAILABLE
    assert status.reason


def test_the_package_is_available_when_it_imports() -> None:
    assert PackageProbe().check().state is ComponentState.AVAILABLE
