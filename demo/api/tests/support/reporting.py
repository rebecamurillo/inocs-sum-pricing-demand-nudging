"""A component report for worker tests that do not look at it."""

from datetime import timedelta

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.domain.system_status import PROBED_COMPONENTS
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings

REPORT_EVERY = timedelta(seconds=30)


def quiet_report(
    clock: Clock, worker_id: str = "w-1", reports: InMemoryComponentReports | None = None
) -> ReportComponents:
    settings = InMemoryFakeSettings()
    return ReportComponents(
        [FakeProbe(name, settings) for name in PROBED_COMPONENTS],
        reports or InMemoryComponentReports(),
        worker_id,
        clock,
    )
