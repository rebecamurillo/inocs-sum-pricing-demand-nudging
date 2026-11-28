from typing import Annotated, Any

from fastapi import APIRouter, Query

from pricing_demo.application.use_cases.list_route_options import ListRouteOptions
from pricing_demo.interface.http.schemas import ProblemDetails, RouteOptionList


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


def build_route_options_router(list_route_options: ListRouteOptions) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["route-options"])

    @router.get(
        "/route-options",
        operation_id="listRouteOptions",
        summary="The stored options of one hub pair, with legs and geometry",
        description=(
            "Each leg says whether its line follows a street path, a timetable shape or a "
            "straight line."
        ),
        response_model=RouteOptionList,
        responses={
            404: _problem("`instance_version_not_found`, or `hub_pair_not_found`"),
            422: _problem("`unknown_period`, or the request is not valid"),
            500: _problem("Unexpected error"),
        },
    )
    def route_options_route(
        instance_version: Annotated[str, Query(description="The instance version's id.")],
        origin_hub: Annotated[str, Query(description="The origin hub's id.")],
        destination_hub: Annotated[str, Query(description="The destination hub's id.")],
        period: Annotated[
            str | None, Query(description="The period's key; checked against the version.")
        ] = None,
    ) -> RouteOptionList:
        return RouteOptionList.from_domain(
            list_route_options.execute(instance_version, period, origin_hub, destination_hub)
        )

    return router
