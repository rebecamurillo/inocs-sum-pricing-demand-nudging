"""The artefact store on a real folder: working directories, the temporary name and the rename,
read-only results, an existing target reused."""

import hashlib
import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore

pytestmark = pytest.mark.integration

KEY = "k" * 64
CONTENT = b'{"stations": []}'


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalArtifactStore]:
    yield LocalArtifactStore(tmp_path)
    # A read-only folder cannot be removed with its content: make it writable for the cleanup.
    for folder, _, files in os.walk(tmp_path):
        os.chmod(folder, 0o755)
        for name in files:
            os.chmod(Path(folder) / name, 0o644)


def test_a_working_directory_is_runs_run_step_and_starts_empty(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    working = store.working_dir("run-1", StepName.AREA)

    assert working == tmp_path / "runs" / "run-1" / "area"
    assert list(working.iterdir()) == []


def test_a_working_directory_of_an_earlier_attempt_is_emptied(
    store: LocalArtifactStore,
) -> None:
    first = store.working_dir("run-1", StepName.AREA)
    (first / "stale.json").write_text("{}")

    again = store.working_dir("run-1", StepName.AREA)

    assert again == first
    assert list(again.iterdir()) == []


def test_the_outputs_move_to_the_store_with_their_hashes_and_sizes(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    working = store.working_dir("run-1", StepName.AREA)
    (working / "stations.json").write_bytes(CONTENT)

    path, files = store.store(StepName.AREA, KEY, working, ["stations.json"])

    assert path == Path("artifacts") / "area" / KEY
    assert [(f.name, f.sha256, f.bytes) for f in files] == [
        ("stations.json", hashlib.sha256(CONTENT).hexdigest(), len(CONTENT))
    ]
    assert (tmp_path / path / "stations.json").read_bytes() == CONTENT
    assert not (working / "stations.json").exists()


def test_the_folder_and_its_files_are_read_only(store: LocalArtifactStore, tmp_path: Path) -> None:
    working = store.working_dir("run-1", StepName.AREA)
    (working / "stations.json").write_bytes(CONTENT)

    path, _ = store.store(StepName.AREA, KEY, working, ["stations.json"])

    folder = tmp_path / path
    assert stat.S_IMODE(folder.stat().st_mode) == 0o555
    assert stat.S_IMODE((folder / "stations.json").stat().st_mode) == 0o444


def test_no_temporary_folder_is_left_beside_the_result(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    working = store.working_dir("run-1", StepName.AREA)
    (working / "stations.json").write_bytes(CONTENT)

    store.store(StepName.AREA, KEY, working, ["stations.json"])

    assert [item.name for item in (tmp_path / "artifacts" / "area").iterdir()] == [KEY]


def test_an_output_that_is_missing_stores_nothing(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    working = store.working_dir("run-1", StepName.HUBS)
    (working / "hubs.geojson").write_bytes(CONTENT)

    with pytest.raises(FileNotFoundError, match=r"stations_hubs\.geojson"):
        store.store(StepName.HUBS, KEY, working, ["hubs.geojson", "stations_hubs.geojson"])

    assert not (tmp_path / "artifacts" / "hubs" / KEY).exists()
    assert (working / "hubs.geojson").exists()


def test_an_existing_artefact_is_reused_and_the_working_outputs_are_discarded(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    first = store.working_dir("run-1", StepName.AREA)
    (first / "stations.json").write_bytes(CONTENT)
    store.store(StepName.AREA, KEY, first, ["stations.json"])
    second = store.working_dir("run-2", StepName.AREA)
    (second / "stations.json").write_bytes(CONTENT)

    path, files = store.store(StepName.AREA, KEY, second, ["stations.json"])

    assert path == Path("artifacts") / "area" / KEY
    assert files[0].sha256 == hashlib.sha256(CONTENT).hexdigest()
    assert not (second / "stations.json").exists()
    assert [item.name for item in (tmp_path / "artifacts" / "area").iterdir()] == [KEY]


def test_upstream_files_are_copied_writable_so_the_package_can_rewrite_them(
    store: LocalArtifactStore,
) -> None:
    area = store.working_dir("run-1", StepName.AREA)
    (area / "stations.json").write_bytes(CONTENT)
    store.store(StepName.AREA, KEY, area, ["stations.json"])
    hubs = store.working_dir("run-1", StepName.HUBS)

    store.copy_upstream(StepName.AREA, KEY, ["stations.json"], hubs)

    copied = hubs / "stations.json"
    assert copied.read_bytes() == CONTENT
    copied.write_bytes(b"{}")
    assert stat.S_IMODE(copied.stat().st_mode) & 0o200


def test_discarding_a_working_directory_removes_it_and_what_it_holds(
    store: LocalArtifactStore,
) -> None:
    working = store.working_dir("run-1", StepName.AREA)
    (working / "partial.json").write_text("{")

    store.discard(working)

    assert not working.exists()
    store.discard(working)
