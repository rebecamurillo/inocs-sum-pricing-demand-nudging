from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.create_city_instance import (
    CreateCityInstance,
    FromCopy,
    FromPackageDefaults,
    StartFrom,
)
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.delete_city_instance import DeleteCityInstance
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.list_hub_pairs import ListHubPairs
from pricing_demo.application.use_cases.list_hubs import ListHubs
from pricing_demo.application.use_cases.list_route_pairs import ListRoutePairs
from pricing_demo.application.use_cases.list_stations import ListStations
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.interface.http.schemas import (
    CityInstanceMenu,
    CityInstanceMenuItem,
    CopyStart,
    CreateCityInstanceRequest,
    CreateInstanceVersionRequest,
    HubList,
    HubPairList,
    HubPairResource,
    HubResource,
    InstanceVersionPatch,
    InstanceVersionResource,
    ProblemDetails,
    RoutePairList,
    RoutePairResource,
    RunResource,
    StationList,
    StationResource,
)

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


UNEXPECTED: Responses = {500: _problem("Unexpected error")}
VERSION_NOT_FOUND: Responses = {404: _problem("No instance version has this id")}
INSTANCE_NOT_FOUND: Responses = {404: _problem("No city instance has this id")}
RUN_ACTIVE: Responses = {
    409: _problem(
        "A run of the version, or of a version of the instance, is queued or running: `run_active`"
    )
}
VERSION_SEALED: Responses = {409: _problem("The version is saved: `version_sealed`")}


def _start_from(request: CreateCityInstanceRequest) -> StartFrom:
    start = request.start_from
    if isinstance(start, CopyStart):
        return FromCopy(start.instance_version_id)
    return FromPackageDefaults()


