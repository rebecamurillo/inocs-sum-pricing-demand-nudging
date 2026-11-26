from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WorkerRow:
    id: str
    host: str
    pid: int
    started_at: datetime
    heartbeat_at: datetime


class InMemoryWorkerRegistry:
    """The `workers` rows in a dict; passes the same contract suite as the PostgreSQL one."""

    def __init__(self) -> None:
        self.rows: dict[str, WorkerRow] = {}

    def register(self, worker_id: str, host: str, pid: int, at: datetime) -> None:
        self.rows[worker_id] = WorkerRow(worker_id, host, pid, started_at=at, heartbeat_at=at)

    def heartbeat(
        self, worker_id: str, host: str, pid: int, started_at: datetime, at: datetime
    ) -> None:
        self.rows[worker_id] = WorkerRow(worker_id, host, pid, started_at, heartbeat_at=at)

    def delete(self, worker_id: str) -> None:
        """What the e2e reset does to the table."""
        self.rows.pop(worker_id, None)
