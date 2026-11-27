import logging

from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.runs import RunState

logger = logging.getLogger(__name__)


class CollectUnreferenced:
    """Removes the artefacts no instance version links to any more (their rows, read-model rows
    and read-only folders) and the working directories of runs that no longer exist.

    One artefact at a time: a failure is logged and the pass goes on. Epic 3 extends it to
    solves and simulations.
    """

    def __init__(self, artifacts: Artifacts, files: ArtifactFiles, runs: RunRepository) -> None:
        self._artifacts = artifacts
        self._files = files
        self._runs = runs

    def execute(self) -> None:
        # While a run is queued or running, no artefact is removed: a step stores an artefact
        # before it links it, and a step that keeps or re-ingests an unreferenced artefact
        # (one another run made) reads it before it links it. Both are left for a later pass.
        active = self._runs.list_by_states([RunState.QUEUED, RunState.RUNNING])
        for artifact in [] if active else self._artifacts.unreferenced():
            try:
                if self._artifacts.remove(artifact.input_key):
                    self._files.remove_artifact(artifact.path)
            except Exception:
                logger.exception("The collection of the artefact %s failed", artifact.input_key)
        existing = {run.id for run in self._runs.list_by_states(list(RunState))}
        try:
            self._files.remove_working_dirs_except(existing)
        except Exception:
            logger.exception("The collection of the working directories failed")
