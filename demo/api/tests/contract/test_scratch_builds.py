"""The ScratchBuilds port: one suite, run against the local adapter and the fake."""

import hashlib
import json
from pathlib import Path

import pytest

from pricing_demo.application.ports.scratch_builds import ScratchBuilds
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.artifact_store.scratch import LocalScratchBuilds
from pricing_demo.infrastructure.fakes.scratch_builds import FakeScratchBuilds


@pytest.fixture(params=["local", "fake"])
def scratch(request: pytest.FixtureRequest, tmp_path: Path) -> ScratchBuilds:
    if request.param == "local":
        return LocalScratchBuilds(tmp_path / "data")
    return FakeScratchBuilds(tmp_path / "data")


def test_create_makes_an_empty_folder_under_verify(scratch: ScratchBuilds, tmp_path: Path) -> None:
    root = scratch.create()

    assert root.is_dir()
    assert list(root.iterdir()) == []
    assert root.parent == tmp_path / "data" / "verify"


def test_each_creation_is_a_new_folder(scratch: ScratchBuilds) -> None:
    assert scratch.create() != scratch.create()


def test_a_step_folder_is_empty_and_inside_the_root(scratch: ScratchBuilds) -> None:
    root = scratch.create()

    folder = scratch.step_dir(root, StepName.HUBS)

    assert folder.parent == root
    assert folder.is_dir()
    assert list(folder.iterdir()) == []


def test_copy_makes_writable_copies(scratch: ScratchBuilds) -> None:
    root = scratch.create()
    source, target = scratch.step_dir(root, StepName.AREA), scratch.step_dir(root, StepName.HUBS)
    (source / "stations.json").write_text("{}")
    (source / "other.json").write_text("[]")
    (source / "stations.json").chmod(0o444)

    scratch.copy(source, ["stations.json"], target)

    assert [item.name for item in target.iterdir()] == ["stations.json"]
    (target / "stations.json").write_text("changed")
    assert (source / "stations.json").read_text() == "{}"


def test_hashes_are_the_sha256_of_the_bytes(scratch: ScratchBuilds) -> None:
    folder = scratch.step_dir(scratch.create(), StepName.AREA)
    (folder / "a.json").write_bytes(b"known bytes")

    assert scratch.hashes(folder, ["a.json"]) == {
        "a.json": hashlib.sha256(b"known bytes").hexdigest()
    }


def test_a_missing_file_is_named_in_the_error(scratch: ScratchBuilds) -> None:
    folder = scratch.step_dir(scratch.create(), StepName.AREA)

    with pytest.raises(FileNotFoundError, match=r"gone\.json"):
        scratch.hashes(folder, ["gone.json"])


def test_read_json_parses_the_file(scratch: ScratchBuilds) -> None:
    folder = scratch.step_dir(scratch.create(), StepName.AREA)
    (folder / "a.json").write_text(json.dumps({"k": [1]}))

    assert scratch.read_json(folder, "a.json") == {"k": [1]}


def test_remove_deletes_the_root_and_a_second_removal_is_fine(scratch: ScratchBuilds) -> None:
    root = scratch.create()
    (scratch.step_dir(root, StepName.AREA) / "a.json").write_text("{}")

    scratch.remove(root)
    scratch.remove(root)

    assert not root.exists()