def build_city_instances_router(
    create_instance: CreateCityInstance,
    list_instances: ListCityInstances,
    create_version: CreateInstanceVersion,
    get_version: GetInstanceVersion,
    update_version: UpdateInstanceVersion,
    delete_version: DeleteInstanceVersion,
    delete_instance: DeleteCityInstance,
    build_version: BuildInstanceVersion,
    get_run: GetRun,
    list_stations: ListStations,
    list_hubs: ListHubs,
    list_hub_pairs: ListHubPairs,
    list_route_pairs: ListRoutePairs,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["city-instances"])

    @router.post(
        "/city-instances",
        operation_id="createCityInstance",
        summary="Create a city instance with its first draft version",
        status_code=201,
        response_model=InstanceVersionResource,
        responses={
            201: {
                "description": "The instance exists; the body is its first draft",
                "headers": {
                    "Location": {
                        "description": "The draft version",
                        "schema": {"type": "string"},
                    }
                },
            },
            409: _problem(
                "`name_taken` (the name or its identifier is used) or "
                "`package_defaults_missing` (no worker reported the package yet)"
            ),
            422: _problem("The request is not valid, or the data set or version is unknown"),
            **UNEXPECTED,
        },
    )
    def create(request: CreateCityInstanceRequest, response: Response) -> InstanceVersionResource:
        view = create_instance.execute(request.name, request.dataset_id, _start_from(request))
        response.headers["Location"] = f"/api/v1/instance-versions/{view.version.id}"
        return InstanceVersionResource.from_view(view)

    @router.get(
        "/city-instances",
        operation_id="listCityInstances",
        summary="The instances with their versions, oldest instance first",
        response_model=CityInstanceMenu,
        responses=UNEXPECTED,
    )
    def read_menu() -> CityInstanceMenu:
        return CityInstanceMenu(
            items=[CityInstanceMenuItem.from_domain(item) for item in list_instances.execute()]
        )

    @router.post(
        "/city-instances/{instance_id}/versions",
        operation_id="createInstanceVersion",
        summary="Create the draft of a new version, based on a version",
        status_code=201,
        response_model=InstanceVersionResource,
        responses={
            201: {
                "description": "The draft",
                "headers": {
                    "Location": {
                        "description": "The draft version",
                        "schema": {"type": "string"},
                    }
                },
            },
            404: _problem("No city instance has this id"),
            409: _problem("The instance has a draft: `draft_exists` carries its `draft_id`"),
            422: _problem("The request is not valid, or the version to base on is unknown"),
            **UNEXPECTED,
        },
    )
    def create_draft(
        instance_id: str, request: CreateInstanceVersionRequest, response: Response
    ) -> InstanceVersionResource:
        view = create_version.execute(instance_id, request.based_on_id)
        response.headers["Location"] = f"/api/v1/instance-versions/{view.version.id}"
        return InstanceVersionResource.from_view(view)

    @router.get(
        "/instance-versions/{version_id}",
        operation_id="getInstanceVersion",
        summary="One version: parameters, periods, rule results and what changes",
        response_model=InstanceVersionResource,
        responses={**VERSION_NOT_FOUND, **UNEXPECTED},
    )
    def read_version(version_id: str) -> InstanceVersionResource:
        return InstanceVersionResource.from_view(get_version.execute(version_id))

    @router.get(
        "/instance-versions/{version_id}/stations",
        operation_id="listStations",
        summary="The public transport stops and bike stations of a built version",
        description="Ordered by `station_id`.",
        response_model=StationList,
        responses={**VERSION_NOT_FOUND, **UNEXPECTED},
    )
    def read_stations(version_id: str) -> StationList:
        return StationList(
            items=[StationResource.from_domain(row) for row in list_stations.execute(version_id)]
        )

    @router.get(
        "/instance-versions/{version_id}/hubs",
        operation_id="listHubs",
        summary="The hubs of a built version, with their stations and lines",
        description="Ordered by `hub_id`.",
        response_model=HubList,
        responses={**VERSION_NOT_FOUND, **UNEXPECTED},
    )
    def read_hubs(version_id: str) -> HubList:
        return HubList(
            items=[HubResource.from_domain(row) for row in list_hubs.execute(version_id)]
        )

    @router.get(
        "/instance-versions/{version_id}/hub-pairs",
        operation_id="listHubPairs",
        summary="The hub pairs of one period of a built version",
        description="Ordered by `origin_hub`, then `destination_hub`.",
        response_model=HubPairList,
        responses={
            404: _problem(
                "`instance_version_not_found`, or `period_not_found` (the period is not one "
                "of the version's)"
            ),
            **UNEXPECTED,
        },
    )
    def read_hub_pairs(
        version_id: str,
        period: Annotated[
            str | None,
            Query(description="The id of a period of the version; the only period by default."),
        ] = None,
    ) -> HubPairList:
        return HubPairList(
            items=[
                HubPairResource.from_domain(row)
                for row in list_hub_pairs.execute(version_id, period)
            ]
        )

    @router.get(
        "/instance-versions/{version_id}/route-pairs",
        operation_id="listRoutePairs",
        summary="The hub pairs the routes step of a version routed",
        description="Ordered by `origin_hub`, then `destination_hub`. Empty until the routes "
        "step is linked to the version, which is before the last step ends.",
        response_model=RoutePairList,
        responses={**VERSION_NOT_FOUND, **UNEXPECTED},
    )
    def read_route_pairs(version_id: str) -> RoutePairList:
        return RoutePairList(
            items=[
                RoutePairResource.from_domain(row) for row in list_route_pairs.execute(version_id)
            ]
        )

    @router.patch(
        "/instance-versions/{version_id}",
        operation_id="updateInstanceVersion",
        summary="Change parameters of a draft; the answer reports every rule",
        response_model=InstanceVersionResource,
        responses={
            **VERSION_NOT_FOUND,
            **VERSION_SEALED,
            422: _problem("A value is not a JSON number, or a name is not a parameter"),
            **UNEXPECTED,
        },
    )
    def patch_version(version_id: str, patch: InstanceVersionPatch) -> InstanceVersionResource:
        return InstanceVersionResource.from_view(
            update_version.execute(version_id, patch.changes())
        )

    @router.delete(
        "/instance-versions/{version_id}",
        operation_id="deleteInstanceVersion",
        summary="Delete an instance version (a draft or a saved one)",
        status_code=204,
        response_class=Response,
        responses={**VERSION_NOT_FOUND, **RUN_ACTIVE, **UNEXPECTED},
    )
    def discard_version(version_id: str) -> Response:
        delete_version.execute(version_id)
        return Response(status_code=204)

    @router.delete(
        "/city-instances/{instance_id}",
        operation_id="deleteCityInstance",
        summary="Delete a city instance with all its versions",
        status_code=204,
        response_class=Response,
        responses={**INSTANCE_NOT_FOUND, **RUN_ACTIVE, **UNEXPECTED},
    )
    def delete_city_instance_route(instance_id: str) -> Response:
        delete_instance.execute(instance_id)
        return Response(status_code=204)

    @router.post(
        "/instance-versions/{version_id}/builds",
        operation_id="buildInstanceVersion",
        summary="Seal a draft and queue its build, or queue the build again after a failure",
        status_code=202,
        response_model=RunResource,
        responses={
            202: {
                "description": "The build run is queued; the body is the run",
                "headers": {
                    "Location": {
                        "description": "The run",
                        "schema": {"type": "string"},
                    }
                },
            },
            **VERSION_NOT_FOUND,
            409: _problem(
                "`rule_broken` (the draft breaks a rule: `failures` lists each with both "
                "values), `run_active` (`run_id` is the run) or `already_built`"
            ),
            503: _problem(
                "`component_unavailable`: `reasons` names each component the build needs and lacks"
            ),
            **UNEXPECTED,
        },
    )
    def build(version_id: str, response: Response) -> RunResource:
        run = build_version.execute(version_id)
        response.headers["Location"] = f"/api/v1/runs/{run.id}"
        return RunResource.from_view(get_run.execute(run.id))

    return router
