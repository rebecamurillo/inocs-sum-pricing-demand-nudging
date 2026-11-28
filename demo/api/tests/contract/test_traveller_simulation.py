"""What any traveller-simulation rule must satisfy; run against the placeholder itself."""

import pytest

from pricing_demo.application.ports.traveller_simulation import TravellerSimulation
from pricing_demo.domain.read_model import OptionStationDeltaRow, StationBikesRow
from pricing_demo.domain.traveller_simulation import (
    BalancedScore,
    FlatPrice,
    ModelPrices,
    PriceScheme,
    SimulationInstance,
    SimulationOption,
    SimulationPair,
)

RULES: list[TravellerSimulation] = [BalancedScore()]

INSTANCE = SimulationInstance(
    pairs=(SimulationPair("A", "B", 6), SimulationPair("B", "A", 3)),
    options=(
        SimulationOption("ab_bike", "A", "B", "pt_bike", 300, 0, 1),
        SimulationOption("ab_pt", "A", "B", "pt_only", 900, 60),
        SimulationOption("ab_car", "A", "B", "car", 400, 0, 0, 12.0, 5.0),
        SimulationOption("ba_bike", "B", "A", "pt_bike", 300, 0, 1),
        SimulationOption("ba_pt", "B", "A", "pt_only", 900, 60),
    ),
    stations=(StationBikesRow("s1", 4, 2), StationBikesRow("s2", 4, 0)),
    deltas=(
        OptionStationDeltaRow("ab_bike", "s1", -1),
        OptionStationDeltaRow("ab_bike", "s2", 1),
        OptionStationDeltaRow("ba_bike", "s2", -1),
        OptionStationDeltaRow("ba_bike", "s1", 1),
    ),
)
SCHEMES: list[PriceScheme] = [
    ModelPrices({"ab_bike": 0.5, "ba_bike": 0.5}, 2.0, 1.0),
    FlatPrice(1.0, 2.0, 1.0),
]


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("scheme", SCHEMES)
def test_conservation(rule: TravellerSimulation, scheme: PriceScheme) -> None:
    out = rule.simulate(INSTANCE, scheme)
    assert sum(out.travellers_per_mode.values()) + out.unserved == 9


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("scheme", SCHEMES)
def test_stations_stay_within_bounds(rule: TravellerSimulation, scheme: PriceScheme) -> None:
    out = rule.simulate(INSTANCE, scheme)
    assert all(0 <= s.bikes <= s.capacity for s in out.stations_end)


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("scheme", SCHEMES)
def test_output_names_its_rule(rule: TravellerSimulation, scheme: PriceScheme) -> None:
    out = rule.simulate(INSTANCE, scheme)
    assert out.rule_id == rule.rule_id
    assert out.rule_version == rule.rule_version
    assert out.parameters == rule.parameters


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("scheme", SCHEMES)
def test_determinism(rule: TravellerSimulation, scheme: PriceScheme) -> None:
    assert rule.simulate(INSTANCE, scheme) == rule.simulate(INSTANCE, scheme)
