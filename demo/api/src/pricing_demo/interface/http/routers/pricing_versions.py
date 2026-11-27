from typing import Any

from fastapi import APIRouter, Response

from pricing_demo.application.use_cases.create_pricing_version import CreatePricingVersion
from pricing_demo.application.use_cases.delete_pricing_version import DeletePricingVersion
from pricing_demo.application.use_cases.get_pricing_version import GetPricingVersion
from pricing_demo.application.use_cases.list_pricing_versions import ListPricingVersions
from pricing_demo.application.use_cases.update_pricing_version import UpdatePricingVersion
from pricing_demo.interface.http.schemas import (
    CreatePricingVersionRequest,
    PricingVersionList,
    PricingVersionPatch,
    PricingVersionResource,
    ProblemDetails,
)

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


UNEXPECTED: Responses = {500: _problem("Unexpected error")}
NOT_FOUND: Responses = {404: _problem("No pricing version has this id")}


def build_pricing_versions_router(
    create: CreatePricingVersion,
    list_versions: ListPricingVersions,
    get: GetPricingVersion,
    update: UpdatePricingVersion,
    delete: DeletePricingVersion,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["pricing-versions"])

    @router.post(
        "/instance-versions/{version_id}/pricing-versions",
        operation_id="createPricingVersion",
        summary="Start a pricing version (a draft) on a built instance version",
        status_code=201,
        response_model=PricingVersionResource,
        responses={
            201: {
                "description": "The draft",
                "headers": {"Location": {"description": "The draft", "schema": {"type": "string"}}},
            },
            404: _problem("No instance version has this id"),
            409: _problem("The instance version is not built: `instance_not_built`"),
            422: _problem("The request is not valid, or `based_on` is not a version of this one"),
            **UNEXPECTED,
        },
    )
    def create_route(
        version_id: str, request: CreatePricingVersionRequest, response: Response
    ) -> PricingVersionResource:
        view = create.execute(version_id, request.name, request.based_on)
        response.headers["Location"] = f"/api/v1/pricing-versions/{view.version.id}"
        return PricingVersionResource.from_view(view)

    @router.get(
        "/instance-versions/{version_id}/pricing-versions",
        operation_id="listPricingVersions",
        summary="The pricing versions of an instance version, in letter order",
        response_model=PricingVersionList,
        responses={404: _problem("No instance version has this id"), **UNEXPECTED},
    )
    def list_route(version_id: str) -> PricingVersionList:
        return PricingVersionList(
            items=[
                PricingVersionResource.from_view(view) for view in list_versions.execute(version_id)
            ]
        )

    @router.get(
        "/pricing-versions/{pricing_version_id}",
        operation_id="getPricingVersion",
        summary="One pricing version: goals, periods, state and rule results",
        response_model=PricingVersionResource,
        responses={**NOT_FOUND, **UNEXPECTED},
    )
    def get_route(pricing_version_id: str) -> PricingVersionResource:
        return PricingVersionResource.from_view(get.execute(pricing_version_id))

    @router.patch(
        "/pricing-versions/{pricing_version_id}",
        operation_id="updatePricingVersion",
        summary="Change the goals of a draft; the answer reports every rule",
        response_model=PricingVersionResource,
        responses={
            **NOT_FOUND,
            409: _problem("The version is saved: `version_sealed`"),
            422: _problem("A value is not a JSON number, or a name is not a goal"),
            **UNEXPECTED,
        },
    )
    def patch_route(pricing_version_id: str, patch: PricingVersionPatch) -> PricingVersionResource:
        return PricingVersionResource.from_view(update.execute(pricing_version_id, patch.changes()))

    @router.delete(
        "/pricing-versions/{pricing_version_id}",
        operation_id="deletePricingVersion",
        summary="Delete a pricing version (a draft is discarded)",
        status_code=204,
        response_class=Response,
        responses={
            **NOT_FOUND,
            409: _problem("A run of the version is queued or running: `run_active`"),
            **UNEXPECTED,
        },
    )
    def delete_route(pricing_version_id: str) -> Response:
        delete.execute(pricing_version_id)
        return Response(status_code=204)

    return router
