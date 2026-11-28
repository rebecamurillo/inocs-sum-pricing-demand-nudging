from collections.abc import Mapping
from typing import Protocol

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentState,
    ComponentStatus,
)

FAKED_COMPONENTS = PROBED_COMPONENTS


class FakeSettingsSource(Protocol):
    def read(self) -> Mapping[str, object]: ...


class FakeProbe:
    """A probe whose answer is read from the fake settings at each check; available until
    the settings say otherwise."""

    def __init__(self, component: ComponentName, settings: FakeSettingsSource) -> None:
        self._component = component
        self._settings = settings

    @property
    def component(self) -> ComponentName:
        return self._component

    def check(self) -> ComponentStatus:
        try:
            return self._read()
        except Exception as error:
            return ComponentStatus.unavailable(
                self._component, f"The fake settings are not readable: {error}"
            )

    def _read(self) -> ComponentStatus:
        components = self._settings.read().get("components")
        if components is None:
            return ComponentStatus.ready(self._component)
        if not isinstance(components, Mapping):
            raise ValueError("'components' is not an object")
        entry = components.get(self._component.value)
        if entry is None:
            return ComponentStatus.ready(self._component)
        if not isinstance(entry, Mapping):
            raise ValueError(f"the entry of {self._component} is not an object")
        try:
            return ComponentStatus(
                self._component, ComponentState(str(entry.get("state"))), entry.get("reason")
            )
        except (ValueError, DomainError) as error:
            raise ValueError(f"the entry of {self._component} is invalid ({error})") from error


class _FixedProbe:
    def __init__(self, status: ComponentStatus) -> None:
        self._status = status

    @property
    def component(self) -> ComponentName:
        return self._status.name

    def check(self) -> ComponentStatus:
        return self._status


def fixed_probe(status: ComponentStatus) -> _FixedProbe:
    """A probe that always answers `status`."""
    return _FixedProbe(status)
