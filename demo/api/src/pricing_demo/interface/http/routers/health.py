from fastapi import APIRouter


def build_health_router() -> APIRouter:
    """Liveness only: the process answers. It checks no component, so it is cheap to poll."""
    router = APIRouter(prefix="/api", include_in_schema=False)

    @router.get("/health")
    def read_health() -> dict[str, str]:
        return {"status": "ok"}

    return router
