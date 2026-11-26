import pytest

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.domain.system_status import ComponentName, ComponentStatus
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import fixed_probe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from tests.support.runs import T0, later

PROBED = (ComponentName.SOLVER, ComponentName.PACKAGE, ComponentName.TRIP_PLANNER)


def ready_probes() -> list[ComponentProbe]:
    return [fixed_probe(ComponentStatus.ready(name)) for name in PROBED]


def test_each_probed_component_is_written_with_the_clock_time_and_the_worker_id() -> None:
    reports = InMemoryComponentReports()
    clock = FixedClock(later(7))
    probes = ready_probes()
    probes[2] = fixed_probe(ComponentStatus.unavailable(ComponentName.TRIP_PLANNER, "no OTP"))

    ReportComponents(probes, reports, "w-1", clock).execute()

    written = {item.status.name: item for item in reports.read().reports}
    assert set(written) == set(PROBED)
    assert {item.reported_at for item in written.values()} == {later(7)}
    assert {item.worker_id for item in written.values()} == {"w-1"}
    assert written[ComponentName.TRIP_PLANNER].status.reason == "no OTP"
    assert written[ComponentName.SOLVER].status.reason is None


def test_a_second_execution_replaces_the_reports() -> None:
    reports = InMemoryComponentReports()
    clock = FixedClock(T0)
    use_case = ReportComponents(ready_probes(), reports, "w-1", clock)
    use_case.execute()

    clock.set(later(30))
    use_case.execute()

    assert {item.reported_at for item in reports.read().reports} == {later(30)}
    assert len(reports.read().reports) == 3


def test_a_missing_probe_is_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="missing: solver"):
        ReportComponents(ready_probes()[1:], InMemoryComponentReports(), "w", FixedClock(T0))


def test_two_probes_for_one_component_are_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="duplicated: package"):
        ReportComponents(
            [*ready_probes(), ready_probes()[1]], InMemoryComponentReports(), "w", FixedClock(T0)
        )


def test_a_probe_of_a_component_the_worker_does_not_probe_is_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="unexpected: storage"):
        ReportComponents(
            [*ready_probes(), fixed_probe(ComponentStatus.ready(ComponentName.STORAGE))],
            InMemoryComponentReports(),
            "w",
            FixedClock(T0),
        )
