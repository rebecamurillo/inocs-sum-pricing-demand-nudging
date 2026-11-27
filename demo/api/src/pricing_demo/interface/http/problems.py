import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus

import fastapi.exceptions
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pricing_demo.application.errors import (
    BikeStationFetchFailed,
    BusShapeMatchingFailed,
    ComponentNotControllable,
    GraphBuildFailed,
    GtfsCopyChanged,
    InvalidProbeSet,
    InvalidStreetExtract,
    InvalidTimetable,
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    PackageDefaultsMissing,
    StreetExtractNotFound,
    UnknownCityDataset,
    UnknownStartVersion,
    VersionNotBuilt,
)
from pricing_demo.domain.builds import (
    AlreadyBuilt,
    ComponentUnavailable,
    DraftChanged,
    RuleBroken,
    RunActive,
)
from pricing_demo.domain.city_datasets import DisjointAreas
from pricing_demo.domain.city_instances import (
    CityInstanceNameTaken,
    CityInstanceNotFound,
    DraftExists,
    InstanceVersionNotFound,
    InvalidInstanceName,
    PeriodNotFound,
    VersionSealed,
)
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.failure_codes import UnknownFailureCode
from pricing_demo.domain.runs import (
    InvalidRunTransition,
    InvalidStepTransition,
    RunAlreadyFinished,
    RunNotFound,
)
from pricing_demo.domain.system_status import IncompleteSystemStatus, InvalidComponentStatus
from pricing_demo.interface.http.schemas import (
    BlockingReasonResponse,
    FieldError,
    ProblemDetails,
    RuleResultResource,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://sum-project.eu/problems/"

logger = logging.getLogger(__name__)

# Starlette's HTTPException: FastAPI's own extends it, and the router raises it for a 404 or a
# 405. The interface imports only fastapi, which re-exports the class without declaring it.
StarletteHTTPException = fastapi.exceptions.StarletteHTTPException  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Problem:
    status: int
    code: str
    title: str


INTERNAL_ERROR = Problem(500, "internal_error", "The server failed to handle the request")

# The one place where a domain error type gets its status and code. An error type is mapped
# on its own, never through its parent: a type without an entry is a server fault (500), and
# a test fails until each error the domain and the application declare has an entry here.
DOMAIN_PROBLEMS: Mapping[type[DomainError], Problem] = {
    InvalidComponentStatus: Problem(
        422, "invalid_component_status", "The component status is not valid"
    ),
    ComponentNotControllable: Problem(
        409, "component_not_controllable", "The component cannot be controlled"
    ),
    RunNotFound: Problem(404, "run_not_found", "The run does not exist"),
    RunAlreadyFinished: Problem(409, "run_finished", "The run has already finished"),
    # No route lets a client ask for a transition the machine refuses: reaching one is a bug.
    InvalidRunTransition: INTERNAL_ERROR,
    InvalidStepTransition: INTERNAL_ERROR,
    IncompleteSystemStatus: INTERNAL_ERROR,
    InvalidProbeSet: INTERNAL_ERROR,
    # Raised by the worker's city data commands only; no route reaches them.
    BikeStationFetchFailed: INTERNAL_ERROR,
    StreetExtractNotFound: INTERNAL_ERROR,
    NoCityDataYet: INTERNAL_ERROR,
    InvalidTimetable: INTERNAL_ERROR,
    InvalidStreetExtract: INTERNAL_ERROR,
    GtfsCopyChanged: INTERNAL_ERROR,
    DisjointAreas: INTERNAL_ERROR,
    BusShapeMatchingFailed: INTERNAL_ERROR,
    UnknownCityDataset: Problem(422, "unknown_city_dataset", "The city data set does not exist"),
    UnknownStartVersion: Problem(
        422, "unknown_start_version", "The version to start from does not exist"
    ),
    InvalidInstanceName: Problem(
        422, "invalid_instance_name", "The name cannot make an identifier"
    ),
    CityInstanceNameTaken: Problem(409, "name_taken", "The name is already used"),
    DraftExists: Problem(409, "draft_exists", "The instance already has a draft"),
    VersionSealed: Problem(409, "version_sealed", "The version is saved and cannot change"),
    PackageDefaultsMissing: Problem(
        409, "package_defaults_missing", "The package defaults are not known yet"
    ),
    InstanceVersionNotFound: Problem(
        404, "instance_version_not_found", "The instance version does not exist"
    ),
    VersionNotBuilt: Problem(409, "version_not_built", "The version has no stored build"),
    PeriodNotFound: Problem(404, "period_not_found", "The version has no such period"),
    CityInstanceNotFound: Problem(
        404, "city_instance_not_found", "The city instance does not exist"
    ),
    OtherTimetableInGraphFolder: INTERNAL_ERROR,
    GraphBuildFailed: INTERNAL_ERROR,
    RuleBroken: Problem(409, "rule_broken", "The draft breaks a rule"),
    RunActive: Problem(409, "run_active", "The version has a queued or running run"),
    AlreadyBuilt: Problem(409, "already_built", "The version is already built"),
    ComponentUnavailable: Problem(
        503, "component_unavailable", "A component the build needs is not available"
    ),
    # Only after every retry of the use case found the draft edited again meanwhile.
    DraftChanged: INTERNAL_ERROR,
    # Raised by the fake pricing model when a test names a code the domain does not have; the
    # test-control request refuses such a code before it gets there.
    UnknownFailureCode: INTERNAL_ERROR,
}


def problem_response(
    problem: Problem,
    detail: str,
    errors: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
    draft_id: str | None = None,
    failures: list[RuleResultResource] | None = None,
    reasons: list[BlockingReasonResponse] | None = None,
    run_id: str | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        type=PROBLEM_TYPE_BASE + problem.code.replace("_", "-"),
        title=problem.title,
        status=problem.status,
        detail=detail,
        code=problem.code,
        errors=errors,
        draft_id=draft_id,
        failures=failures,
        reasons=reasons,
        run_id=run_id,
    )
    return JSONResponse(
        status_code=problem.status,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(headers) if headers else None,
    )


def _domain_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)
    problem = DOMAIN_PROBLEMS.get(type(error))
    # A mapped 503 is an answer to the client, not a fault: only the unmapped and the
    # explicitly internal errors are logged and hidden.
    if problem is None or problem is INTERNAL_ERROR:
        return _unexpected_error(request, error)
    return problem_response(
        problem,
        str(error),
        draft_id=error.draft_id if isinstance(error, DraftExists) else None,
        failures=[RuleResultResource.from_domain(item) for item in error.failures]
        if isinstance(error, RuleBroken)
        else None,
        reasons=[BlockingReasonResponse.from_domain(item) for item in error.reasons]
        if isinstance(error, ComponentUnavailable)
        else None,
        run_id=error.run_id if isinstance(error, RunActive) else None,
    )


