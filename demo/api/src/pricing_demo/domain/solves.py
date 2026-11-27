"""What a solve of the pricing model stores: its rows, its quality and its provenance
(ARCHITECTURE.md § 5.2). The fields are those the package writes (`solver.py:703-778`)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

SolveRowType = Literal["PT+Bike", "PT-Only", "Car"]
PT_BIKE: SolveRowType = "PT+Bike"


@dataclass(frozen=True)
class SolveRow:
    """One option of the solve. `PT+Bike` rows exist for the options the model offers only;
    `bike_price` is its price per bike leg."""

    arc_id: str
    origin_hub: str
    destination_hub: str
    type: SolveRowType
    nu: float
    flow: float
    bike_price: float | None
    total_price: float | None
    z_value: float | None
    relaxation_difference: float | None


@dataclass(frozen=True)
class SolveOd:
    origin_hub: str
    destination_hub: str
    gamma: float


@dataclass(frozen=True)
class SolveQuality:
    solver_status: int
    solver_status_name: str
    objective_value: float | None
    gap_pct: float | None
    solution_time_s: float | None
    sol_count: int
    time_limit_reached: bool


@dataclass(frozen=True)
class SolveProvenance:
    gurobi_version: str
    licence_kind: str
    solver_parameters: Mapping[str, object]
    package_fingerprint: str
    demonstrator_version: str
    dependency_lock_sha256: str
    platform: str


@dataclass(frozen=True)
class Solve:
    quality: SolveQuality
    provenance: SolveProvenance
    rows: Sequence[SolveRow] = field(default_factory=tuple)
    ods: Sequence[SolveOd] = field(default_factory=tuple)
    # The first record of the package's `optimizer.summarize`, as the package wrote it, and the
    # goals the solve ran with under the package's names.
    package_summary: Mapping[str, object] | None = None
    package_parameters: Mapping[str, object] = field(default_factory=dict)


def model_bike_prices(rows: Sequence[SolveRow]) -> dict[str, float]:
    """The price per bike leg of each option the model offers (the `PT+Bike` rows)."""
    return {
        row.arc_id: row.bike_price
        for row in rows
        if row.type == PT_BIKE and row.bike_price is not None
    }
