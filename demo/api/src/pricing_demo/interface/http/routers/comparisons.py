from typing import Annotated, Any

from fastapi import APIRouter, Query

from pricing_demo.application.use_cases.compare_pricing_versions import ComparePricingVersions
from pricing_demo.interface.http.schemas import ComparisonResponse, ProblemDetails

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


def build_comparisons_router(compare: ComparePricingVersions) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["comparisons"])

    @router.get(
        "/comparisons",
        operation_id="comparePricingVersions",
        summary="Two to four finished pricing versions of one instance version, side by side",
        response_model=ComparisonResponse,
        responses={
            404: _problem("`pricing_version_not_found`"),
            409: _problem(
                "`different_instances`: the versions belong to different instance versions, or "
                "`no_result`: a version has no result"
            ),
            422: _problem(
                "`version_count_out_of_range`: fewer than two or more than four versions, or "
                "the request is not valid"
            ),
            500: _problem("Unexpected error"),
        },
    )
    def compare_route(
        pricing_versions: Annotated[
            str, Query(description="Two to four pricing version ids, separated by commas.")
        ],
        period: Annotated[
            str | None,
            Query(description="The period's id; the versions' first period when absent."),
        ] = None,
    ) -> ComparisonResponse:
        ids = [item.strip() for item in pricing_versions.split(",") if item.strip()]
        return ComparisonResponse.from_domain(compare.execute(ids, period))

    return router
