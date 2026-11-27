"""The real `PricingSolver`: the unmodified package's solve of one period, run in a stage
child, and what it leaves read into a `Solve` (ARCHITECTURE.md § 4.1, § 4.7).

The package is not imported here: the child imports it (`stage_runner.run_pricing_model`).
"""

import json
import os
from pathlib import Path
from typing import Any

from pricing_demo.application.ports.pricing_solver import SolveOutcome, SolveRequest
from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.infrastructure.pricing_model.solve_reading import (
    RESULTS_FILE,
    ProvenanceBase,
    optimizer_fields,
    read_solve,
    size_limited,
)
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import (
    SOLVE_FACTS_FILE,
    STDOUT_FILE,
    StageSpec,
)

# `PipelineConfig` requires an area and a timetable that `optimize` never reads: it reads only
# the output folder (model-notes entry 28).
PIPELINE_PLACEHOLDERS: dict[str, Any] = {
    "center_lat": 0.0,
    "center_lon": 0.0,
    "radius_m": 0.0,
    "gtfs_path": "unused",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class PackagePricingSolver:
    def __init__(
        self, child: StageChild, demonstrator_version: str, dependency_lock_sha256: str
    ) -> None:
        self._child = child
        self._demonstrator_version = demonstrator_version
        self._dependency_lock_sha256 = dependency_lock_sha256

    def solve(self, request: SolveRequest, stop: StopSignal) -> SolveOutcome:
        if stop.is_set():
            return SolveOutcome(stopped=True)
        spec = StageSpec(
            step="pricing_model",
            working_dir=str(request.working_dir),
            parent_pid=os.getpid(),
            pipeline=dict(PIPELINE_PLACEHOLDERS),
            optimizer=optimizer_fields(request.goals, request.fixed_inputs),
        )
        ended = self._child.run(spec, stop)
        if ended.stopped:
            return SolveOutcome(stopped=True, log_excerpt=ended.log_excerpt)
        folder = request.working_dir
        try:
            stdout = (folder / STDOUT_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            stdout = ""
        # The package swallows the size-limit error and goes on: that, not the exit, is the
        # reason when the log shows it.
        if ended.failure_code is not None and not size_limited(stdout):
            return SolveOutcome(
                failure_code=ended.failure_code,
                failure_reason=ended.failure_reason,
                log_excerpt=ended.log_excerpt,
            )
        facts = _read_json(folder / SOLVE_FACTS_FILE)
        facts = facts if isinstance(facts, dict) else {}
        results = _read_json(folder / RESULTS_FILE)
        try:
            read = read_solve(
                results,
                stdout,
                facts,
                ProvenanceBase(
                    request.package_fingerprint,
                    self._demonstrator_version,
                    self._dependency_lock_sha256,
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            # A results file in a shape the adapter does not know: a failure, never an
            # exception (the port's promise), with the child's log kept.
            return SolveOutcome(
                failure_code=STAGE_ERROR,
                failure_reason=f"{type(error).__name__}: {error}",
                log_excerpt=ended.log_excerpt,
            )
        if isinstance(read, tuple):
            code, reason = read
            return SolveOutcome(
                failure_code=code, failure_reason=reason, log_excerpt=ended.log_excerpt
            )
        return SolveOutcome(solve=read, output_files=(RESULTS_FILE,), log_excerpt=ended.log_excerpt)
