from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pricing_demo.domain.traveller_simulation import SimulationOutputs


@dataclass(frozen=True)
class StoredSimulation:
    """A simulation as it is stored, named by the key of what it read."""

    key: str
    instance_key: str
    period_id: str
    outputs: SimulationOutputs
    scheme_kind: Literal["model_prices", "flat"]
    solve_key: str | None
    flat_price_kind: str | None
    flat_price_amount_chf: float | None
    pt_fare_chf: float
    car_parking_fee_chf: float
    demonstrator_version: str
    duration_s: float
    created_at: datetime
    adapter: Literal["domain", "package"] = "domain"
    package_fingerprint: str | None = None


@dataclass(frozen=True)
class SimulationLink:
    """A pricing version's simulation of one period under one scheme and rule."""

    pricing_version_id: str
    period_id: str
    price_scheme: str
    rule_id: str
    rule_version: int
    simulation_key: str
    created_at: datetime


class Simulations(Protocol):
    def is_stored(self, key: str) -> bool: ...

    def store(self, new: Sequence[StoredSimulation], links: Sequence[SimulationLink]) -> None:
        """In one transaction: each simulation with its child rows (one stored under the key
        already is left as it is), then the links (a link of the same version, period, scheme,
        rule id and rule version is replaced). Nothing is stored when any part fails."""
        ...

    def links_of(self, pricing_version_id: str) -> list[SimulationLink]:
        """The version's links, ordered by period, scheme, rule id and rule version."""
        ...

    def remove_unlinked(self) -> int:
        """Remove every simulation no link names, with its child rows; returns how many."""
        ...
