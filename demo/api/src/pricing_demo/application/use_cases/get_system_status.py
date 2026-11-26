from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.component_reports import ComponentReports
from pricing_demo.domain.system_status import (
    ComponentName,
    ComponentState,
    SystemStatus,
    system_status_from,
)


class GetSystemStatus:
    """The API probes storage only; the rest comes from the worker's reports and heartbeats."""

    def __init__(self, storage: ComponentProbe, reports: ComponentReports, clock: Clock) -> None:
        if storage.component is not ComponentName.STORAGE:
            raise InvalidProbeSet(
                f"The API probes the storage component only, not {storage.component}."
            )
        self._storage = storage
        self._reports = reports
        self._clock = clock

    def execute(self) -> SystemStatus:
        storage = self._storage.check()
        if storage.state is not ComponentState.AVAILABLE:
            return system_status_from(storage, None, [], self._clock.now())
        reported = self._reports.read()
        return system_status_from(
            storage, reported.latest_worker_heartbeat, reported.reports, self._clock.now()
        )
