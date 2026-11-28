from collections.abc import Mapping
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
    that was deleted meanwhile (the e2e reset). A heartbeat without a fingerprint or a simulation
    rule keeps the row's."""

    def register(
        self,
        worker_id: str,
        host: str,
        pid: int,
        at: datetime,
        package_fingerprint: str | None = None,
        simulation_rule: Mapping[str, object] | None = None,
    ) -> None: ...

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        started_at: datetime,
        at: datetime,
        package_fingerprint: str | None = None,
        simulation_rule: Mapping[str, object] | None = None,
    ) -> None: ...
