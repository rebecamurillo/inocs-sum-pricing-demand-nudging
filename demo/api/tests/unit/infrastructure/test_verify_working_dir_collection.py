"""The collection of working directories leaves the folder of a running `verify`: a re-solve
outlasts the worker's collection interval, and `runs/verify-{uuid}/` is no run's."""

from pathlib import Path

from pricing_demo.domain.runs import StepName
from pricing_demo.domain.solve_verification import VERIFY_RUN_PREFIX
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore


def test_the_folder_of_a_running_verify_is_not_collected(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    verifying = store.working_dir(f"{VERIFY_RUN_PREFIX}abc", StepName.PRICING_MODEL)
    (verifying / "Instance_1.json").write_text("{}")
    store.working_dir("gone", StepName.PRICING_MODEL)

    store.remove_working_dirs_except(set())

    assert [item.name for item in (tmp_path / "runs").iterdir()] == [f"{VERIFY_RUN_PREFIX}abc"]
    assert (verifying / "Instance_1.json").is_file()
