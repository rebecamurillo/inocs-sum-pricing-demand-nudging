from collections import Counter
from collections.abc import Sequence

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.domain.system_status import ComponentName, SystemStatus


class GetSystemStatus:
    def __init__(self, probes: Sequence[ComponentProbe]) -> None:
        counts = Counter(probe.component for probe in probes)
        missing = [name for name in ComponentName if counts[name] == 0]
        duplicated = [name for name in ComponentName if counts[name] > 1]
        if missing or duplicated:
            raise InvalidProbeSet(
                "Exactly one probe per component is required; "
                f"missing: {', '.join(missing) or 'none'}; "
                f"duplicated: {', '.join(duplicated) or 'none'}."
            )
        self._probes = tuple(probes)

    def execute(self) -> SystemStatus:
        return SystemStatus.of(probe.check() for probe in self._probes)
