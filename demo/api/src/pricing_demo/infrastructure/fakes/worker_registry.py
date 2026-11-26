from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WorkerRow:
    id: str
    host: str
    pid: int
    started_at: datetime
    heartbeat_at: datetime
    package_fingerprint: str | None = None


class InMemoryWorkerRegistry:
    """The `workers` rows in a dict; passes the same contract suite as the PostgreSQL one."""

    def __init__(self) -> None:
        self.rows: dict[str, WorkerRow] = {}

    def register(
        self,
        worker_id: str,
        host: str,
        pid: int,
        at: datetime,
        package_fingerprint: str | None = None,
    ) -> None:
        self.rows[worker_id] = WorkerRow(
            worker_id, host, pid, at, at, package_fingerprint=package_fingerprint
        )

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None = None,
    ) -> None:
        # A heartbeat that knows no fingerprint (the one a running step writes) keeps the row's.
        known = self.rows.get(worker_id)
        kept = package_fingerprint or (known.package_fingerprint if known else None)
        self.rows[worker_id] = WorkerRow(
            worker_id, host, pid, started_at, at, package_fingerprint=kept
        )

    def delete(self, worker_id: str) -> None:
        """What the e2e reset does to the table."""
        self.rows.pop(worker_id, None)
