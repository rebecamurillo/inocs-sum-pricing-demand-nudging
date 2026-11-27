"""A pricing rig with the use cases of the result: a built fake city, a pricing version run by
the worker's two steps, and the readers of its result."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.application.use_cases.compare_pricing_versions import ComparePricingVersions
from pricing_demo.application.use_cases.get_pricing_result import GetPricingResult
from pricing_demo.application.use_cases.get_showcase import GetShowcase
from pricing_demo.application.use_cases.list_hub_pair_results import ListHubPairResults
from pricing_demo.application.use_cases.list_hub_results import ListHubResults
from pricing_demo.application.use_cases.list_place_names import ListPlaceNames
from pricing_demo.application.use_cases.list_route_options import ListRouteOptions
from pricing_demo.application.use_cases.mark_showcase import MarkShowcase
from pricing_demo.application.use_cases.quote_trip import QuoteTrip
from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    InMemoryPackageFingerprints,
)
from pricing_demo.infrastructure.fakes.trip_reads import InMemoryTripReads
from tests.support.pricing_runs import PERIOD, PricingRig
from tests.support.runs import T0


class ResultRig(PricingRig):
    def __init__(
        self,
        folder: Path,
        with_fingerprint: bool = True,
        route_failures: Sequence[Mapping[str, str]] = (),
        instance_changes: Sequence[tuple[str, float]] = (),
    ) -> None:
        super().__init__(folder, route_failures=route_failures, instance_changes=instance_changes)
        base = self.rig
        self.fingerprints = InMemoryPackageFingerprints()
        if with_fingerprint:
            self.fingerprints.record(FAKE_FINGERPRINT, T0)
        self.lookup = ResultLookup(base.pricing, base.solves, base.simulations)
        self.result = GetPricingResult(
            self.lookup,
            base.simulations,
            base.instances,
            base.datasets,
            base.artifacts,
            self.fingerprints,
            base.status,
        )
        self.compare = ComparePricingVersions(
            base.pricing, self.result, base.solves, base.instances
        )
        self.hub_pairs = ListHubPairResults(
            self.lookup, base.solves, base.artifacts, base.read_model
        )
        self.hubs = ListHubResults(self.lookup, base.artifacts, base.read_model)
        self.trips = InMemoryTripReads(
            base.instances, base.datasets, base.artifacts, base.read_model, base.route_failures
        )
        self.quote = QuoteTrip(self.lookup, base.pricing, base.solves, self.trips)
        self.place_names = ListPlaceNames(base.instances, self.trips)
        self.route_options = ListRouteOptions(base.instances, self.trips)
        self.mark = MarkShowcase(self.lookup, base.showcase, base.clock)
        self.get_showcase = GetShowcase(base.showcase, self.lookup, base.instances)

    def finished(self, **changes: float) -> str:
        """A pricing version whose run succeeded (both steps)."""
        version = self.version(**changes)
        self.run(version)
        return version

    def current_rule(self, rule: BalancedScore | None) -> None:
        """The rule the live worker reports (none: no live worker)."""
        status = self.rig.status
        status.value = replace(
            status.value, simulation_rule=None if rule is None else SimulationRule.of(rule)
        )


__all__ = ["PERIOD", "ResultRig"]
