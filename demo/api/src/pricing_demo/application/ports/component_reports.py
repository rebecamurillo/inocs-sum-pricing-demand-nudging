from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.system_status import ComponentReport, ComponentStatus


@dataclass(frozen=True)
class ReportedComponents:
    reports: tuple[ComponentReport, ...]
    latest_worker_heartbeat: datetime | None


class ComponentReports(Protocol):
    """The `component_reports` rows: the worker writes them, the API reads them."""

    def write(
        self,
        status: ComponentStatus,
        worker_id: str,
        at: datetime,
        details: Mapping[str, object] | None = None,
    ) -> None:
        """Replace the report of `status.name`; `details` is stored as `{}` when None."""
        ...

    def read(self) -> ReportedComponents:
        """Every report with its worker's last heartbeat, and the latest heartbeat of any worker."""
        ...
