from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pricing_demo.application.ports.artifacts import StoredFile
from pricing_demo.domain.runs import StepName


class ArtifactFiles(Protocol):
    """The file store of the worker: working directories and read-only artefact folders."""

    def working_dir(self, run_id: str, step: StepName) -> Path:
        """`runs/{run}/{step}/` under the data directory, created empty (an earlier attempt's
        files are removed)."""
        ...

    def copy_upstream(self, step: StepName, key: str, names: Sequence[str], into: Path) -> None:
        """Copy the named files of the artefact `{step}/{key}` into `into`."""
        ...

    def store(
        self, step: StepName, key: str, working_dir: Path, names: Sequence[str]
    ) -> tuple[Path, tuple[StoredFile, ...]]:
        """Move the named outputs to `artifacts/{step}/{key}/` through a temporary name and a
        rename, make the folder and its files read-only, and return the folder (relative to
        the data directory) with each file's sha256 and size. When the folder exists the
        working outputs are discarded and the existing files are described: the same key
        names the same content."""
        ...

    def discard(self, working_dir: Path) -> None: ...
