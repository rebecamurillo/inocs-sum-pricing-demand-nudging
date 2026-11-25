from fastapi import APIRouter

from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.interface.http.schemas import ProblemDetails, SystemStatusResponse


def build_system_status_router(get_system_status: GetSystemStatus, api_version: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["system"])

    @router.get(
        "/system-status",
        operation_id="getSystemStatus",
        summary="Which components of the system work now",
        response_model=SystemStatusResponse,
        responses={500: {"model": ProblemDetails, "description": "Unexpected error"}},
    )
    def read_system_status() -> SystemStatusResponse:
        return SystemStatusResponse.from_domain(get_system_status.execute(), api_version)

    return router
