from datetime import datetime

from sqlalchemy import Engine, func
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
    ) -> None:
        self._upsert(worker_id, host, pid, at, at, package_fingerprint)

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None = None,
    ) -> None:
        self._upsert(worker_id, host, pid, started_at, at, package_fingerprint)

    def _upsert(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None,
    ) -> None:
        statement = insert(workers).values(
            id=worker_id,
            host=host,
            pid=pid,
            started_at=started_at,
            heartbeat_at=at,
            package_fingerprint=package_fingerprint,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "host": statement.excluded.host,
                "pid": statement.excluded.pid,
                "started_at": statement.excluded.started_at,
                "heartbeat_at": statement.excluded.heartbeat_at,
                # A heartbeat that knows no fingerprint (the one a running step writes) keeps
                # the row's.
                "package_fingerprint": func.coalesce(
                    statement.excluded.package_fingerprint, workers.c.package_fingerprint
                ),
            },
        )
        with self._engine.begin() as connection:
            connection.execute(statement)
