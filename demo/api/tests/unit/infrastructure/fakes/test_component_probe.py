import pytest

from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.infrastructure.fakes.component_probe import FAKED_COMPONENTS, FakeControl


def test_every_faked_component_is_available_by_default() -> None:
    control = FakeControl()

    assert all(control.probe(name).check().available for name in FAKED_COMPONENTS)


def test_storage_is_not_faked() -> None:
    assert ComponentName.STORAGE not in FAKED_COMPONENTS


def test_a_component_answers_what_the_control_sets() -> None:
    control = FakeControl()

    control.set_component(ComponentName.SOLVER, available=False, reason="No licence.")

    status = control.probe(ComponentName.SOLVER).check()
    assert not status.available
    assert status.reason == "No licence."
    assert control.probe(ComponentName.TRIP_PLANNER).check().available


def test_reset_returns_every_component_to_available() -> None:
    control = FakeControl()
    control.set_component(ComponentName.SOLVER, available=False, reason="No licence.")
    control.set_component(ComponentName.TRIP_PLANNER, available=False, reason="No answer.")

    control.reset()

    assert all(control.probe(name).check().available for name in FAKED_COMPONENTS)


def test_a_component_that_is_not_faked_cannot_be_set() -> None:
    with pytest.raises(ComponentNotControllable):
        FakeControl().set_component(ComponentName.STORAGE, available=False, reason="Down.")
