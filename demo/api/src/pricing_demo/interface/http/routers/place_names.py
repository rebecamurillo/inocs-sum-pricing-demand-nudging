from typing import Annotated, Any

from fastapi import APIRouter, Query

from pricing_demo.application.use_cases.list_place_names import ListPlaceNames
from pricing_demo.interface.http.schemas import PlaceNameLine, PlaceNameList, ProblemDetails


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


def build_place_names_router(list_place_names: ListPlaceNames) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["place-names"])

    @router.get(
        "/place-names",
        operation_id="listPlaceNames",
        summary="The stop and bike-station names of an instance version that match a text",
        description=(
            "Case and accent do not matter. A parent station and its platforms are one line. "
            "A text of fewer than two characters matches nothing."
        ),
        response_model=PlaceNameList,
        responses={
            404: _problem("`instance_version_not_found`"),
            500: _problem("Unexpected error"),
        },
    )
    def place_names_route(
        instance_version: Annotated[str, Query(description="The instance version's id.")],
        q: Annotated[str, Query(description="The text typed.")],
    ) -> PlaceNameList:
        return PlaceNameList(
            items=[
                PlaceNameLine.from_domain(line)
                for line in list_place_names.execute(instance_version, q)
            ]
        )

    return router
