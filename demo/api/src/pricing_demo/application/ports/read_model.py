from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pricing_demo.domain.read_model import (
    HubPairRow,
    HubRow,
    OptionStationDeltaRow,
    RouteOptionRow,
    RoutePairRow,
    StationBikesRow,
    StationHubRow,
    StationRow,
)
from pricing_demo.domain.runs import StepName


@dataclass(frozen=True)
class IngestionBatch:
    """The rows one step's outputs make, and the step's counts, for the artefact `input_key`."""

    input_key: str
    step: StepName
    counts: Mapping[str, Any]
    stations: Sequence[StationRow] = ()
    hubs: Sequence[HubRow] = ()
    station_hubs: Sequence[StationHubRow] = ()
    hub_pairs: Sequence[HubPairRow] = ()
    route_options: Sequence[RouteOptionRow] = ()
    station_bikes: Sequence[StationBikesRow] = ()
    deltas: Sequence[OptionStationDeltaRow] = ()
    route_pairs: Sequence[RoutePairRow] = ()


class ReadModel(Protocol):
    """The tables every screen reads, keyed by the artefact they were ingested from."""

    def ingest(self, batch: IngestionBatch) -> None:
        """In one transaction: replace the rows of the batch's key, then store the counts and
        the time on the artefact. Nothing is stored when any part fails."""
        ...

    def is_ingested(self, key: str) -> bool: ...

    def counts_of(self, keys: Collection[str]) -> Mapping[str, Mapping[str, Any]]:
        """The counts of the ingested keys among `keys`."""
        ...

    def stations(self, key: str) -> list[StationRow]:
        """Ordered by station id."""
        ...

    def hubs(self, key: str) -> list[HubRow]:
        """Ordered by hub id."""
        ...

    def hub_pairs(self, key: str) -> list[HubPairRow]:
        """Ordered by origin, then destination."""
        ...

    def route_pairs(self, key: str) -> list[RoutePairRow]:
        """The pairs of a routes artefact, ordered by origin, then destination."""
        ...

    def route_options(self, key: str) -> list[RouteOptionRow]:
        """The options of an instance artefact, ordered by arc id."""
        ...

    def route_options_of_pair(
        self, key: str, origin_hub: str, destination_hub: str
    ) -> list[RouteOptionRow]:
        """The options of one hub pair of an instance artefact, ordered by arc id."""
        ...

    def station_bikes(self, key: str) -> list[StationBikesRow]:
        """The bike stations of an instance artefact, ordered by station id."""
        ...

    def option_station_deltas(self, key: str) -> list[OptionStationDeltaRow]:
        """The bike movement of each option at each station, ordered by arc, then station."""
        ...
