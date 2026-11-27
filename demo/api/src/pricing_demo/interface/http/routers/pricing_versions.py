from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from pricing_demo.application.use_cases.create_pricing_version import CreatePricingVersion
from pricing_demo.application.use_cases.delete_pricing_version import DeletePricingVersion
from pricing_demo.application.use_cases.get_pricing_result import GetPricingResult
from pricing_demo.application.use_cases.get_pricing_version import GetPricingVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.list_hub_pair_results import ListHubPairResults
from pricing_demo.application.use_cases.list_hub_results import ListHubResults
from pricing_demo.application.use_cases.list_pricing_version_simulations import (
    ListPricingVersionSimulations,
)
from pricing_demo.application.use_cases.list_pricing_versions import ListPricingVersions
from pricing_demo.application.use_cases.run_pricing_version import RunPricingVersion
from pricing_demo.application.use_cases.simulate_pricing_version import SimulatePricingVersion
from pricing_demo.application.use_cases.update_pricing_version import UpdatePricingVersion
from pricing_demo.interface.http.schemas import (
    CreatePricingVersionRequest,
    HubPairResultList,
    HubPairResultResource,
    HubResultList,
    HubResultResource,
    PricingResultResponse,
    PricingVersionList,
    PricingVersionPatch,
    PricingVersionResource,
    PricingVersionSimulationList,
    PricingVersionSimulationResource,
    ProblemDetails,
    RunResource,
)

Responses = dict[int | str, dict[str, Any]]


def _problem(description: str) -> dict[str, Any]:
    return {"model": ProblemDetails, "description": description}


UNEXPECTED: Responses = {500: _problem("Unexpected error")}
NOT_FOUND: Responses = {404: _problem("No pricing version has this id")}
NO_RESULT: Responses = {
    404: _problem(
        "`pricing_version_not_found`, or `no_result`: the version's latest pricing run has not "
        "succeeded, or its solve, its summary or one of its two simulations is missing"
    )
}
Period = Annotated[
    str | None,
    Query(description="The period's id; the version's first period when absent."),
]


def build_pricing_versions_router(
    create: CreatePricingVersion,
    list_versions: ListPricingVersions,
    get: GetPricingVersion,
    update: UpdatePricingVersion,
    delete: DeletePricingVersion,
    run_version: RunPricingVersion,
    get_run: GetRun,
    simulate_version: SimulatePricingVersion,
    list_simulations: ListPricingVersionSimulations,
    get_result: GetPricingResult,
    list_hub_pair_results: ListHubPairResults,
    list_hub_results: ListHubResults,
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
            409: _problem(
                "`run_active` (a run of the version is queued or running) or `is_showcase` "
                "(the version is the showcase)"
            ),
            **UNEXPECTED,
        },
    )
    def delete_route(pricing_version_id: str) -> Response:
        delete.execute(pricing_version_id)
        return Response(status_code=204)

    @router.post(
        "/pricing-versions/{pricing_version_id}/runs",
        operation_id="runPricingVersion",
        summary="Seal a draft and queue its pricing run, or queue the run again after a failure",
        status_code=202,
        response_model=RunResource,
        responses={
            202: {
                "description": "The pricing run is queued; the body is the run",
                "headers": {
                    "Location": {
                        "description": "The run",
                        "schema": {"type": "string"},
                    }
                },
            },
            **NOT_FOUND,
            409: _problem(
                "`rule_broken` (the draft breaks a rule: `pricing_failures` lists each with its "
                "goal and value), `run_active` (`run_id` is the run) or `already_run`"
            ),
            503: _problem(
                "`component_unavailable`: `reasons` names each component the run needs and lacks"
            ),
            **UNEXPECTED,
        },
    )
    def run_route(pricing_version_id: str, response: Response) -> RunResource:
        run = run_version.execute(pricing_version_id)
        response.headers["Location"] = f"/api/v1/runs/{run.id}"
        return RunResource.from_view(get_run.execute(run.id))

    @router.post(
        "/pricing-versions/{pricing_version_id}/simulations",
        operation_id="simulatePricingVersion",
        summary="Queue a simulation run: the stored solve, simulated again with the current rule",
        status_code=202,
        response_model=RunResource,
        responses={
            202: {
                "description": "The simulation run is queued; the body is the run",
                "headers": {"Location": {"description": "The run", "schema": {"type": "string"}}},
            },
            **NOT_FOUND,
            409: _problem(
                "`run_active` (`run_id` is the run), `no_result` (no succeeded pricing run) or "
                "`simulation_current` (both schemes already have a simulation with the current "
                "rule)"
            ),
            503: _problem(
                "`component_unavailable`: no worker runs, or storage is down; `reasons` names each"
            ),
            **UNEXPECTED,
        },
    )
    def simulate_route(pricing_version_id: str, response: Response) -> RunResource:
        run = simulate_version.execute(pricing_version_id)
        response.headers["Location"] = f"/api/v1/runs/{run.id}"
        return RunResource.from_view(get_run.execute(run.id))

    @router.get(
        "/pricing-versions/{pricing_version_id}/simulations",
        operation_id="listPricingVersionSimulations",
        summary="Every stored simulation of a version, with its rule and whether it is current",
        response_model=PricingVersionSimulationList,
        responses={**NOT_FOUND, **UNEXPECTED},
    )
    def list_simulations_route(pricing_version_id: str) -> PricingVersionSimulationList:
        return PricingVersionSimulationList(
            items=[
                PricingVersionSimulationResource.from_view(item)
                for item in list_simulations.execute(pricing_version_id)
            ]
        )

    @router.get(
        "/pricing-versions/{pricing_version_id}/result",
        operation_id="getPricingResult",
        summary="The numbers of a finished version, each with its unit, its source and its group",
        response_model=PricingResultResponse,
        responses={**NO_RESULT, **UNEXPECTED},
    )
    def result_route(pricing_version_id: str, period: Period = None) -> PricingResultResponse:
        return PricingResultResponse.from_domain(get_result.execute(pricing_version_id, period))

    @router.get(
        "/pricing-versions/{pricing_version_id}/hub-pair-results",
        operation_id="listHubPairResults",
        summary="Per hub pair: the bike price, the travellers per mode and the options",
        response_model=HubPairResultList,
        responses={**NO_RESULT, **UNEXPECTED},
    )
    def hub_pair_results_route(pricing_version_id: str, period: Period = None) -> HubPairResultList:
        return HubPairResultList(
            items=[
                HubPairResultResource.from_domain(item)
                for item in list_hub_pair_results.execute(pricing_version_id, period)
            ]
        )

    @router.get(
        "/pricing-versions/{pricing_version_id}/hub-results",
        operation_id="listHubResults",
        summary="Per hub: the bike rides that start and end there and the mean bike price",
        response_model=HubResultList,
        responses={**NO_RESULT, **UNEXPECTED},
    )
    def hub_results_route(pricing_version_id: str, period: Period = None) -> HubResultList:
        return HubResultList(
            items=[
                HubResultResource.from_domain(item)
                for item in list_hub_results.execute(pricing_version_id, period)
            ]
        )

    return router
