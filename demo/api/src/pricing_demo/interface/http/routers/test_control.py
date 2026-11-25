from typing import Protocol

from fastapi import APIRouter, Response

from pricing_demo.domain.system_status import ComponentName
from pricing_demo.interface.http.schemas import ComponentAnswerRequest


class E2ETestSeam(Protocol):
    """What the end-to-end suite may change in an application that runs on fake adapters.

    No use case needs it, so it belongs to the delivery layer; infrastructure satisfies it
    structurally.
    """

    def set_component(self, name: ComponentName, available: bool, reason: str | None) -> None:
        """Make a faked component answer as given.

        Raises ComponentNotControllable when the component is not faked.
        """
        ...

    def reset(self) -> None:
        """Return the application to its initial state: fakes at their defaults, no stored data."""
        ...


def build_test_control_router(seam: E2ETestSeam) -> APIRouter:
    router = APIRouter(prefix="/api/test-control", include_in_schema=False)

    @router.put("/components/{name}", status_code=204)
    def set_component_answer(name: ComponentName, answer: ComponentAnswerRequest) -> Response:
        seam.set_component(name, answer.available, answer.reason)
        return Response(status_code=204)

    @router.post("/reset", status_code=204)
    def reset() -> Response:
        seam.reset()
        return Response(status_code=204)

    return router
