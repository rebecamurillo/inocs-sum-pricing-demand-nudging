import logging

from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.application.ports.simulations import Simulations
from pricing_demo.domain.runs import RunState

logger = logging.getLogger(__name__)


class CollectUnreferenced:
    """Removes the simulations no pricing version links to any more (with their child rows),
    the artefacts no instance version links to and no solve references any more (their rows,
    read-model rows, solve rows and read-only folders), and the working directories of runs
    that no longer exist.

    One artefact at a time: a failure is logged and the pass goes on.
    """

    def __init__(
        self,
        artifacts: Artifacts,
        files: ArtifactFiles,
        runs: RunRepository,
        simulations: Simulations | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._files = files
        self._runs = runs
        self._simulations = simulations

    def execute(self) -> None:
        # While a run is queued or running, no artefact or simulation is removed: a step stores
        # an artefact before it links it, and a step that keeps or re-ingests an unreferenced
        # artefact (one another run made) reads it before it links it, as a simulation step
        # does with a stored simulation. All are left for a later pass.
        active = self._runs.list_by_states([RunState.QUEUED, RunState.RUNNING])
        if self._simulations is not None and not active:
            try:
                self._simulations.remove_unlinked()
            except Exception:
                logger.exception("The collection of the unlinked simulations failed")
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
