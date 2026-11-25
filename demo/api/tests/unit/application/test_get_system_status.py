import pytest

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe


def all_probes() -> list[FakeProbe]:
    return [FakeProbe(name) for name in ComponentName]


def test_the_status_lists_every_component_in_order() -> None:
    status = GetSystemStatus(list(reversed(all_probes()))).execute()

    assert [item.name for item in status.components] == list(ComponentName)


def test_runs_can_start_when_every_probe_reports_available() -> None:
    status = GetSystemStatus(all_probes()).execute()

    assert status.can_start_runs


def test_an_unavailable_probe_blocks_runs_and_keeps_its_reason() -> None:
    probes = all_probes()
    probes[2].set_answer(available=False, reason="No Gurobi licence was found.")

    status = GetSystemStatus(probes).execute()

    assert not status.can_start_runs
    solver = status.components[2]
    assert (solver.name, solver.reason) == (ComponentName.SOLVER, "No Gurobi licence was found.")


def test_the_status_is_read_again_at_each_execution() -> None:
    probes = all_probes()
    use_case = GetSystemStatus(probes)
    assert use_case.execute().can_start_runs

    probes[1].set_answer(available=False, reason="Not installed.")

    assert not use_case.execute().can_start_runs


def test_a_missing_probe_is_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="missing: solver"):
        GetSystemStatus(
            [probe for probe in all_probes() if probe.component != ComponentName.SOLVER]
        )


def test_two_probes_for_one_component_are_refused() -> None:
    with pytest.raises(InvalidProbeSet, match="duplicated: storage"):
        GetSystemStatus([*all_probes(), FakeProbe(ComponentName.STORAGE)])
