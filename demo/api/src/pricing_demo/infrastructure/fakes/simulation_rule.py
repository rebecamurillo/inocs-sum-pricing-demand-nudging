"""The traveller simulation rule of the fake adapter set: `balanced-score`, with the version
and the weights the `pricing_model.simulation_rule` entry of the fake settings stages, so a
test can change the rule the worker uses (the next heartbeat records it, the next simulation
step simulates with it)."""

from collections.abc import Mapping
from typing import Any

from pricing_demo.domain.traveller_simulation import BalancedScore
from pricing_demo.infrastructure.fakes.component_probe import FakeSettingsSource


class FakeSimulationRule:
    def __init__(self, settings: FakeSettingsSource) -> None:
        self._settings = settings

    def current(self) -> BalancedScore:
        """`BalancedScore` v1 with equal weights, or the staged version and weights."""
        model: Mapping[str, Any] = self._settings.read().get("pricing_model") or {}  # type: ignore[assignment]
        staged = model.get("simulation_rule")
        if not isinstance(staged, Mapping):
            return BalancedScore()
        return BalancedScore(
            price_weight=float(staged["price_weight"]),
            time_weight=float(staged["time_weight"]),
            rule_version=int(staged["version"]),
        )
