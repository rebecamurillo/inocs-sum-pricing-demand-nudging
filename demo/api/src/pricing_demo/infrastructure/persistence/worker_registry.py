from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import Engine, func, null
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.infrastructure.persistence.tables import workers


class PostgresWorkerRegistry:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register(
        self,
        worker_id: str,
        host: str,
        pid: int,
        at: datetime,
        package_fingerprint: str | None = None,
        simulation_rule: Mapping[str, object] | None = None,
    ) -> None:
        self._upsert(worker_id, host, pid, at, at, package_fingerprint, simulation_rule)

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None = None,
        simulation_rule: Mapping[str, object] | None = None,
    ) -> None:
        self._upsert(worker_id, host, pid, started_at, at, package_fingerprint, simulation_rule)

    def _upsert(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None,
        simulation_rule: Mapping[str, object] | None,
    ) -> None:
        statement = insert(workers).values(
            id=worker_id,
            host=host,
            pid=pid,
            started_at=started_at,
            heartbeat_at=at,
            package_fingerprint=package_fingerprint,
            # SQL null, not JSON null: a heartbeat without a rule keeps the row's.
            simulation_rule=dict(simulation_rule) if simulation_rule is not None else null(),
        )
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "host": statement.excluded.host,
                "pid": statement.excluded.pid,
                "started_at": statement.excluded.started_at,
                "heartbeat_at": statement.excluded.heartbeat_at,
                # A heartbeat that knows no fingerprint or rule (the one a running step writes)
                # keeps the row's.
                "package_fingerprint": func.coalesce(
                    statement.excluded.package_fingerprint, workers.c.package_fingerprint
                ),
                "simulation_rule": func.coalesce(
                    statement.excluded.simulation_rule, workers.c.simulation_rule
                ),
            },
        )
        with self._engine.begin() as connection:
            connection.execute(statement)
