"""Stored simulations for the tests: a version simulated under a rule, in memory."""

from pricing_demo.application.ports.simulations import SimulationLink, StoredSimulation
from pricing_demo.domain.traveller_simulation import (
    BalancedScore,
    FlatPrice,
    SimulationInstance,
)
from pricing_demo.infrastructure.fakes.simulations import InMemorySimulations
from tests.support.runs import T0

SCHEMES = ("model_prices", "flat")


def simulate_under(
    simulations: InMemorySimulations,
    version_id: str,
    period_id: str,
    rule: BalancedScore,
    schemes: tuple[str, ...] = SCHEMES,
) -> None:
    """Store a simulation of each scheme named, under `rule`, and link it to the version."""
    outputs = rule.simulate(SimulationInstance((), (), (), ()), FlatPrice(1.0, 2.0, 2.8))
    new, links = [], []
    for scheme in schemes:
        key = f"{version_id}/{scheme}/{rule.rule_version}/{sorted(rule.parameters.items())}"
        new.append(
            StoredSimulation(
                key=key,
                instance_key="i",
                period_id=period_id,
                outputs=outputs,
                scheme_kind=scheme,  # type: ignore[arg-type]
                solve_key=None,
                flat_price_kind="per_ride",
                flat_price_amount_chf=1.0,
                pt_fare_chf=2.0,
                car_parking_fee_chf=2.8,
                demonstrator_version="0.1.0",
                duration_s=0.0,
                created_at=T0,
            )
        )
        links.append(
            SimulationLink(version_id, period_id, scheme, rule.rule_id, rule.rule_version, key, T0)
        )
    simulations.store(new, links)
