from typing import Protocol

from pricing_demo.domain.system_status import ComponentName, ComponentStatus


class ComponentProbe(Protocol):
    @property
    def component(self) -> ComponentName: ...

    def check(self) -> ComponentStatus:
        """Report whether the component works now.

        Never raises: a failure is an unavailable status that carries its reason.
        """
        ...
