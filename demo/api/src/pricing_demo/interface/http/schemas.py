from pydantic import BaseModel

from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus


class ComponentStatusResponse(BaseModel):
    name: ComponentName
    available: bool
    reason: str | None

    @classmethod
    def from_domain(cls, status: ComponentStatus) -> "ComponentStatusResponse":
        return cls(name=status.name, available=status.available, reason=status.reason)


class SystemStatusResponse(BaseModel):
    api_version: str
    components: list[ComponentStatusResponse]
    can_read_stored_results: bool
    can_start_runs: bool

    @classmethod
    def from_domain(cls, status: SystemStatus, api_version: str) -> "SystemStatusResponse":
        return cls(
            api_version=api_version,
            components=[ComponentStatusResponse.from_domain(item) for item in status.components],
            can_read_stored_results=status.can_read_stored_results,
            can_start_runs=status.can_start_runs,
        )


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    """An error, as a problem document (RFC 9457)."""

    type: str
    title: str
    status: int
    detail: str
    code: str
    errors: list[FieldError] | None = None


class ComponentAnswerRequest(BaseModel):
    available: bool
    reason: str | None = None
