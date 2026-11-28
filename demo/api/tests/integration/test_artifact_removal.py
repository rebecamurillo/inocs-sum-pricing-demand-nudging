"""The removal of a stored artefact folder on a real folder: only one artefact's folder, and
never a partial folder left under the key's name."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore

pytestmark = pytest.mark.integration

KEY = "r" * 64


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalArtifactStore]:
    yield LocalArtifactStore(tmp_path)
    # A read-only folder cannot be removed with its content: make it writable for the cleanup.
    for folder, _, files in os.walk(tmp_path):
        os.chmod(folder, 0o755)
        for name in files:
            os.chmod(Path(folder) / name, 0o644)


def stored(store: LocalArtifactStore, key: str) -> Path:
    working = store.working_dir("run-x", StepName.AREA)
    (working / "stations.json").write_bytes(b'{"stations": []}')
    path, _ = store.store(StepName.AREA, key, working, ["stations.json"])
    return path


def test_a_step_folder_is_refused_and_its_artefacts_stay(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    path = stored(store, KEY)

    with pytest.raises(ValueError, match="artefact folder"):
        store.remove_artifact("artifacts/area")

    assert (tmp_path / path).is_dir()


def test_the_removal_leaves_nothing_in_the_step_folder_and_the_other_artefacts_stay(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    gone = stored(store, KEY)
    kept = stored(store, "s" * 64)

    store.remove_artifact(str(gone))

    assert [item.name for item in (tmp_path / "artifacts" / "area").iterdir()] == [kept.name]
