from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.showcase import Showcase, ShowcaseMark
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.domain.pricing_versions import NoResult, ResultNotFound


class MarkShowcase:
    """Makes a finished pricing version and period the showcase. Refused (`NoResult`) for a
    version without a result or a period it does not price."""

    def __init__(self, lookup: ResultLookup, showcase: Showcase, clock: Clock) -> None:
        self._lookup = lookup
        self._showcase = showcase
        self._clock = clock

    def execute(self, version_id: str, period_id: str | None = None) -> ShowcaseMark:
        try:
            found = self._lookup.find(version_id, period_id)
        except ResultNotFound as error:
            raise NoResult(version_id) from error
        at = self._clock.now()
        self._showcase.mark(version_id, found.period_id, at)
        return ShowcaseMark(version_id, found.period_id, at)
