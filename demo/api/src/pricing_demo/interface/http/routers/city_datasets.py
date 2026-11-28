from fastapi import APIRouter

from pricing_demo.application.use_cases.list_city_datasets import ListCityDatasets
from pricing_demo.interface.http.schemas import (
    CityDatasetList,
    CityDatasetResource,
    ProblemDetails,
)


def build_city_datasets_router(list_use_case: ListCityDatasets) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["city-data"])

    @router.get(
        "/city-datasets",
        operation_id="listCityDatasets",
        summary="The imported city data sets, oldest first",
        response_model=CityDatasetList,
        responses={500: {"model": ProblemDetails, "description": "Unexpected error"}},
    )
    def list_city_datasets() -> CityDatasetList:
        return CityDatasetList(
            items=[CityDatasetResource.from_domain(item) for item in list_use_case.execute()]
        )

    return router
