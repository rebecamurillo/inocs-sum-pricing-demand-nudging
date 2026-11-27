import pytest

from pricing_demo.application.ports.artifacts import Artifact, StoredFile
from pricing_demo.application.use_cases.collect_unreferenced import CollectUnreferenced
from pricing_demo.domain.runs import RunState, StepName
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from tests.support.builds import RecordingFiles
from tests.support.runs import T0, make_run


def artifact(key: str, run_id: str | None = None) -> Artifact:
    return Artifact(
        input_key=key,
        step=StepName.AREA,
        inputs={},
        files=(StoredFile("a.json", "ab" * 32, 1),),
        path=f"artifacts/area/{key}",
        package_fingerprint=FAKE_FINGERPRINT.fingerprint,
        created_at=T0,
        run_id=run_id,
    )


def collector(
    artifacts: InMemoryArtifacts, files: RecordingFiles, runs: InMemoryRunRepository
) -> CollectUnreferenced:
    return CollectUnreferenced(artifacts, files, runs)


def test_unreferenced_artefacts_go_with_their_folders_and_linked_ones_stay() -> None:
    artifacts, files, runs = InMemoryArtifacts(), RecordingFiles(), InMemoryRunRepository()
    for key in ("kept", "gone-1", "gone-2"):
        artifacts.add(artifact(key))
    artifacts.link("a.v1", StepName.AREA, None, "kept")

    collector(artifacts, files, runs).execute()

    assert files.removed == ["artifacts/area/gone-1", "artifacts/area/gone-2"]
    assert artifacts.get("kept") is not None
    assert artifacts.get("gone-1") is None


def test_working_directories_of_existing_runs_are_kept() -> None:
    artifacts, files, runs = InMemoryArtifacts(), RecordingFiles(), InMemoryRunRepository()
    runs.add(make_run("r1", state=RunState.RUNNING))
    runs.add(make_run("r2", state=RunState.FAILED))

    collector(artifacts, files, runs).execute()

    assert files.kept_runs == {"r1", "r2"}


@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING])
def test_no_artefact_is_removed_while_a_run_is_active(state: RunState) -> None:
    # The active run may be about to keep or re-ingest "old" (another run made it) or to link
    # "fresh" (it made it): both are left for a later pass.
    artifacts, files, runs = InMemoryArtifacts(), RecordingFiles(), InMemoryRunRepository()
    runs.add(make_run("r1", state=state))
    artifacts.add(artifact("fresh", "r1"))
    artifacts.add(artifact("old", "ended"))

    collector(artifacts, files, runs).execute()

    assert files.removed == []
    assert artifacts.get("fresh") is not None
    assert artifacts.get("old") is not None
    assert files.kept_runs == {"r1"}


def test_once_the_runs_ended_the_unreferenced_artefacts_go() -> None:
    artifacts, files, runs = InMemoryArtifacts(), RecordingFiles(), InMemoryRunRepository()
    runs.add(make_run("r1", state=RunState.SUCCEEDED))
    artifacts.add(artifact("fresh", "r1"))
    artifacts.add(artifact("old", "ended"))

    collector(artifacts, files, runs).execute()

    assert files.removed == ["artifacts/area/fresh", "artifacts/area/old"]


def test_a_failure_on_one_artefact_does_not_stop_the_pass() -> None:
    artifacts = InMemoryArtifacts()
    files, runs = RecordingFiles(failing={"artifacts/area/a"}), InMemoryRunRepository()
    artifacts.add(artifact("a"))
    artifacts.add(artifact("b"))

    collector(artifacts, files, runs).execute()

    assert files.removed == ["artifacts/area/b"]
    assert files.kept_runs == set()


def test_nothing_to_collect_is_fine() -> None:
    files = RecordingFiles()

    collector(InMemoryArtifacts(), files, InMemoryRunRepository()).execute()

    assert files.removed == []
