from collections.abc import Mapping

from pricing_demo.domain.system_status import PROBED_COMPONENTS, ComponentName, ComponentState
from pricing_demo.infrastructure.fakes.component_probe import FAKED_COMPONENTS, FakeProbe
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings


def test_the_faked_components_are_the_probed_ones() -> None:
    assert FAKED_COMPONENTS == PROBED_COMPONENTS
    assert ComponentName.STORAGE not in FAKED_COMPONENTS


def test_a_probe_is_available_without_a_settings_row() -> None:
    settings = InMemoryFakeSettings()

    for name in FAKED_COMPONENTS:
        assert FakeProbe(name, settings).check().state is ComponentState.AVAILABLE


def test_a_probe_answers_what_the_settings_say_at_each_check() -> None:
    settings = InMemoryFakeSettings()
    probe = FakeProbe(ComponentName.SOLVER, settings)
    assert probe.check().state is ComponentState.AVAILABLE

    settings.set_component("solver", "limited", "Size-limited.")

    status = probe.check()
    assert status.state is ComponentState.LIMITED
    assert status.reason == "Size-limited."
    assert FakeProbe(ComponentName.TRIP_PLANNER, settings).check().state is (
        ComponentState.AVAILABLE
    )


def test_the_defaults_make_every_probe_available_again() -> None:
    settings = InMemoryFakeSettings()
    settings.set_component("trip_planner", "unavailable", "No answer.")

    settings.write_defaults()

    assert all(
        FakeProbe(name, settings).check().state is ComponentState.AVAILABLE
        for name in FAKED_COMPONENTS
    )


def test_a_malformed_entry_is_an_unavailable_status_that_names_the_fault() -> None:
    class Broken:
        def __init__(self, content: Mapping[str, object]) -> None:
            self.content = content

        def read(self) -> Mapping[str, object]:
            return self.content

    for content in (
        {"components": {"solver": {"state": "maybe"}}},
        {"components": {"solver": {"state": "unavailable"}}},
        {"components": {"solver": "down"}},
        {"components": ["solver"]},
    ):
        status = FakeProbe(ComponentName.SOLVER, Broken(content)).check()

        assert status.state is ComponentState.UNAVAILABLE
        assert status.reason


def test_a_settings_source_that_raises_is_an_unavailable_status() -> None:
    class Failing:
        def read(self) -> dict[str, object]:
            raise ConnectionError("no database")

    status = FakeProbe(ComponentName.PACKAGE, Failing()).check()

    assert status.state is ComponentState.UNAVAILABLE
    assert "no database" in (status.reason or "")
