"""What the worker knows about the pricing package it runs: its identity and its defaults."""

from collections.abc import Mapping
from dataclasses import dataclass, field

# The package's names for the two park-time defaults; the demonstrator's columns say the unit.
_RENAMED = {"min_park_time": "min_park_time_min", "max_park_time": "max_park_time_min"}
# The defaults of the three groups that feed an instance version, and the columns they fill.
_INSTANCE_COLUMNS = (
    "clustering_threshold_m",
    "clustering_buffer_m",
    "min_od_distance_m",
    "seed",
    "fixed_capacity",
    "min_demand",
    "max_demand",
    "min_inventory_pct",
    "max_inventory_pct",
    "min_park_time_min",
    "max_park_time_min",
)

# The solver's twelve choice-model constants, in the order of ARCHITECTURE.md § 6.4.
CHOICE_COEFFICIENT_NAMES = (
    "ASC_PT",
    "ASC_BIKE",
    "ASC_CAR",
    "BETA_Cost_BIKE",
    "BETA_Time_BIKE",
    "BETA_TR_BIKE",
    "BETA_Cost_PT",
    "BETA_Time_PT",
    "BETA_TR_PT",
    "BETA_Cost_Car",
    "BETA_Cost_park",
    "BETA_Time_Car",
)


@dataclass(frozen=True)
class PackageFingerprint:
    """`fingerprint` is the sha256 over the package's sources and the repository commit;
    `defaults` maps `PipelineConfig`, `InstanceParams` and `OptimizerParams` to the default
    value of each field that has one; `choice_coefficients` maps each of the twelve choice-model
    constants of the solver to its value, or to None when it was not found."""

    fingerprint: str
    version: str
    git_commit: str
    git_dirty: bool
    defaults: Mapping[str, Mapping[str, object]]
    choice_coefficients: Mapping[str, float | None] = field(default_factory=dict)


def instance_defaults(defaults: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    """The package defaults an instance version holds, by column name."""
    found: dict[str, object] = {}
    for group in ("PipelineConfig", "InstanceParams"):
        for name, value in defaults.get(group, {}).items():
            column = _RENAMED.get(name, name)
            if column in _INSTANCE_COLUMNS:
                found[column] = value
    return found
