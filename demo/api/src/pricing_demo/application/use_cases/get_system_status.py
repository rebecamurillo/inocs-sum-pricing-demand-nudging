from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.component_reports import ComponentReports
from pricing_demo.domain.city_datasets import city_data_status
from pricing_demo.domain.system_status import (
    ComponentName,
    ComponentState,
    SystemStatus,
    system_status_from,
)


class GetSystemStatus:
    """The API probes storage only; the rest comes from the worker's reports and heartbeats."""

    def __init__(
        self,
        storage: ComponentProbe,
        reports: ComponentReports,
        datasets: CityDatasets,
        clock: Clock,
    ) -> None:
        if storage.component is not ComponentName.STORAGE:
            raise InvalidProbeSet(
                f"The API probes the storage component only, not {storage.component}."
            )
        self._storage = storage
        self._reports = reports
        self._datasets = datasets
        self._clock = clock

    def execute(self) -> SystemStatus:
        storage = self._storage.check()
        if storage.state is not ComponentState.AVAILABLE:
            return system_status_from(
                storage,
                None,
                [],
                self._clock.now(),
                city_data_status(0),
            )
        reported = self._reports.read()
        return system_status_from(
            storage,
            reported.latest_worker_heartbeat,
            reported.reports,
            self._clock.now(),
            city_data_status(self._datasets.count()),
            reported.simulation_rule,
        )
