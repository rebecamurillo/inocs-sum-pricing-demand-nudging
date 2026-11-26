from collections import Counter
from collections.abc import Sequence

from pricing_demo.application.errors import InvalidProbeSet
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.component_reports import ComponentReports
from pricing_demo.domain.system_status import PROBED_COMPONENTS


class ReportComponents:
    """Check the solver, the package and the trip planner and write what each answered."""

    def __init__(
        self,
        probes: Sequence[ComponentProbe],
        reports: ComponentReports,
        worker_id: str,
        clock: Clock,
    ) -> None:
        counts = Counter(probe.component for probe in probes)
        missing = [name for name in PROBED_COMPONENTS if counts[name] == 0]
        duplicated = [name for name in PROBED_COMPONENTS if counts[name] > 1]
        unexpected = [name for name in counts if name not in PROBED_COMPONENTS]
        if missing or duplicated or unexpected:
            raise InvalidProbeSet(
                "Exactly one probe per probed component is required; "
                f"missing: {', '.join(missing) or 'none'}; "
                f"duplicated: {', '.join(duplicated) or 'none'}; "
                f"unexpected: {', '.join(unexpected) or 'none'}."
            )
        self._probes = tuple(probes)
        self._reports = reports
        self._worker_id = worker_id
        self._clock = clock

    def execute(self) -> None:
        for probe in self._probes:
            self._reports.write(probe.check(), self._worker_id, self._clock.now())
