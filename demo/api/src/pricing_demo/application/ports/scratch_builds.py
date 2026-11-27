from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from pricing_demo.domain.runs import StepName


class ScratchBuilds(Protocol):
    """The scratch folders of `verify-build`: a rebuild's files, which never reach the store."""

    def create(self) -> Path:
        """A new, empty `verify/{uuid}/` under the data directory."""
        ...

    def step_dir(self, root: Path, step: StepName) -> Path:
        """`{root}/{step}/`, created empty."""
        ...

    def copy(self, source_dir: Path, names: Sequence[str], into: Path) -> None:
        """Writable copies of the named files of `source_dir` in `into`."""
        ...

    def hashes(self, folder: Path, names: Sequence[str]) -> dict[str, str]:
        """The sha256 of each named file; a missing file raises `FileNotFoundError` naming it."""
        ...

    def read_json(self, folder: Path, name: str) -> Any:
        """The parsed content of the file `name` of `folder`."""
        ...

    def remove(self, root: Path) -> None:
        """Remove the folder and everything in it; a missing folder is fine."""
        ...
