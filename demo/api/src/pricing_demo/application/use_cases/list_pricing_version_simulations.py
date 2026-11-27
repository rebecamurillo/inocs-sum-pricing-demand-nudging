from collections.abc import Callable
from dataclasses import dataclass

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.simulations import LinkedSimulation, Simulations
from pricing_demo.application.use_cases.simulate_pricing_version import has_rule
from pricing_demo.domain.pricing_versions import PricingVersionNotFound
from pricing_demo.domain.system_status import SystemStatus


@dataclass(frozen=True)
class VersionSimulation:
    linked: LinkedSimulation
    # True when the simulation ran under the rule the live worker uses now.
    rule_current: bool


class ListPricingVersionSimulations:
    """Every simulation stored for a version, with whether its rule is the current one."""

    def __init__(
        self,
        pricing_versions: PricingVersions,
        simulations: Simulations,
        system_status: Callable[[], SystemStatus],
    ) -> None:
        self._pricing_versions = pricing_versions
        self._simulations = simulations
        self._system_status = system_status

    def execute(self, version_id: str) -> list[VersionSimulation]:
        if self._pricing_versions.get(version_id) is None:
            raise PricingVersionNotFound(version_id)
        linked = self._simulations.linked_of(version_id)
        if not linked:
            return []
        rule = self._system_status().simulation_rule
        return [
            VersionSimulation(item, rule is not None and has_rule(item, rule)) for item in linked
        ]
