from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi

from pricing_demo.interface.http.problems import PROBLEM_MEDIA_TYPE, register_problem_handlers
from pricing_demo.interface.http.routers.health import build_health_router
from pricing_demo.interface.http.schemas import ProblemDetails

PROBLEM_REF = "#/components/schemas/ProblemDetails"

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    *,
    api_version: str,
    routers: Sequence[APIRouter],
    test_control: APIRouter | None = None,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Mount the routers it is given; a feature is added by passing its router, not here.

    `test_control` is the e2e seam's router: it is passed only when the application runs on
    fake adapters, and it is never part of the contract. `lifespan` runs around the server's
    life, to release what the adapters hold.
    """
    app = FastAPI(
        title="Dynamic pricing demonstrator API",
        version=api_version,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_problem_handlers(app)
    app.include_router(build_health_router())
    for router in routers:
        app.include_router(router)
    if test_control is not None:
        app.include_router(test_control)

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            _declare_problem_documents(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def _declare_problem_documents(schema: dict[str, Any]) -> None:
    """Every error is a problem document, so the contract says so.

    FastAPI documents each response model as application/json and adds a 422 of its own
    (HTTPValidationError) to every route that takes input; the API answers both as
    ProblemDetails in application/problem+json.
    """
    schemas: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    for path in schema["paths"].values():
        for operation in path.values():
            for status, response in operation["responses"].items():
                content = response.get("content", {})
                body = content.get("application/json", {})
                reference = body.get("schema", {}).get("$ref", "")
                if reference.endswith("/ProblemDetails"):
                    response["content"] = {PROBLEM_MEDIA_TYPE: body}
                elif status == "422" and reference.endswith("/HTTPValidationError"):
                    response["description"] = "The request is not valid"
                    response["content"] = {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": PROBLEM_REF}}}
                    _define_problem_details(schemas)
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)


def _define_problem_details(schemas: dict[str, Any]) -> None:
    if "ProblemDetails" in schemas:
        return
    definition = ProblemDetails.model_json_schema(ref_template="#/components/schemas/{model}")
    schemas.update(definition.pop("$defs", {}))
    schemas["ProblemDetails"] = definition
