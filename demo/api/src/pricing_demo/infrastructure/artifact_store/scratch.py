import json
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.artifact_store.local import WRITABLE_FILE, _hash_file


class LocalScratchBuilds:
    """`{data_dir}/verify/{uuid}/{step}/` while `verify-build` rebuilds a version."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def create(self) -> Path:
        root = self._data_dir / "verify" / uuid.uuid4().hex
        root.mkdir(parents=True)
        return root

    def step_dir(self, root: Path, step: StepName) -> Path:
        folder = root / step.value
        folder.mkdir(parents=True)
        return folder

    def copy(self, source_dir: Path, names: Sequence[str], into: Path) -> None:
        for name in names:
            target = into / name
            shutil.copy2(source_dir / name, target)
            target.chmod(WRITABLE_FILE)

    def hashes(self, folder: Path, names: Sequence[str]) -> dict[str, str]:
        missing = [name for name in names if not (folder / name).is_file()]
        if missing:
            raise FileNotFoundError(f"The step wrote no {', '.join(missing)}.")
        return {name: _hash_file(folder / name) for name in names}

    def read_json(self, folder: Path, name: str) -> Any:
        return json.loads((folder / name).read_text(encoding="utf-8"))

    def remove(self, root: Path) -> None:
        shutil.rmtree(root, ignore_errors=True)
