import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pricing_demo.application.ports.artifacts import StoredFile
from pricing_demo.domain.runs import StepName

READ_ONLY_FILE = 0o444
READ_ONLY_FOLDER = 0o555
WRITABLE_FILE = 0o644


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class LocalArtifactStore:
    """`{data_dir}/runs/{run}/{step}/` while a step works, `{data_dir}/artifacts/{step}/{key}/`
    once it succeeded (ARCHITECTURE.md § 4.3). The store never changes an artefact: it is
    written under a temporary name, renamed into place, and read-only from then on."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def working_dir(self, run_id: str, step: StepName) -> Path:
        folder = self._data_dir / "runs" / run_id / step.value
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        return folder

    def copy_upstream(self, step: StepName, key: str, names: Sequence[str], into: Path) -> None:
        source = self._artifact_folder(step, key)
        for name in names:
            target = into / name
            # Copied, not linked: the package rewrites its inputs in place, and the stored
            # file is read-only, so the copy is made writable.
            shutil.copy2(source / name, target)
            target.chmod(WRITABLE_FILE)

    def store(
        self, step: StepName, key: str, working_dir: Path, names: Sequence[str]
    ) -> tuple[Path, tuple[StoredFile, ...]]:
        final = self._artifact_folder(step, key)
        relative = final.relative_to(self._data_dir)
        if final.exists():
            self.discard(working_dir)
            return relative, self._describe(final, names)
        missing = [name for name in names if not (working_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(f"The {step.value} step wrote no {', '.join(missing)}.")
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.parent / f"{key}.tmp-{uuid.uuid4().hex}"
        temporary.mkdir()
        try:
            for name in names:
                os.replace(working_dir / name, temporary / name)
                (temporary / name).chmod(READ_ONLY_FILE)
            try:
                os.rename(temporary, final)
            except OSError:
                # A concurrent writer renamed first: the same key names the same content.
                if not final.exists():
                    raise
                shutil.rmtree(temporary, ignore_errors=True)
            else:
                final.chmod(READ_ONLY_FOLDER)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
        return relative, self._describe(final, names)

    def read_json(self, path: str, name: str) -> Any:
        return json.loads((self._data_dir / path / name).read_text(encoding="utf-8"))

    def discard(self, working_dir: Path) -> None:
        shutil.rmtree(working_dir, ignore_errors=True)

    def _artifact_folder(self, step: StepName, key: str) -> Path:
        return self._data_dir / "artifacts" / step.value / key

    @staticmethod
    def _describe(folder: Path, names: Sequence[str]) -> tuple[StoredFile, ...]:
        return tuple(
            StoredFile(name, _hash_file(folder / name), (folder / name).stat().st_size)
            for name in names
        )
