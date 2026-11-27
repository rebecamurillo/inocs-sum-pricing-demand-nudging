import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pricing_demo.application.build_planning import plan_for
from pricing_demo.application.ingest_step import StepIngestion
from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifact, Artifacts
from pricing_demo.application.ports.build_sources import BuildSources
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.city_preparation import CityPreparation, PreparationRequest
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.build_plan import (
    STEP_OUTPUTS,
    STEP_UPSTREAM,
    STEP_UPSTREAM_FILES,
    BuildPlan,
    PlannedStep,
)
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import InstanceVersion, InstanceVersionNotFound
from pricing_demo.domain.failure_codes import TIMETABLE_MISMATCH, failure_reason
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import Run, RunStep, StepName
from pricing_demo.domain.trip_planner_graph import timetable_matches

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
        ingestion: StepIngestion,
        read_model: ReadModel,
        route_failures: RouteFailures,
    ) -> None:
        self._preparation = preparation
        self._files = files
        self._artifacts = artifacts
        self._queue = queue
        self._instances = instances
        self._datasets = datasets
        self._sources = sources
        self._clock = clock
        self._ingestion = ingestion
        self._read_model = read_model
        self._route_failures = route_failures

    def keep(self, run: Run, step: RunStep) -> bool:
        _, _, planned = self._plan(run, step)
        key = planned.input_key
        # An artefact whose ingestion failed is not kept: the step runs and only ingests it.
        if key is None or self._artifacts.get(key) is None or not self._read_model.is_ingested(key):
            return False
        self._artifacts.link(run.subject.id, step.step, planned.period_id, key)
        if step.step is StepName.ROUTES:
            self._set_failure_pct(run.id, self._read_model.counts_of([key])[key])
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
        existing = self._artifacts.get(key)
        if existing is not None:
            # The files are stored and the ingestion failed before: ingest them, nothing else.
            return self._ingest(run, step, existing, dataset, plan, version, planned)
        if step.step is StepName.ROUTES:
            # Cleared first: a refused attempt does not show an earlier attempt's failures.
            self._route_failures.clear(run.id, step.position)
            manifest = self._sources.graph_manifest()
            if manifest is not None and not timetable_matches(manifest, dataset.gtfs):
                return StepOutcome.failed(TIMETABLE_MISMATCH, failure_reason(TIMETABLE_MISMATCH))
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
            lambda failure: self._route_failures.add(
                run.id, step.position, period.id, failure, self._clock.now()
            ),
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
        artifact = Artifact(
            key,
            step.step,
            inputs,
            stored,
            str(path),
            fingerprint,
            self._clock.now(),
            run.id,
            dict(outcome.counts),
        )
        self._artifacts.add(artifact)
        self._files.discard(working)
        # Another run may have stored the same key first; its row is the artefact (its run's
        # failures and reported counts are the ones the read model and the summary read).
        stored_artifact = self._artifacts.get(key) or artifact
        return self._ingest(
            run,
            step,
            stored_artifact,
            dataset,
            plan,
            version,
            planned,
            outcome.log_excerpt,
            outcome.peak_rss_bytes,
        )

    def _ingest(
        self,
        run: Run,
        step: RunStep,
        artifact: Artifact,
        dataset: CityDataset,
        plan: BuildPlan,
        version: InstanceVersion,
        planned: PlannedStep,
        log_excerpt: str | None = None,
        peak_rss_bytes: int | None = None,
    ) -> StepOutcome:
        """Ingest the stored artefact, then link it: the link exists only for an ingested
        artefact. A failure here fails the step and leaves the artefact where it is."""
        try:
            upstream = {
                name: found
                for name in STEP_UPSTREAM[step.step]
                if (key := plan.step(name).input_key) is not None
                and (found := self._artifacts.get(key)) is not None
            }
            counts = self._ingestion.ingest(artifact, dataset, upstream)
        except Exception as error:
            logger.exception("The ingestion of step %s of run %s failed", step.step.value, run.id)
            # The child's log is what tells why its files could not be read: keep it.
            return StepOutcome.failed(
                STAGE_ERROR,
                f"{type(error).__name__}: {error}",
                log_excerpt=log_excerpt,
                peak_rss_bytes=peak_rss_bytes,
            )
        self._artifacts.link(version.id, step.step, planned.period_id, artifact.input_key)
        if step.step is StepName.ROUTES:
            self._set_failure_pct(run.id, counts)
        return StepOutcome.done(counts, log_excerpt=log_excerpt, peak_rss_bytes=peak_rss_bytes)

    def _set_failure_pct(self, run_id: str, counts: Mapping[str, Any]) -> None:
        pct = counts["failure_pct"]
        self._queue.update(run_id, lambda run: replace(run, failure_pct=pct))

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
