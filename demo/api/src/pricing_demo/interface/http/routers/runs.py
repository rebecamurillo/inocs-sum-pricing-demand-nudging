from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse

from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.list_route_failures import ListRouteFailures
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.domain.runs import RunState
from pricing_demo.interface.http.schemas import (
    ProblemDetails,
    RouteFailureList,
    RouteFailureResource,
    RunList,
    RunResource,
)

Responses = dict[int | str, dict[str, Any]]

NOT_FOUND: Responses = {404: {"model": ProblemDetails, "description": "No run has this id"}}
UNEXPECTED: Responses = {500: {"model": ProblemDetails, "description": "Unexpected error"}}


def build_runs_router(
    list_runs: ListRuns,
    get_run: GetRun,
    get_run_log: GetRunLog,
    cancel_run: CancelRun,
    list_route_failures: ListRouteFailures,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["runs"])

    @router.get(
        "/runs",
        operation_id="listRuns",
        summary="The stored runs, oldest queue time first",
        response_model=RunList,
        responses=UNEXPECTED,
    )
    def read_runs(
        state: Annotated[
            str | None,
            Query(description="Comma-separated run states to keep, such as queued,running."),
        ] = None,
    ) -> RunList:
        states = list(RunState)
        if state:
            try:
                states = [RunState(item) for item in state.split(",")]
            except ValueError as error:
                raise RequestValidationError(
                    [
                        {
                            "type": "enum",
                            "loc": ("query", "state"),
                            "msg": f"must be a comma-separated list of {', '.join(RunState)}",
                            "input": state,
                        }
                    ]
                ) from error
        return RunList(items=[RunResource.from_view(view) for view in list_runs.execute(states)])

    @router.get(
        "/runs/{run_id}",
        operation_id="getRun",
        summary="One run, with its steps and the state of its runner",
        response_model=RunResource,
        responses={**NOT_FOUND, **UNEXPECTED},
    )
    def read_run(run_id: str) -> RunResource:
        return RunResource.from_view(get_run.execute(run_id))

    @router.get(
        "/runs/{run_id}/log",
        operation_id="getRunLog",
        summary="The log excerpts of the run's steps, in step order",
        response_class=PlainTextResponse,
        responses={
            200: {"content": {"text/plain": {"schema": {"type": "string"}}}},
            **NOT_FOUND,
            **UNEXPECTED,
        },
    )
    def read_run_log(run_id: str) -> PlainTextResponse:
        return PlainTextResponse(get_run_log.execute(run_id))

    @router.get(
        "/runs/{run_id}/route-failures",
        operation_id="listRouteFailures",
        summary="The trip-planner queries that failed during the run's routes step",
        response_model=RouteFailureList,
        responses={**NOT_FOUND, **UNEXPECTED},
    )
    def read_route_failures(run_id: str) -> RouteFailureList:
        return RouteFailureList(
            items=[
                RouteFailureResource.from_domain(failure, period)
                for failure, period in list_route_failures.execute(run_id)
            ]
        )

    @router.put(
        "/runs/{run_id}/cancellation",
        operation_id="cancelRun",
        summary="Cancel a run: at once when queued, at its next safe point when running",
        response_model=RunResource,
        responses={
            202: {
                "model": RunResource,
                "description": "A running run was asked to stop",
                "headers": {
                    "Location": {
                        "description": "The run, which reports when it stops",
                        "schema": {"type": "string"},
                    }
                },
            },
            404: NOT_FOUND[404],
            409: {"model": ProblemDetails, "description": "The run has already finished"},
            **UNEXPECTED,
        },
    )
    def cancel(run_id: str, response: Response) -> RunResource:
        result = cancel_run.execute(run_id)
        if result.cancelled_at_once:
            response.status_code = 200
        else:
            response.status_code = 202
            response.headers["Location"] = f"/api/v1/runs/{result.view.run.id}"
        return RunResource.from_view(result.view)

    return router
