import logging
from dataclasses import replace

from pricing_demo.application.build_planning import plan_for
from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifact, Artifacts
from pricing_demo.application.ports.build_sources import BuildSources
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.city_preparation import CityPreparation, PreparationRequest
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.build_plan import (
    STEP_OUTPUTS,
    STEP_UPSTREAM,
    STEP_UPSTREAM_FILES,
    BuildPlan,
    PlannedStep,
)
from pricing_demo.domain.city_instances import InstanceVersion, InstanceVersionNotFound
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import Run, RunStep

logger = logging.getLogger(__name__)

NO_KEY_REASON = (
    "the step's input key is not known: the package fingerprint or "
    "the trip planner's graph manifest is missing"
)


class BuildStepExecutor:
    """Runs and keeps the four steps of a build (`StepExecutor` and `StepKeeper`).

    The worker computes each step's key itself (ARCHITECTURE.md § 3.2 step 4) and writes it to
    the run step when it differs from the one queued: the stored artefacts decide `kept`, not
    the plan the API made earlier.
    """

    def __init__(
        self,
        preparation: CityPreparation,
        files: ArtifactFiles,
        artifacts: Artifacts,
        queue: RunQueue,
        instances: CityInstances,
        datasets: CityDatasets,
        sources: BuildSources,
        clock: Clock,
    ) -> None:
        self._preparation = preparation
        self._files = files
        self._artifacts = artifacts
        self._queue = queue
        self._instances = instances
        self._datasets = datasets
        self._sources = sources
        self._clock = clock

    def keep(self, run: Run, step: RunStep) -> bool:
        _, _, planned = self._plan(run, step)
        if planned.input_key is None or self._artifacts.get(planned.input_key) is None:
            return False
        self._artifacts.link(run.subject.id, step.step, planned.period_id, planned.input_key)
        return True

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        version, plan, planned = self._plan(run, step)
        key, inputs = planned.input_key, planned.inputs
        if key is None or inputs is None:
            return StepOutcome.failed(STAGE_ERROR, NO_KEY_REASON)
        instance = self._instances.get_instance(version.instance_id)
        dataset = self._datasets.get(instance.dataset_id) if instance else None
        period = self._instances.periods_of(version.id)[0]
        assert dataset is not None  # the instance's foreign key
        working = self._files.working_dir(run.id, step.step)
        wanted = STEP_UPSTREAM_FILES[step.step]
        for upstream in STEP_UPSTREAM[step.step]:
            names = [name for name in STEP_OUTPUTS[upstream] if name in wanted]
            upstream_key = plan.step(upstream).input_key
            assert upstream_key is not None  # a key exists only when its upstream keys do
            self._files.copy_upstream(upstream, upstream_key, names, working)
        outcome = self._preparation.prepare(
            PreparationRequest(run.id, step.step, working, version.parameters, dataset, period),
            lambda done, total: self._progress(run.id, step, done, total),
            stop,
        )
        if outcome.stopped:
            # A step that was stopped leaves nothing to resume from (ARCHITECTURE.md § 4.5).
            self._files.discard(working)
            return outcome
        if outcome.failure_code is not None:
            # The working directory stays until the step succeeds or the run is deleted.
            return outcome
        path, stored = self._files.store(step.step, key, working, STEP_OUTPUTS[step.step])
        fingerprint = self._sources.package_fingerprint()
        assert fingerprint is not None  # the key was computed from it
        self._artifacts.add(
            Artifact(key, step.step, inputs, stored, str(path), fingerprint, self._clock.now())
        )
        self._artifacts.link(version.id, step.step, planned.period_id, key)
        self._files.discard(working)
        return outcome

    def _plan(self, run: Run, step: RunStep) -> tuple[InstanceVersion, BuildPlan, PlannedStep]:
        """The version's plan, recomputed now, and the step's place in it; its key is written
        to the run step when it is not the one queued."""
        version = self._instances.get_version(run.subject.id)
        if version is None:
            raise InstanceVersionNotFound(run.subject.id)
        plan = plan_for(version, self._instances, self._datasets, self._artifacts, self._sources)
        planned = plan.step(step.step)
        self._write_key(run.id, step, planned.input_key)
        return version, plan, planned

    def _write_key(self, run_id: str, step: RunStep, key: str | None) -> None:
        if key is None or key == step.input_key:
            return

        def change(run: Run) -> Run:
            steps = tuple(
                replace(item, input_key=key) if item.position == step.position else item
                for item in run.steps
            )
            return replace(run, steps=steps)

        self._queue.update(run_id, change)

    def _progress(self, run_id: str, step: RunStep, done: int, total: int) -> None:
        def change(run: Run) -> Run:
            steps = tuple(
                replace(item, progress_done=done, progress_total=total)
                if item.position == step.position
                else item
                for item in run.steps
            )
            return replace(run, steps=steps)

        self._queue.update(run_id, change)
