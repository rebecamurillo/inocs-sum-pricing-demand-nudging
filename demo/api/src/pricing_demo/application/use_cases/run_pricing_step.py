import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifact, Artifacts
from pricing_demo.application.ports.build_sources import BuildSources
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.component_reports import ComponentReports
from pricing_demo.application.ports.pricing_solver import PricingSolver, SolveRequest
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.solves import Solves, StoredResultSummary
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.run_step_writes import write_kept, write_key
from pricing_demo.domain.derived_result import DERIVATION_VERSION, summarise_result
from pricing_demo.domain.failure_codes import SOLVER_SIZE_LIMITED, failure_reason
from pricing_demo.domain.pricing_keys import (
    FIXED_SOLVER_INPUTS,
    KEPT_SOLVE_REASON,
    SOLVER_GOALS,
    solve_inputs,
    solve_key,
)
from pricing_demo.domain.pricing_versions import PricingVersion, PricingVersionNotFound
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import Run, RunStep, StepName
from pricing_demo.domain.solves import PT_BIKE, SolveRow
from pricing_demo.domain.system_status import ComponentState

logger = logging.getLogger(__name__)

NO_INSTANCE_REASON = "the step's input key is not known: the instance version has no stored build"
NO_FINGERPRINT_REASON = (
    "the step's input key is not known: the runner has not reported the pricing package"
)
INSTANCE_FILE = "Instance_1.json"


def solve_counts(rows: list[SolveRow], status_name: str) -> dict[str, Any]:
    """What a solve counted: the hub pairs it prices, the options it offers, its status."""
    offered = [row for row in rows if row.type == PT_BIKE]
    return {
        "hub_pairs_priced": len({(row.origin_hub, row.destination_hub) for row in offered}),
        "options_offered": len(offered),
        "solver_status_name": status_name,
    }


@dataclass(frozen=True)
class _StepInputs:
    key: str
    inputs: Mapping[str, Any]
    instance_key: str
    package_fingerprint: str


