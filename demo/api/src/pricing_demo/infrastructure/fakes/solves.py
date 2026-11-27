import threading
from collections.abc import Collection
from datetime import datetime

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.solves import SolveRecord
from pricing_demo.domain.solves import Solve, SolveOd, SolveRow
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts


class InMemorySolves:
    """The solves in dicts; passes the same contract suite as the PostgreSQL adapter. The
    artefacts are the ones the executors store in `InMemoryArtifacts`, which this one tells
    which keys a solve still references."""

    def __init__(self, artifacts: InMemoryArtifacts) -> None:
        self._artifacts = artifacts
        self._rows: dict[str, tuple[tuple[SolveRow, ...], tuple[SolveOd, ...]]] = {}
        self._versions: dict[tuple[str, str], SolveRecord] = {}
        self._lock = threading.Lock()
        artifacts.attach_solves(self)

    def is_stored(self, key: str) -> bool:
        with self._lock:
            return key in self._rows

    def store(
        self,
        artifact: Artifact,
        solve: Solve,
        pricing_version_id: str,
        period_id: str,
        created_at: datetime,
    ) -> None:
        ids = [row.arc_id for row in solve.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("A solve has one row per option.")
        self._artifacts.add(artifact)
        with self._lock:
            self._rows.setdefault(artifact.input_key, (tuple(solve.rows), tuple(solve.ods)))
            self._versions[(pricing_version_id, period_id)] = SolveRecord(
                artifact.input_key, solve.quality, solve.provenance, created_at
            )

    def link_stored(
        self, key: str, pricing_version_id: str, period_id: str, created_at: datetime
    ) -> None:
        with self._lock:
            source = next((record for record in self._versions.values() if record.key == key), None)
            if source is None:
                raise KeyError(key)
            self._versions[(pricing_version_id, period_id)] = SolveRecord(
                key, source.quality, source.provenance, created_at
            )

    def rows(self, key: str) -> list[SolveRow]:
        with self._lock:
            found = self._rows.get(key)
        return sorted(found[0], key=lambda row: row.arc_id) if found else []

    def solve_key_of(self, pricing_version_id: str, period_id: str) -> str | None:
        record = self.solve_of(pricing_version_id, period_id)
        return None if record is None else record.key

    def solve_of(self, pricing_version_id: str, period_id: str) -> SolveRecord | None:
        with self._lock:
            return self._versions.get((pricing_version_id, period_id))

    # What the artefacts' collection and the deletion of a version do; the port has no such
    # methods.
    def referenced_keys(self) -> set[str]:
        with self._lock:
            return {record.key for record in self._versions.values()}

    def drop_key(self, key: str) -> None:
        with self._lock:
            self._rows.pop(key, None)

    def drop_version(self, version_ids: Collection[str]) -> None:
        with self._lock:
            for version_period in [item for item in self._versions if item[0] in version_ids]:
                del self._versions[version_period]