def _validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    errors = [_field_error(item["loc"], item["msg"]) for item in error.errors()]
    return problem_response(
        Problem(422, "validation_failed", "The request is not valid"),
        f"{len(errors)} field(s) failed validation.",
        errors,
    )


def _field_error(location: tuple[str | int, ...], message: str) -> FieldError:
    # The first part of a location says where the value came from (body, query, path).
    parts = location[1:] or location
    return FieldError(field=".".join(str(part) for part in parts), message=message)


def _http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    status = error.status_code
    if status == HTTPStatus.INTERNAL_SERVER_ERROR:
        return _unexpected_error(request, error)
    if status == HTTPStatus.NOT_FOUND:
        return problem_response(
            Problem(404, "not_found", "The resource does not exist"),
            f"{request.method} {request.url.path} matches no resource.",
            headers=error.headers,
        )
    if status == HTTPStatus.METHOD_NOT_ALLOWED:
        return problem_response(
            Problem(405, "method_not_allowed", "The method is not allowed on this resource"),
            f"{request.method} is not allowed on {request.url.path}.",
            headers=error.headers,
        )
    phrase = _phrase(status)
    problem = Problem(status, re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_"), phrase)
    if status >= 500:
        _log(request, error)
        detail = "The server could not complete the request; it was logged on the server."
    else:
        detail = error.detail
    return problem_response(problem, detail, headers=error.headers)


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def _log(request: Request, error: Exception) -> None:
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=error)


def _unexpected_error(request: Request, error: Exception) -> JSONResponse:
    _log(request, error)
    return problem_response(
        INTERNAL_ERROR,
        "An unexpected error occurred; it was logged on the server.",
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
