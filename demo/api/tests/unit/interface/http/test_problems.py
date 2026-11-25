import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import ComponentName, IncompleteSystemStatus, SystemStatus
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.interface.http.app import create_app
from tests.unit.interface.http.conftest import API_VERSION, AppFactory, Faked

PROBLEM_JSON = "application/problem+json"


class RuleBroken(DomainError):
    pass


class FailingUseCase(GetSystemStatus):
    def __init__(self, error: Exception) -> None:
        super().__init__([FakeProbe(name) for name in ComponentName])
        self._error = error

    def execute(self) -> SystemStatus:
        raise self._error


def client_raising(error: HTTPException) -> TestClient:
    router = APIRouter()

    @router.get("/api/v1/raises")
    def raises() -> None:
        raise error

    return TestClient(create_app(api_version=API_VERSION, routers=[router]))


def test_a_mapped_domain_error_is_a_problem_with_its_message(client_for: AppFactory) -> None:
    response = client_for(
        FailingUseCase(ComponentNotControllable("The storage is not faked."))
    ).get("/api/v1/system-status")

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": "https://sum-project.eu/problems/component-not-controllable",
        "title": "The component cannot be controlled",
        "status": 409,
        "detail": "The storage is not faked.",
        "code": "component_not_controllable",
    }


def test_a_domain_error_without_a_mapping_is_a_server_fault(client_for: AppFactory) -> None:
    response = client_for(FailingUseCase(RuleBroken("/srv/secret/path is in use."))).get(
        "/api/v1/system-status"
    )

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "internal_error"
    assert "secret" not in response.text


def test_a_mapped_error_that_is_an_internal_breach_is_a_server_fault(
    client_for: AppFactory,
) -> None:
    response = client_for(FailingUseCase(IncompleteSystemStatus("A component is missing."))).get(
        "/api/v1/system-status"
    )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "missing" not in response.text


def test_an_unexpected_error_is_a_problem_without_its_message(client_for: AppFactory) -> None:
    response = client_for(FailingUseCase(RuntimeError("/srv/secret/path failed"))).get(
        "/api/v1/system-status"
    )

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "internal_error"
    assert "secret" not in response.text
    assert "Traceback" not in response.text


def test_an_invalid_body_lists_the_fields_that_failed(faked: Faked) -> None:
    response = faked.client.put("/api/test-control/components/solver", json={"available": "maybe"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["errors"] == [
        {
            "field": "available",
            "message": "Input should be a valid boolean, unable to interpret input",
        }
    ]


def test_a_missing_body_names_the_body_as_the_field(faked: Faked) -> None:
    response = faked.client.put("/api/test-control/components/solver")

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "body"


def test_an_unknown_path_is_a_problem(faked: Faked) -> None:
    response = faked.client.get("/api/v1/nothing")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "not_found"
    assert response.json()["detail"] == "GET /api/v1/nothing matches no resource."


def test_a_wrong_method_is_a_problem_that_keeps_the_allow_header(faked: Faked) -> None:
    response = faked.client.post("/api/v1/system-status")

    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_a_body_that_cannot_be_read_is_a_problem(faked: Faked) -> None:
    response = faked.client.put(
        "/api/test-control/components/solver",
        content=b"\xff\xfe\x00",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["status"] == 400
    assert body["code"] == "bad_request"
    assert "detail" in body
    assert "errors" not in body


@pytest.mark.parametrize(
    ("status", "code", "title"),
    [
        (401, "unauthorized", "Unauthorized"),
        (403, "forbidden", "Forbidden"),
        (429, "too_many_requests", "Too Many Requests"),
    ],
)
def test_any_other_http_error_is_a_problem(status: int, code: str, title: str) -> None:
    client = client_raising(HTTPException(status, detail="Not for you.", headers={"X-Why": "why"}))

    response = client.get("/api/v1/raises")

    assert response.status_code == status
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["x-why"] == "why"
    assert response.json() == {
        "type": f"https://sum-project.eu/problems/{code.replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": "Not for you.",
        "code": code,
    }


def test_an_http_error_that_is_a_server_fault_keeps_its_status_and_hides_its_message() -> None:
    client = client_raising(HTTPException(503, detail="/srv/secret/path is down."))

    response = client.get("/api/v1/raises")

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "service_unavailable"
    assert "secret" not in response.text
