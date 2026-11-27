from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.system_status import ComponentReport, ComponentStatus


@dataclass(frozen=True)
class ReportedComponents:
    reports: tuple[ComponentReport, ...]
    latest_worker_heartbeat: datetime | None
    # The `simulation_rule` of the worker with that latest heartbeat (ties by id).
    simulation_rule: Mapping[str, object] | None = None


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
        """Every report with its worker's last heartbeat, the latest heartbeat of any worker and
        the simulation rule that worker records."""
        ...
