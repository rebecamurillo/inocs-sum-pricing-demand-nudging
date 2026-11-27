from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, Engine, delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.application.ports.simulations import (
    LinkedSimulation,
    SimulationLink,
    StoredSimulation,
)
from pricing_demo.infrastructure.persistence.tables import (
    pricing_version_simulations,
    simulation_choices,
    simulation_modes,
    simulation_pairs,
    simulation_stations,
    simulations,
)

BATCH_SIZE = 1000


def _insert_all(connection: Connection, table: Any, values: list[dict[str, Any]]) -> None:
    for start in range(0, len(values), BATCH_SIZE):
        connection.execute(insert(table), values[start : start + BATCH_SIZE])


class PostgresSimulations:
    """The simulations. Storing is one transaction: the new simulations with their child rows
    and the links, or none of them."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_stored(self, key: str) -> bool:
        query = select(simulations.c.simulation_key).where(simulations.c.simulation_key == key)
        with self._engine.connect() as connection:
            return connection.execute(query).scalar() is not None

    def store(self, new: Sequence[StoredSimulation], links: Sequence[SimulationLink]) -> None:
        with self._engine.begin() as connection:
            for simulation in new:
                self._insert(connection, simulation)
            for link in links:
                values = {
                    "pricing_version_id": link.pricing_version_id,
                    "period_id": link.period_id,
                    "price_scheme": link.price_scheme,
                    "rule_id": link.rule_id,
                    "rule_version": link.rule_version,
                    "simulation_key": link.simulation_key,
                    "created_at": link.created_at,
                }
                statement = insert(pricing_version_simulations).values(values)
                connection.execute(
                    statement.on_conflict_do_update(
                        constraint="pk_pricing_version_simulations",
                        set_={
                            "simulation_key": statement.excluded.simulation_key,
                            "created_at": statement.excluded.created_at,
                        },
                    )
                )

    def links_of(self, pricing_version_id: str) -> list[SimulationLink]:
        table = pricing_version_simulations
        query = (
            select(table)
            .where(table.c.pricing_version_id == pricing_version_id)
            .order_by(
                table.c.period_id, table.c.price_scheme, table.c.rule_id, table.c.rule_version
            )
        )
        with self._engine.connect() as connection:
            return [
                SimulationLink(
                    row.pricing_version_id,
                    row.period_id,
                    row.price_scheme,
                    row.rule_id,
                    row.rule_version,
                    row.simulation_key,
                    row.created_at,
                )
                for row in connection.execute(query)
            ]

    def linked_of(self, pricing_version_id: str) -> list[LinkedSimulation]:
        table = pricing_version_simulations
        query = (
            select(table, simulations.c.rule_parameters)
            .join(simulations, simulations.c.simulation_key == table.c.simulation_key)
            .where(table.c.pricing_version_id == pricing_version_id)
            .order_by(
                table.c.period_id, table.c.price_scheme, table.c.rule_id, table.c.rule_version
            )
        )
        with self._engine.connect() as connection:
            return [
                LinkedSimulation(
                    row.pricing_version_id,
                    row.period_id,
                    row.price_scheme,
                    row.rule_id,
                    row.rule_version,
                    dict(row.rule_parameters),
                    row.simulation_key,
                    row.created_at,
                )
                for row in connection.execute(query)
            ]

    def remove_unlinked(self) -> int:
        with self._engine.begin() as connection:
            result = connection.execute(
                delete(simulations).where(
                    ~exists().where(
                        pricing_version_simulations.c.simulation_key == simulations.c.simulation_key
                    )
                )
            )
            return result.rowcount

    @staticmethod
    def _insert(connection: Connection, simulation: StoredSimulation) -> None:
        key, out = simulation.key, simulation.outputs
        inserted = connection.execute(
            insert(simulations)
            .values(
                simulation_key=key,
                instance_key=simulation.instance_key,
                period_id=simulation.period_id,
                rule_id=out.rule_id,
                rule_version=out.rule_version,
                rule_parameters=dict(out.parameters),
                price_scheme=simulation.scheme_kind,
                solve_key=simulation.solve_key,
                flat_price_kind=simulation.flat_price_kind,
                flat_price_amount_chf=simulation.flat_price_amount_chf,
                pt_fare_chf=simulation.pt_fare_chf,
                car_parking_fee_chf=simulation.car_parking_fee_chf,
                travellers=sum(out.travellers_per_mode.values()) + out.unserved,
                displaced=out.displaced,
                unserved=out.unserved,
                bike_rides=out.bike_rides,
                bike_revenue_chf=out.bike_revenue_chf,
                stations_empty=len(out.stations_empty),
                stations_full=len(out.stations_full),
                adapter=simulation.adapter,
                package_fingerprint=simulation.package_fingerprint,
                demonstrator_version=simulation.demonstrator_version,
                duration_s=simulation.duration_s,
                created_at=simulation.created_at,
            )
            .on_conflict_do_nothing(index_elements=["simulation_key"])
            .returning(simulations.c.simulation_key)
        ).first()
        if inserted is None:
            # Stored by another run first: the same key names the same content.
            return
        _insert_all(
            connection,
            simulation_modes,
            [
                {"simulation_key": key, "mode": mode, "travellers": count}
                for mode, count in out.travellers_per_mode.items()
            ],
        )
        _insert_all(
            connection,
            simulation_choices,
            [
                {
                    "simulation_key": key,
                    "origin_hub": option.origin_hub,
                    "destination_hub": option.destination_hub,
                    "arc_id": option.arc_id,
                    "mode": option.mode,
                    "travellers": option.travellers,
                    "price_chf": option.price_paid_chf,
                    "displaced": option.displaced,
                }
                for option in out.options
            ],
        )
        _insert_all(
            connection,
            simulation_pairs,
            [
                {
                    "simulation_key": key,
                    "origin_hub": origin,
                    "destination_hub": destination,
                    "unserved": count,
                }
                for origin, destination, count in out.unserved_per_pair
            ],
        )
        _insert_all(
            connection,
            simulation_stations,
            [
                {
                    "simulation_key": key,
                    "station_id": station.station_id,
                    "bikes_end": station.bikes,
                    "empty": station.station_id in out.stations_empty,
                    "full": station.station_id in out.stations_full,
                }
                for station in out.stations_end
            ],
        )
