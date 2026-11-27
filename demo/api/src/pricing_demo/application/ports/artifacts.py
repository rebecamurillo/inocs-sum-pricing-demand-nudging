from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from pricing_demo.domain.runs import StepName


@dataclass(frozen=True)
class StoredFile:
    name: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class Artifact:
    """The outputs of one step, named by its input key. `path` is relative to the data
    directory."""

    input_key: str
    step: StepName
    inputs: Mapping[str, Any]
    files: tuple[StoredFile, ...]
    path: str
    package_fingerprint: str
    created_at: datetime
    # The run that produced it, and the counts that run's step reported (the ingestion adds to
    # them what only the stored files tell).
    run_id: str | None = None
    reported_counts: Mapping[str, Any] = field(default_factory=dict)


class Artifacts(Protocol):
    """The `artifacts` rows and the links of instance versions to them."""

    def stored_keys(self, keys: Collection[str]) -> set[str]:
        """The keys among `keys` that have an artefact."""
        ...

    def get(self, key: str) -> Artifact | None: ...

    def add(self, artifact: Artifact) -> None:
        """Insert the artefact; one already stored under the key is left as it is."""
        ...

    def link(self, version_id: str, step: StepName, period_id: str | None, key: str) -> None:
        """Make `key` the artefact of the version's step and period (insert or replace)."""
        ...

    def links_of(self, version_id: str) -> Mapping[StepName, str]:
        """The key linked to each step of the version."""
        ...
