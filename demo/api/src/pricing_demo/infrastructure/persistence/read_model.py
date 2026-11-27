from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, Engine, Table, delete, insert, select, update

from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.domain.read_model import HubPairRow, HubRow, RoutePairRow, StationRow
from pricing_demo.infrastructure.persistence.tables import (
    artifacts,
    hub_pairs,
    hubs,
    option_station_deltas,
    route_options,
    route_pairs,
    station_bikes,
    station_hubs,
    stations,
)

BATCH_SIZE = 1000


def _insert_all(connection: Connection, table: Table, values: Sequence[dict[str, Any]]) -> None:
    for start in range(0, len(values), BATCH_SIZE):
        connection.execute(insert(table), list(values[start : start + BATCH_SIZE]))


class PostgresReadModel:
    """The read-model tables. The ingestion is one transaction: a failure in any table, or in
    the update of the artefact, leaves none of the rows and no `ingested_at`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ingest(self, batch: IngestionBatch) -> None:
        key = batch.input_key
        with self._engine.begin() as connection:
            # Two runs that stored the same key ingest it one after the other: the second
            # replaces the first's rows instead of failing on their primary keys.
            connection.execute(
                select(artifacts.c.input_key).where(artifacts.c.input_key == key).with_for_update()
            )
            for table, column in _KEYS:
                connection.execute(delete(table).where(table.c[column] == key))
            _insert_all(
                connection,
                stations,
                [
                    {
                        "stations_key": key,
                        "station_id": row.station_id,
                        "kind": row.kind,
                        "name": row.name,
                        "lat": row.lat,
                        "lon": row.lon,
                    }
                    for row in batch.stations
                ],
            )
            _insert_all(
                connection,
                hubs,
                [
                    {
                        "hubs_key": key,
                        "hub_id": row.hub_id,
                        "label": row.label,
                        "lat": row.lat,
                        "lon": row.lon,
                        "outline": dict(row.outline) if row.outline is not None else None,
                        "pt_station_ids": list(row.pt_station_ids),
                        "bike_station_ids": list(row.bike_station_ids),
                        "lines": list(row.lines),
                    }
                    for row in batch.hubs
                ],
            )
            _insert_all(
                connection,
                station_hubs,
                [
                    {"hubs_key": key, "station_id": row.station_id, "hub_id": row.hub_id}
                    for row in batch.station_hubs
                ],
            )
            _insert_all(
                connection,
                hub_pairs,
                [
                    {
                        "instance_key": key,
                        "origin_hub": row.origin_hub,
                        "destination_hub": row.destination_hub,
                        "demand": row.demand,
                        "euclid_dist_m": row.euclid_dist_m,
                    }
                    for row in batch.hub_pairs
                ],
            )
            _insert_all(
                connection,
                route_pairs,
                [
                    {
                        "instance_key": key,
                        "origin_hub": row.origin_hub,
                        "destination_hub": row.destination_hub,
                    }
                    for row in batch.route_pairs
                ],
            )
            _insert_all(
                connection,
                route_options,
                [
                    {
                        "instance_key": key,
                        "arc_id": row.arc_id,
                        "origin_hub": row.origin_hub,
                        "destination_hub": row.destination_hub,
                        "mode": row.mode,
                        "total_travel_time_s": row.total_travel_time_s,
                        "total_transfer_time_s": row.total_transfer_time_s,
                        "total_distance_m": row.total_distance_m,
                        "legs": [
                            {
                                "mode": leg.mode,
                                "duration_s": leg.duration_s,
                                "distance_m": leg.distance_m,
                                "line_kind": leg.line_kind,
                            }
                            for leg in row.legs
                        ],
                        "geometry": row.geometry,
                        "bike_legs": row.bike_legs,
                    }
                    for row in batch.route_options
                ],
            )
            _insert_all(
                connection,
                station_bikes,
                [
                    {
                        "instance_key": key,
                        "station_id": row.station_id,
                        "capacity": row.capacity,
                        "inventory_start": row.inventory_start,
                    }
                    for row in batch.station_bikes
                ],
            )
            _insert_all(
                connection,
                option_station_deltas,
                [
                    {
                        "instance_key": key,
                        "arc_id": row.arc_id,
                        "station_id": row.station_id,
                        "delta": row.delta,
                    }
                    for row in batch.deltas
                ],
            )
            connection.execute(
                update(artifacts)
                .where(artifacts.c.input_key == key)
                .values(counts=dict(batch.counts), ingested_at=datetime.now(UTC))
            )

    def is_ingested(self, key: str) -> bool:
        query = select(artifacts.c.ingested_at).where(artifacts.c.input_key == key)
        with self._engine.connect() as connection:
            return connection.execute(query).scalar() is not None

    def counts_of(self, keys: Collection[str]) -> Mapping[str, Mapping[str, Any]]:
        if not keys:
            return {}
        query = select(artifacts.c.input_key, artifacts.c.counts).where(
            artifacts.c.input_key.in_(list(keys)), artifacts.c.ingested_at.is_not(None)
        )
        with self._engine.connect() as connection:
            return {row[0]: row[1] for row in connection.execute(query)}

    def stations(self, key: str) -> list[StationRow]:
        query = (
            select(stations).where(stations.c.stations_key == key).order_by(stations.c.station_id)
        )
        return [
            StationRow(row.station_id, row.kind, row.name, row.lat, row.lon)
            for row in self._rows(query)
        ]

    def hubs(self, key: str) -> list[HubRow]:
        query = select(hubs).where(hubs.c.hubs_key == key).order_by(hubs.c.hub_id)
        return [
            HubRow(
                row.hub_id,
                row.label,
                row.lat,
                row.lon,
                row.outline,
                tuple(row.pt_station_ids),
                tuple(row.bike_station_ids),
                tuple(row.lines),
            )
            for row in self._rows(query)
        ]

    def hub_pairs(self, key: str) -> list[HubPairRow]:
        query = (
            select(hub_pairs)
            .where(hub_pairs.c.instance_key == key)
            .order_by(hub_pairs.c.origin_hub, hub_pairs.c.destination_hub)
        )
        return [
            HubPairRow(row.origin_hub, row.destination_hub, row.demand, row.euclid_dist_m)
            for row in self._rows(query)
        ]

    def route_pairs(self, key: str) -> list[RoutePairRow]:
        query = (
            select(route_pairs)
            .where(route_pairs.c.instance_key == key)
            .order_by(route_pairs.c.origin_hub, route_pairs.c.destination_hub)
        )
        return [RoutePairRow(row.origin_hub, row.destination_hub) for row in self._rows(query)]

    def _rows(self, query: Any) -> Iterable[Any]:
        with self._engine.connect() as connection:
            return connection.execute(query).all()


_KEYS: tuple[tuple[Table, str], ...] = (
    (option_station_deltas, "instance_key"),
    (station_bikes, "instance_key"),
    (route_options, "instance_key"),
    (hub_pairs, "instance_key"),
    (route_pairs, "instance_key"),
    (station_hubs, "hubs_key"),
    (hubs, "hubs_key"),
    (stations, "stations_key"),
)
