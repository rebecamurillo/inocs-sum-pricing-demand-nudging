from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pricing_demo.export_openapi import render_openapi
from pricing_demo.interface.http.app import create_app

PROBLEM_JSON = "application/problem+json"
THING = "/api/v1/things/{thing_id}"


class Thing(BaseModel):
    name: str
    size: int


def things_router() -> APIRouter:
    """A feature the skeleton does not have: a path parameter and a body."""
    router = APIRouter(prefix="/api/v1/things", tags=["things"])

    @router.put("/{thing_id}", response_model=Thing)
    def replace_thing(thing_id: int, thing: Thing) -> Thing:
        return thing

    return router


def app_with(*routers: APIRouter) -> FastAPI:
    return create_app(api_version="0.0.0", routers=routers)


def references(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from references(value)
    elif isinstance(node, list):
        for item in node:
            yield from references(item)


def test_a_feature_is_mounted_by_passing_its_router() -> None:
    client = TestClient(app_with(things_router()))

    response = client.put("/api/v1/things/3", json={"name": "a", "size": 1})

    assert response.status_code == 200
    assert response.json() == {"name": "a", "size": 1}


def test_the_test_control_routes_are_mounted_only_when_given() -> None:
    control = APIRouter(prefix="/api/test-control")

    @control.post("/reset", status_code=204)
    def reset() -> None:
        return None

    without = TestClient(create_app(api_version="0.0.0", routers=[]))
    with_control = TestClient(create_app(api_version="0.0.0", routers=[], test_control=control))

    assert without.post("/api/test-control/reset").status_code == 404
    assert with_control.post("/api/test-control/reset").status_code == 204


def test_liveness_answers_without_any_feature_and_stays_out_of_the_contract() -> None:
    app = create_app(api_version="0.0.0", routers=[])

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "/api/health" not in app.openapi()["paths"]


def test_the_422_of_a_route_with_input_is_a_problem_document_in_the_contract() -> None:
    document = app_with(things_router()).openapi()

    response = document["paths"][THING]["put"]["responses"]["422"]

    assert response["content"] == {
        PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
    }


def test_the_contract_holds_no_framework_validation_schema_and_no_dangling_reference() -> None:
    document = app_with(things_router()).openapi()

    schemas = document["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert {"ProblemDetails", "FieldError", "Thing"} <= set(schemas)
    assert [
        reference
        for reference in references(document)
        if reference.removeprefix("#/components/schemas/") not in schemas
    ] == []


def test_the_422_that_is_answered_matches_the_one_that_is_documented() -> None:
    client = TestClient(app_with(things_router()))

    response = client.put("/api/v1/things/not-a-number", json={"name": "a"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["code"] == "validation_failed"
    assert sorted(error["field"] for error in body["errors"]) == ["size", "thing_id"]


def test_the_exported_contract_of_the_application_holds_no_framework_validation_schema() -> None:
    assert "HTTPValidationError" not in render_openapi()
