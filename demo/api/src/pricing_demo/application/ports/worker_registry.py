from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WorkerIdentity:
    id: str
    host: str
    pid: int
    started_at: datetime


class WorkerRegistry(Protocol):
    """The `workers` rows. Both calls write the whole row, so a heartbeat re-creates a row
    that was deleted meanwhile (the e2e reset)."""

    def register(
        self,
        worker_id: str,
        host: str,
        pid: int,
        at: datetime,
        package_fingerprint: str | None = None,
    ) -> None: ...

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None = None,
    ) -> None: ...
