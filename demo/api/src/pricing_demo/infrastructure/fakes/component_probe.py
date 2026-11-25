from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.domain.system_status import ComponentName, ComponentStatus

FAKED_COMPONENTS = (
    ComponentName.PRICING_MODEL,
    ComponentName.SOLVER,
    ComponentName.TRIP_PLANNER,
)


class FakeProbe:
    """A probe whose answer is set by the caller; available until told otherwise."""

    def __init__(self, component: ComponentName) -> None:
        self._component = component
        self._answer = ComponentStatus.ready(component)

    @property
    def component(self) -> ComponentName:
        return self._component

    def set_answer(self, available: bool, reason: str | None) -> None:
        self._answer = ComponentStatus(self._component, available, reason)

    def reset(self) -> None:
        self._answer = ComponentStatus.ready(self._component)

    def check(self) -> ComponentStatus:
        return self._answer


class FakeControl:
    """Holds the fake probes of the faked components and changes what they answer."""

    def __init__(self) -> None:
        self._probes = {name: FakeProbe(name) for name in FAKED_COMPONENTS}

    def probe(self, name: ComponentName) -> FakeProbe:
        return self._probes[name]

    def set_component(self, name: ComponentName, available: bool, reason: str | None) -> None:
        probe = self._probes.get(name)
        if probe is None:
            raise ComponentNotControllable(f"The {name} component is not faked.")
        probe.set_answer(available, reason)

    def reset(self) -> None:
        for probe in self._probes.values():
            probe.reset()
