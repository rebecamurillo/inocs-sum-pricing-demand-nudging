import threading
from collections.abc import Collection, Mapping
from dataclasses import replace
from typing import Any

from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.domain.read_model import (
    HubPairRow,
    HubRow,
    OptionStationDeltaRow,
    RouteOptionRow,
    RoutePairRow,
    StationBikesRow,
    StationRow,
)


class InMemoryReadModel:
    """The ingested batches in a dict, one per key; passes the same contract suite as the
    PostgreSQL adapter."""

    def __init__(self) -> None:
        self._batches: dict[str, IngestionBatch] = {}
        self._lock = threading.Lock()

    def ingest(self, batch: IngestionBatch) -> None:
        with self._lock:
            self._batches[batch.input_key] = replace(batch, counts=dict(batch.counts))

    def is_ingested(self, key: str) -> bool:
        with self._lock:
            return key in self._batches

    def counts_of(self, keys: Collection[str]) -> Mapping[str, Mapping[str, Any]]:
        with self._lock:
            return {key: self._batches[key].counts for key in keys if key in self._batches}

    def stations(self, key: str) -> list[StationRow]:
        batch = self._batch(key)
        return sorted(batch.stations, key=lambda row: row.station_id) if batch else []

    def hubs(self, key: str) -> list[HubRow]:
        batch = self._batch(key)
        return sorted(batch.hubs, key=lambda row: row.hub_id) if batch else []

    def hub_pairs(self, key: str) -> list[HubPairRow]:
        batch = self._batch(key)
        if batch is None:
            return []
        return sorted(batch.hub_pairs, key=lambda row: (row.origin_hub, row.destination_hub))

    def route_pairs(self, key: str) -> list[RoutePairRow]:
        batch = self._batch(key)
        if batch is None:
            return []
        return sorted(batch.route_pairs, key=lambda row: (row.origin_hub, row.destination_hub))

    def route_options(self, key: str) -> list[RouteOptionRow]:
        batch = self._batch(key)
        return sorted(batch.route_options, key=lambda row: row.arc_id) if batch else []

    def station_bikes(self, key: str) -> list[StationBikesRow]:
        batch = self._batch(key)
        return sorted(batch.station_bikes, key=lambda row: row.station_id) if batch else []

    def option_station_deltas(self, key: str) -> list[OptionStationDeltaRow]:
        batch = self._batch(key)
        if batch is None:
            return []
        return sorted(batch.deltas, key=lambda row: (row.arc_id, row.station_id))

    def drop(self, key: str) -> None:
        """What the removal of the artefact does (its rows go with it)."""
        with self._lock:
            self._batches.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._batches.clear()

    def _batch(self, key: str) -> IngestionBatch | None:
        with self._lock:
            return self._batches.get(key)
