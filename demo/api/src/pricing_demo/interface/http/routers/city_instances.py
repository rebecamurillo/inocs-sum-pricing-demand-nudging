from typing import Any

from fastapi import APIRouter, Response

from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.create_city_instance import (
    CreateCityInstance,
    FromCopy,
    FromPackageDefaults,
    StartFrom,
)
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.interface.http.schemas import (
    CityInstanceMenu,
    CityInstanceMenuItem,
    CopyStart,
    CreateCityInstanceRequest,
    CreateInstanceVersionRequest,
    InstanceVersionPatch,
    InstanceVersionResource,
    ProblemDetails,
    RunResource,
)

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


UNEXPECTED: Responses = {500: _problem("Unexpected error")}
VERSION_NOT_FOUND: Responses = {404: _problem("No instance version has this id")}
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
    build_version: BuildInstanceVersion,
    get_run: GetRun,
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
        summary="Discard a draft, and its instance when it was the only version",
        status_code=204,
        response_class=Response,
        responses={**VERSION_NOT_FOUND, **VERSION_SEALED, **UNEXPECTED},
    )
    def discard_version(version_id: str) -> Response:
        delete_version.execute(version_id)
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
