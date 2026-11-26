from datetime import datetime

from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.infrastructure.persistence.tables import workers


class PostgresWorkerRegistry:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register(self, worker_id: str, host: str, pid: int, at: datetime) -> None:
        self._upsert(worker_id, host, pid, started_at=at, at=at)

    def heartbeat(
        self, worker_id: str, host: str, pid: int, started_at: datetime, at: datetime
    ) -> None:
        self._upsert(worker_id, host, pid, started_at=started_at, at=at)

    def _upsert(
        self, worker_id: str, host: str, pid: int, started_at: datetime, at: datetime
    ) -> None:
        statement = insert(workers).values(
            id=worker_id, host=host, pid=pid, started_at=started_at, heartbeat_at=at
        )
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "host": statement.excluded.host,
                "pid": statement.excluded.pid,
                "started_at": statement.excluded.started_at,
                "heartbeat_at": statement.excluded.heartbeat_at,
            },
        )
        with self._engine.begin() as connection:
            connection.execute(statement)
