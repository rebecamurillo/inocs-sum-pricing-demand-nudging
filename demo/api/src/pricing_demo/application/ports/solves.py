from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.domain.derived_result import ResultNumbers
from pricing_demo.domain.solves import Solve, SolveProvenance, SolveQuality, SolveRow


@dataclass(frozen=True)
class SolveRecord:
    """A version's `solves` row: the artefact it points to, and the solve's quality and
    provenance."""

    key: str
    quality: SolveQuality
    provenance: SolveProvenance
    created_at: datetime


@dataclass(frozen=True)
class StoredResultSummary:
    """The numbers of a solve's result for one derivation version, with the package's own
    summary record as it was written."""

    solve_key: str
    derivation_version: int
    numbers: ResultNumbers
    package_summary: Mapping[str, object] | None
    created_at: datetime


@dataclass(frozen=True)
class SolveRef:
    """A version's `solves` row named by its id, `{pricing version}.{period key}`."""

    solve_id: str
    pricing_version_id: str
    period_id: str
    key: str


class Solves(Protocol):
    """The solves of the pricing model. A solve is named by the input key of its artefact; each
    pricing version has its own `solves` row for its period, which points to that artefact."""

    def is_stored(self, key: str) -> bool:
        """True when an artefact of the `pricing_model` step with that key (and so its rows)
        is stored."""
        ...

    def store(
        self,
        artifact: Artifact,
        solve: Solve,
        pricing_version_id: str,
        period_id: str,
        created_at: datetime,
        summary: StoredResultSummary | None = None,
    ) -> None:
        """In one transaction: the artefact when none has the key, its rows and hub-pair
        gammas when none are stored, the result summary when none is stored for its key and
        derivation version, and the version's `solves` row for the period (replacing an earlier
        solve of the same version and period). Nothing is stored when any part fails."""
        ...

    def store_summary(self, summary: StoredResultSummary) -> None:
        """Add the summary unless one is stored for its key and derivation version."""
        ...

    def summary_of(self, key: str, derivation_version: int) -> StoredResultSummary | None: ...

    def package_summary_of(self, key: str) -> Mapping[str, object] | None:
        """The package's summary record kept with any derivation version of the key."""
        ...

    def link_stored(
        self, key: str, pricing_version_id: str, period_id: str, created_at: datetime
    ) -> None:
        """Give the version its `solves` row for the period, copying the quality and the
        provenance from a stored row of the same key. Raises `KeyError` when no row has it."""
        ...

    def rows(self, key: str) -> list[SolveRow]:
        """The rows of the solve, ordered by arc id."""
        ...

    def solve_key_of(self, pricing_version_id: str, period_id: str) -> str | None:
        """The input key the version's solve of the period points to."""
        ...

    def solve_of(self, pricing_version_id: str, period_id: str) -> SolveRecord | None:
        """The version's `solves` row for the period."""
        ...

    def find(self, solve_id: str) -> SolveRef | None:
        """The version and period a `solves.id` names, and the key it points to."""
        ...
