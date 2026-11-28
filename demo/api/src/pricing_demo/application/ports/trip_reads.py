from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pricing_demo.domain.read_model import HubRow, RouteFailure, RouteOptionRow, StationRow


@dataclass(frozen=True)
class TripArea:
    """What a trip quote needs to know of a built instance version: its circle, its minimum
    trip distance, the ids of its periods by key, its stations and hubs, the hub each station
    belongs to, the hub pairs it kept, and whether its data set has bus shapes."""

    centre: tuple[float, float]
    radius_m: float
    min_od_distance_m: float
    period_ids: Mapping[str, str]
    stations: Sequence[StationRow]
    hubs: Sequence[HubRow]
    station_hubs: Mapping[str, str]
    hub_pairs: frozenset[tuple[str, str]]
    bus_shapes: bool


class TripReads(Protocol):
    """The stored data behind the traveller view: PostgreSQL only, never the trip planner."""

    def area(self, instance_version_id: str) -> TripArea | None:
        """None when the instance version does not exist or is not built."""
        ...

    def pair_options(
        self, instance_version_id: str, origin_hub: str, destination_hub: str
    ) -> list[RouteOptionRow]:
        """The options of the hub pair, ordered by arc id."""
        ...

    def pair_failures(
        self, instance_version_id: str, origin_hub: str, destination_hub: str
    ) -> list[RouteFailure]:
        """The failed queries of the pair recorded by the routes step of the run that produced
        the version's `routes` artefact (that run may belong to another version, which kept
        the step)."""
        ...
