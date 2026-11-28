from collections.abc import Mapping
from typing import Protocol

from pricing_demo.domain.traveller_simulation import (
    PriceScheme,
    SimulationInstance,
    SimulationOutputs,
)


class TravellerSimulation(Protocol):
    """A rule that simulates the travellers of a period under a price scheme."""

    @property
    def rule_id(self) -> str: ...

    @property
    def rule_version(self) -> int: ...

    @property
    def parameters(self) -> Mapping[str, float]: ...

    def simulate(self, instance: SimulationInstance, scheme: PriceScheme) -> SimulationOutputs:
        """The outputs, each carrying the rule's id, version and parameters."""
        ...
