from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, null, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.solves import SolveRecord, SolveRef, StoredResultSummary
from pricing_demo.domain.derived_result import ResultNumbers
from pricing_demo.domain.pricing_keys import solve_id
from pricing_demo.domain.solves import Solve, SolveProvenance, SolveQuality, SolveRow
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.tables import (
    artifacts,
    instance_periods,
    result_summaries,
    solve_ods,
    solve_rows,
    solves,
)

BATCH_SIZE = 1000

_QUALITY = (
    "solver_status",
    "solver_status_name",
    "objective_value",
    "gap_pct",
    "solution_time_s",
    "sol_count",
    "time_limit_reached",
)
_PROVENANCE = (
    "gurobi_version",
    "licence_kind",
    "solver_parameters",
    "package_fingerprint",
    "demonstrator_version",
    "dependency_lock_sha256",
    "platform",
)


def _record(row: Any) -> SolveRecord:
    return SolveRecord(
        row.input_key,
        SolveQuality(**{name: getattr(row, name) for name in _QUALITY}),
        SolveProvenance(**{name: getattr(row, name) for name in _PROVENANCE}),
        row.created_at,
    )


class PostgresSolves:
    """The solves. A solve is stored in one transaction: its artefact, its rows and the
    version's `solves` row, or none of them."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_stored(self, key: str) -> bool:
        query = select(artifacts.c.input_key).where(
            artifacts.c.input_key == key, artifacts.c.step == "pricing_model"
        )
        with self._engine.connect() as connection:
            return connection.execute(query).scalar() is not None

    def store(
        self,
        artifact: Artifact,
        solve: Solve,
        pricing_version_id: str,
        period_id: str,
        created_at: datetime,
        summary: StoredResultSummary | None = None,
    ) -> None:
        key = artifact.input_key
        with self._engine.begin() as connection:
            PostgresArtifacts.add_in(connection, artifact)
            # Another run that solved the same key first stored the rows: they are the
            # solve's (the same key names the same content).
            stored = connection.execute(
                select(solve_rows.c.arc_id).where(solve_rows.c.solve_key == key).limit(1)
            ).scalar()
            if stored is None:
                self._insert_all(
                    connection,
                    solve_rows,
                    [
                        {
                            "solve_key": key,
                            "arc_id": row.arc_id,
                            "origin_hub": row.origin_hub,
                            "destination_hub": row.destination_hub,
                            "type": row.type,
                            "nu": row.nu,
                            "flow": row.flow,
                            "bike_price": row.bike_price,
                            "total_price": row.total_price,
                            "z_value": row.z_value,
                            "relaxation_difference": row.relaxation_difference,
                        }
                        for row in solve.rows
                    ],
                )
                self._insert_all(
                    connection,
                    solve_ods,
                    [
                        {
                            "solve_key": key,
                            "origin_hub": item.origin_hub,
                            "destination_hub": item.destination_hub,
                            "gamma": item.gamma,
                        }
                        for item in solve.ods
                    ],
                )
            if summary is not None:
                self._insert_summary(connection, summary)
            self._upsert_version_row(
                connection,
                pricing_version_id,
                period_id,
                SolveRecord(key, solve.quality, solve.provenance, created_at),
            )

    def store_summary(self, summary: StoredResultSummary) -> None:
        with self._engine.begin() as connection:
            self._insert_summary(connection, summary)

    def summary_of(self, key: str, derivation_version: int) -> StoredResultSummary | None:
        query = select(result_summaries).where(
            result_summaries.c.solve_key == key,
            result_summaries.c.derivation_version == derivation_version,
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        if row is None:
            return None
        return StoredResultSummary(
            row.solve_key,
            row.derivation_version,
            ResultNumbers.from_record(row.numbers),
            row.package_summary,
            row.created_at,
        )

    def package_summary_of(self, key: str) -> Mapping[str, object] | None:
        query = (
            select(result_summaries.c.package_summary)
            .where(
                result_summaries.c.solve_key == key,
                result_summaries.c.package_summary.is_not(None),
            )
            .order_by(result_summaries.c.derivation_version)
            .limit(1)
        )
        with self._engine.connect() as connection:
            found: Mapping[str, object] | None = connection.execute(query).scalar()
        return found

    def link_stored(
        self, key: str, pricing_version_id: str, period_id: str, created_at: datetime
    ) -> None:
        with self._engine.begin() as connection:
            source = connection.execute(
                select(solves).where(solves.c.input_key == key).limit(1)
            ).first()
            if source is None:
                raise KeyError(key)
            record = _record(source)
            self._upsert_version_row(
                connection,
                pricing_version_id,
                period_id,
                SolveRecord(key, record.quality, record.provenance, created_at),
            )

    def rows(self, key: str) -> list[SolveRow]:
        query = (
            select(solve_rows).where(solve_rows.c.solve_key == key).order_by(solve_rows.c.arc_id)
        )
        with self._engine.connect() as connection:
            return [
                SolveRow(
                    row.arc_id,
                    row.origin_hub,
                    row.destination_hub,
                    row.type,
                    row.nu,
                    row.flow,
                    row.bike_price,
                    row.total_price,
                    row.z_value,
                    row.relaxation_difference,
                )
                for row in connection.execute(query)
            ]

    def solve_key_of(self, pricing_version_id: str, period_id: str) -> str | None:
        record = self.solve_of(pricing_version_id, period_id)
        return None if record is None else record.key

    def solve_of(self, pricing_version_id: str, period_id: str) -> SolveRecord | None:
        query = select(solves).where(
            solves.c.pricing_version_id == pricing_version_id, solves.c.period_id == period_id
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        return None if row is None else _record(row)

    def find(self, solve_id: str) -> SolveRef | None:
        query = select(solves.c.pricing_version_id, solves.c.period_id, solves.c.input_key).where(
            solves.c.id == solve_id
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        return None if row is None else SolveRef(solve_id, row[0], row[1], row[2])

    @staticmethod
    def _insert_summary(connection: Any, summary: StoredResultSummary) -> None:
        connection.execute(
            insert(result_summaries)
            .values(
                solve_key=summary.solve_key,
                derivation_version=summary.derivation_version,
                numbers=summary.numbers.record(),
                # SQL null, not the JSON null a Python None would be stored as.
                package_summary=summary.package_summary
                if summary.package_summary is not None
                else null(),
                objective_residual=summary.numbers.objective_residual,
                created_at=summary.created_at,
            )
            .on_conflict_do_nothing(constraint="pk_result_summaries")
        )

    @staticmethod
    def _insert_all(connection: Any, table: Any, values: list[dict[str, Any]]) -> None:
        for start in range(0, len(values), BATCH_SIZE):
            connection.execute(insert(table), values[start : start + BATCH_SIZE])

    @staticmethod
    def _upsert_version_row(
        connection: Any, pricing_version_id: str, period_id: str, record: SolveRecord
    ) -> None:
        period_key = connection.execute(
            select(instance_periods.c.key).where(instance_periods.c.id == period_id)
        ).scalar()
        values = {
            "id": solve_id(pricing_version_id, period_key or period_id),
            "pricing_version_id": pricing_version_id,
            "period_id": period_id,
            "input_key": record.key,
            **{name: getattr(record.quality, name) for name in _QUALITY},
            **{
                name: dict(getattr(record.provenance, name))
                if name == "solver_parameters"
                else getattr(record.provenance, name)
                for name in _PROVENANCE
            },
            "created_at": record.created_at,
        }
        statement = insert(solves).values(values)
        connection.execute(
            statement.on_conflict_do_update(
                constraint="uq_solves_pricing_version_id",
                set_={name: statement.excluded[name] for name in values if name != "id"},
            )
        )
