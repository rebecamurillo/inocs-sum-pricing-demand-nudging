import pytest

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import (
    ComponentName,
    ComponentStatus,
    IncompleteSystemStatus,
    InvalidComponentStatus,
    SystemStatus,
)

SOLVER_REASON = "No Gurobi licence was found."


def system_status(**unavailable: str) -> SystemStatus:
    """Every component available, except those named with their reason."""
    return SystemStatus.of(
        ComponentStatus.unavailable(name, unavailable[name.value])
        if name.value in unavailable
        else ComponentStatus.ready(name)
        for name in ComponentName
    )


def test_an_available_component_has_no_reason() -> None:
    status = ComponentStatus.ready(ComponentName.STORAGE)

    assert status.available
    assert status.reason is None


def test_an_unavailable_component_keeps_its_reason() -> None:
    status = ComponentStatus.unavailable(ComponentName.SOLVER, SOLVER_REASON)

    assert not status.available
    assert status.reason == SOLVER_REASON


@pytest.mark.parametrize("reason", [None, ""])
def test_an_unavailable_component_without_a_reason_is_refused(reason: str | None) -> None:
    with pytest.raises(InvalidComponentStatus):
        ComponentStatus(ComponentName.SOLVER, available=False, reason=reason)


def test_an_available_component_with_a_reason_is_refused() -> None:
    with pytest.raises(InvalidComponentStatus):
        ComponentStatus(ComponentName.SOLVER, available=True, reason="fine")


def test_domain_errors_share_one_base() -> None:
    assert issubclass(InvalidComponentStatus, DomainError)
    assert issubclass(IncompleteSystemStatus, DomainError)


def test_statuses_are_put_in_component_order() -> None:
    reversed_statuses = [ComponentStatus.ready(name) for name in reversed(ComponentName)]

    status = SystemStatus.of(reversed_statuses)

    assert [item.name for item in status.components] == list(ComponentName)


def test_a_status_without_every_component_is_refused() -> None:
    with pytest.raises(IncompleteSystemStatus):
        SystemStatus.of([ComponentStatus.ready(ComponentName.STORAGE)])


def test_a_status_with_a_component_twice_is_refused() -> None:
    statuses = [ComponentStatus.ready(name) for name in ComponentName]

    with pytest.raises(IncompleteSystemStatus):
        SystemStatus.of([*statuses, ComponentStatus.ready(ComponentName.SOLVER)])


def test_everything_works_when_every_component_is_available() -> None:
    status = system_status()

    assert status.can_read_stored_results
    assert status.can_start_runs


def test_runs_are_blocked_when_the_solver_is_unavailable() -> None:
    status = system_status(solver=SOLVER_REASON)

    assert status.can_read_stored_results
    assert not status.can_start_runs


def test_stored_results_cannot_be_read_when_storage_is_unavailable() -> None:
    status = system_status(storage="The database does not answer.")

    assert not status.can_read_stored_results
    assert not status.can_start_runs
