from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime

from pricing_demo.application.ports.component_reports import ReportedComponents
from pricing_demo.domain.system_status import ComponentReport, ComponentStatus


class InMemoryComponentReports:
    """The reports in a dict; passes the same contract suite as the PostgreSQL one."""

    def __init__(self) -> None:
        self._reports: dict[str, ComponentReport] = {}
        # The `workers.heartbeat_at` values, set by the test.
        self.worker_heartbeats: dict[str, datetime] = {}
        # The `workers.simulation_rule` values, set by the test.
        self.worker_rules: dict[str, Mapping[str, object]] = {}

    def write(
        self,
        status: ComponentStatus,
        worker_id: str,
        at: datetime,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self._reports[status.name.value] = ComponentReport(
            status=status,
            reported_at=at,
            worker_id=worker_id,
            worker_heartbeat_at=None,
            details=dict(details or {}),
        )

    def read(self) -> ReportedComponents:
        reports = tuple(
            replace(report, worker_heartbeat_at=self.worker_heartbeats.get(report.worker_id))
            for report in self._reports.values()
        )
        latest = max(self.worker_heartbeats.values(), default=None)
        newest = min(
            (item for item, at in self.worker_heartbeats.items() if at == latest), default=None
        )
        rule = None if newest is None else self.worker_rules.get(newest)
        return ReportedComponents(reports, latest, rule)
