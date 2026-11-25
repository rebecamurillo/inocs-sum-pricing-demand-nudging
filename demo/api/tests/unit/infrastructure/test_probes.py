import httpx
import pytest

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

    assert probe.check().available


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

    assert not status.available
    assert status.reason == f"{OTP_URL} answered HTTP 503."


def test_the_trip_planner_reports_a_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    status = otp_probe(httpx.MockTransport(handler)).check()

    assert not status.available
    assert status.reason == f"No answer from {OTP_URL} within 2 s."


def test_the_trip_planner_reports_a_refused_connection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    status = otp_probe(httpx.MockTransport(handler)).check()

    assert not status.available
    assert status.reason == f"{OTP_URL} is not reachable: Connection refused"


def test_the_storage_is_unavailable_when_the_database_does_not_answer() -> None:
    engine = create_db_engine("postgresql+psycopg://user:secret@127.0.0.1:1/missing")

    status = StorageProbe(engine).check()

    assert not status.available
    assert status.reason is not None
    assert status.reason.startswith("The database does not answer: ")
    assert "secret" not in status.reason


def test_the_solver_reason_starts_with_the_probes_own_words_and_adds_gurobis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRB_LICENSE_FILE", "/nonexistent/gurobi.lic")

    status = SolverProbe().check()

    assert not status.available
    assert status.reason is not None
    assert status.reason.startswith("Gurobi did not start: ")
    assert status.reason.removeprefix("Gurobi did not start: ").strip()


def test_the_package_is_available_when_it_imports() -> None:
    assert PackageProbe().check().available
