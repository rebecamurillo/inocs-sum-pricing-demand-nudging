from typing import Any

from fastapi import APIRouter

from pricing_demo.application.use_cases.get_showcase import GetShowcase
from pricing_demo.application.use_cases.mark_showcase import MarkShowcase
from pricing_demo.interface.http.schemas import ProblemDetails, ShowcaseRequest, ShowcaseResponse

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


UNEXPECTED: Responses = {500: _problem("Unexpected error")}


def build_showcase_router(mark: MarkShowcase, get: GetShowcase) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["showcase"])

    @router.put(
        "/showcase",
        operation_id="markShowcase",
        summary="Make a finished pricing version and period the showcase",
        response_model=ShowcaseResponse,
        responses={
            404: _problem("`pricing_version_not_found`"),
            409: _problem("`no_result`: the version has no result, or does not price the period"),
            **UNEXPECTED,
        },
    )
    def mark_route(request: ShowcaseRequest) -> ShowcaseResponse:
        mark.execute(request.pricing_version_id, request.period_id)
        return ShowcaseResponse.from_view(get.execute())

    @router.get(
        "/showcase",
        operation_id="getShowcase",
        summary="The showcased pricing version with what Home draws",
        response_model=ShowcaseResponse,
        responses={
            404: _problem(
                "`no_showcase` (none is marked) or `no_result` (the marked version has lost "
                "part of its result)"
            ),
            **UNEXPECTED,
        },
    )
    def get_route() -> ShowcaseResponse:
        return ShowcaseResponse.from_view(get.execute())

    return router