class PricingModelStepExecutor:
    """Runs and keeps the pricing model step of a pricing run (`StepExecutor` and `StepKeeper`).

    The worker computes the step's key itself (ARCHITECTURE.md § 3.2) and writes it to the run
    step: a stored solve with the key decides `kept`, not anything the API knew when it queued
    the run.
    """

    def __init__(
        self,
        solver: PricingSolver,
        probe: ComponentProbe,
        reports: ComponentReports,
        worker_id: str,
        files: ArtifactFiles,
        artifacts: Artifacts,
        solves: Solves,
        pricing_versions: PricingVersions,
        queue: RunQueue,
        sources: BuildSources,
        clock: Clock,
        read_model: ReadModel,
    ) -> None:
        self._solver = solver
        self._probe = probe
        self._reports = reports
        self._worker_id = worker_id
        self._files = files
        self._artifacts = artifacts
        self._solves = solves
        self._pricing_versions = pricing_versions
        self._queue = queue
        self._sources = sources
        self._clock = clock
        self._read_model = read_model

    def keep(self, run: Run, step: RunStep) -> bool:
        version, period_id = self._subject(run, step)
        found = self._key(version, run, step)
        if isinstance(found, str) or not self._solves.is_stored(found.key):
            return False
        key = found.key
        try:
            self._solves.link_stored(key, version.id, period_id, self._clock.now())
        except KeyError:
            # The solve's rows are stored and no version points to them any more: solve again.
            return False
        record = self._solves.solve_of(version.id, period_id)
        assert record is not None  # linked just above
        if self._solves.summary_of(key, DERIVATION_VERSION) is None:
            # A solve stored before its summary existed, or under an older derivation version.
            try:
                summary = self._summary(
                    version,
                    found.instance_key,
                    key,
                    self._solves.rows(key),
                    record.quality.objective_value,
                    self._solves.package_summary_of(key),
                )
            except ValueError:
                # The execution reports the reason when it solves and stores again.
                return False
            self._solves.store_summary(summary)
        counts = solve_counts(self._solves.rows(key), record.quality.solver_status_name)
        write_kept(self._queue, run.id, step, KEPT_SOLVE_REASON, counts)
        return True

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        version, period_id = self._subject(run, step)
        found = self._key(version, run, step)
        if isinstance(found, str):
            return StepOutcome.failed(STAGE_ERROR, found)
        key, inputs, instance_key, fingerprint = (
            found.key,
            found.inputs,
            found.instance_key,
            found.package_fingerprint,
        )
        refused = self._reprobe()
        if refused is not None:
            return refused
        working = self._files.working_dir(run.id, StepName.PRICING_MODEL)
        self._files.copy_upstream(
            StepName.TRAVELLERS_AND_BIKES, instance_key, [INSTANCE_FILE], working
        )
        values = version.goals.as_dict()
        outcome = self._solver.solve(
            SolveRequest(
                run.id,
                working,
                {name: values[name] for name in SOLVER_GOALS},
                dict(FIXED_SOLVER_INPUTS),
                fingerprint,
            ),
            stop,
        )
        if outcome.stopped:
            # A step that was stopped leaves nothing to resume from (ARCHITECTURE.md § 4.5).
            self._files.discard(working)
            return StepOutcome.stopped_on_signal()
        if outcome.failure_code is not None or outcome.solve is None:
            # The working directory stays until the step succeeds or the run is deleted.
            return StepOutcome.failed(
                outcome.failure_code or STAGE_ERROR,
                outcome.failure_reason or "the solver returned no solve",
                log_excerpt=outcome.log_excerpt,
            )
        counts = solve_counts(list(outcome.solve.rows), outcome.solve.quality.solver_status_name)
        try:
            # Computed before the files move, so a failure leaves the working directory intact.
            summary = self._summary(
                version,
                instance_key,
                key,
                list(outcome.solve.rows),
                outcome.solve.quality.objective_value,
                outcome.solve.package_summary,
            )
            path, stored = self._files.store(
                StepName.PRICING_MODEL, key, working, list(outcome.output_files)
            )
            now = self._clock.now()
            artifact = Artifact(
                key,
                StepName.PRICING_MODEL,
                inputs,
                stored,
                str(path),
                fingerprint,
                now,
                run.id,
                counts,
            )
            self._solves.store(artifact, outcome.solve, version.id, period_id, now, summary)
        except Exception as error:
            logger.exception("The storing of the solve of run %s failed", run.id)
            return StepOutcome.failed(
                STAGE_ERROR, f"{type(error).__name__}: {error}", log_excerpt=outcome.log_excerpt
            )
        self._files.discard(working)
        return StepOutcome.done(counts, log_excerpt=outcome.log_excerpt)

    def _summary(
        self,
        version: PricingVersion,
        instance_key: str,
        key: str,
        rows: list[SolveRow],
        objective_value: float | None,
        package_summary: Mapping[str, object] | None,
    ) -> StoredResultSummary:
        """The numbers of the solve's result, from its rows and the instance it solved."""
        hubs_key = self._artifacts.links_of(version.instance_version_id).get(StepName.HUBS)
        if hubs_key is None:
            raise ValueError("the instance version has no stored hubs")
        numbers = summarise_result(
            rows,
            self._read_model.route_options(instance_key),
            self._read_model.option_station_deltas(instance_key),
            self._read_model.station_bikes(instance_key),
            self._read_model.hubs(hubs_key),
            self._read_model.hub_pairs(instance_key),
            version.goals,
            objective_value,
        )
        return StoredResultSummary(
            key, DERIVATION_VERSION, numbers, package_summary, self._clock.now()
        )

    def _subject(self, run: Run, step: RunStep) -> tuple[PricingVersion, str]:
        version = self._pricing_versions.get(run.subject.id)
        if version is None:
            raise PricingVersionNotFound(run.subject.id)
        period_id = step.period or self._pricing_versions.period_ids(version.id)[0]
        return version, period_id

    def _instance_key(self, version: PricingVersion) -> str | None:
        return self._artifacts.links_of(version.instance_version_id).get(
            StepName.TRAVELLERS_AND_BIKES
        )

    def _key(self, version: PricingVersion, run: Run, step: RunStep) -> _StepInputs | str:
        """The step's key and inputs, written to the run step; or the reason it has none."""
        instance_key = self._instance_key(version)
        if instance_key is None:
            return NO_INSTANCE_REASON
        fingerprint = self._sources.package_fingerprint()
        if fingerprint is None:
            return NO_FINGERPRINT_REASON
        key = solve_key(version.goals, instance_key, fingerprint)
        write_key(self._queue, run.id, step, key)
        return _StepInputs(
            key, solve_inputs(version.goals, instance_key, fingerprint), instance_key, fingerprint
        )

    def _reprobe(self) -> StepOutcome | None:
        """Probe the solver again, report what it answered, and refuse a solver that cannot
        solve: the answer the API judged on may be old."""
        status = self._probe.check()
        self._reports.write(status, self._worker_id, self._clock.now())
        if status.state is ComponentState.LIMITED:
            return StepOutcome.failed(SOLVER_SIZE_LIMITED, failure_reason(SOLVER_SIZE_LIMITED))
        if status.state is ComponentState.UNAVAILABLE:
            return StepOutcome.failed(
                STAGE_ERROR,
                failure_reason(
                    STAGE_ERROR, exception_type="SolverUnavailable", message=status.reason
                ),
            )
        return None
