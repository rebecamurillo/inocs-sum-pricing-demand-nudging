import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.application.ports.pricing_solver import SolveRequest
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.failure_codes import SOLVER_NO_SOLUTION, SOLVER_SIZE_LIMITED
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.infrastructure.pricing_model.pricing_solver import PackagePricingSolver
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec

GOALS = {name: new_draft_goals(None).as_dict()[name] for name in SOLVER_GOALS}
OPTIMAL_LOG = (
    "Restricted license - for non-production use only\n"
    "Set parameter Threads to value 4\n"
    "Solver ended Instance_1 with status 2. Best objective found: 3.5\n"
    "Total feasible solutions found: 1\n"
)
RESULTS = {
    "Solution Time (s)": 0.5,
    "Objective Value": 3.5,
    "Gap (%)": 0.0,
    "Solution Method": -1,
    "instances": [
        {"Instance OD": "1->0", "OD": "1->0", "gamma": 1.2},
        {
            "OD": "1->0",
            "Arc ID": "a1p",
            "Type": "PT-Only",
            "nu": 1.0,
            "Flow (q)": 17.0,
            "Bike Price": 0.0,
            "Total Price": 2.0,
        },
    ],
}


class FakeChild(StageChild):
    """Leaves what a child would, then answers with the outcome the test names."""

    def __init__(
        self,
        outcome: StepOutcome | None = None,
        stdout: str = OPTIMAL_LOG,
        results: object = RESULTS,
        summary: str | None = None,
    ) -> None:
        self.specs: list[StageSpec] = []
        self._outcome = outcome or StepOutcome.done()
        self._stdout = stdout
        self._results = results
        self._summary = summary

    def run(
        self, spec: StageSpec, stop: StopSignal, on_progress: Callable[[], None] | None = None
    ) -> StepOutcome:
        self.specs.append(spec)
        folder = Path(spec.working_dir)
        (folder / "stdout.log").write_text(self._stdout, encoding="utf-8")
        (folder / "solve_facts.json").write_text(
            json.dumps(
                {
                    "results_file": "optimization_instance_results.json",
                    "gurobi_version": "14.0.0",
                    "platform": "Linux-test",
                }
            ),
            encoding="utf-8",
        )
        (folder / "optimization_instance_results.json").write_text(
            json.dumps(self._results), encoding="utf-8"
        )
        if self._summary is not None:
            (folder / "package_summary.json").write_text(self._summary, encoding="utf-8")
        return self._outcome


def solve(
    tmp_path: Path, child: FakeChild, stop: threading.Event | None = None
) -> tuple[Any, FakeChild]:
    solver = PackagePricingSolver(child, "0.1.0", "b" * 64)
    request = SolveRequest("run-1", tmp_path, GOALS, dict(FIXED_SOLVER_INPUTS), "f" * 64)
    return solver.solve(request, stop or threading.Event()), child


def test_the_child_is_asked_for_a_pricing_model_stage_with_the_goals_under_the_packages_names(
    tmp_path: Path,
) -> None:
    _, child = solve(tmp_path, FakeChild())

    spec = child.specs[0]
    assert (spec.step, spec.working_dir, spec.parent_pid) == (
        "pricing_model",
        str(tmp_path),
        os.getpid(),
    )
    assert spec.optimizer["cost_bike"] == GOALS["cost_bike_chf"]
    assert spec.optimizer["P_bar"] == GOALS["lowest_price_chf"]
    assert spec.optimizer["max_displayed_alternatives"] == GOALS["max_displayed_options"]
    assert {name: spec.optimizer[name] for name in FIXED_SOLVER_INPUTS} == dict(FIXED_SOLVER_INPUTS)
    assert spec.pipeline == {
        "center_lat": 0.0,
        "center_lon": 0.0,
        "radius_m": 0.0,
        "gtfs_path": "unused",
    }


def test_a_solve_that_ended_well_is_the_solve_with_its_provenance_and_its_file(
    tmp_path: Path,
) -> None:
    outcome, _ = solve(tmp_path, FakeChild())

    assert outcome.failure_code is None
    assert list(outcome.output_files) == ["optimization_instance_results.json"]
    quality, provenance = outcome.solve.quality, outcome.solve.provenance
    assert (quality.solver_status_name, quality.objective_value, quality.sol_count) == (
        "OPTIMAL",
        3.5,
        1,
    )
    assert provenance.gurobi_version == "14.0.0"
    assert provenance.platform == "Linux-test"
    assert provenance.licence_kind == "limited"
    assert provenance.solver_parameters == {"Threads": 4}
    assert provenance.package_fingerprint == "f" * 64
    assert provenance.demonstrator_version == "0.1.0"
    assert provenance.dependency_lock_sha256 == "b" * 64
    assert [row.arc_id for row in outcome.solve.rows] == ["a1p"]
    assert [od.gamma for od in outcome.solve.ods] == [1.2]


def test_the_size_limit_in_the_log_is_the_reason_even_when_the_package_went_on(
    tmp_path: Path,
) -> None:
    log = (
        "Gurobi error during optimization: Model too large for size-limited license\n"
        "Solver ended with status 1\n"
    )

    outcome, _ = solve(tmp_path, FakeChild(stdout=log, results=None))

    assert outcome.failure_code == SOLVER_SIZE_LIMITED
    assert outcome.solve is None


def test_a_null_result_is_no_solution_with_the_status_name(tmp_path: Path) -> None:
    outcome, _ = solve(tmp_path, FakeChild(stdout="Solver ended with status 3\n", results=None))

    assert outcome.failure_code == SOLVER_NO_SOLUTION
    assert "INFEASIBLE" in (outcome.failure_reason or "")


def test_a_child_that_failed_gives_its_failure_and_log(tmp_path: Path) -> None:
    failed = StepOutcome(
        failure_code=STAGE_ERROR, failure_reason="ValueError: bad", log_excerpt="Traceback"
    )

    outcome, _ = solve(tmp_path, FakeChild(failed))

    assert (outcome.failure_code, outcome.failure_reason) == (STAGE_ERROR, "ValueError: bad")
    assert outcome.log_excerpt == "Traceback"
    assert outcome.solve is None


def test_a_results_file_in_an_unknown_shape_is_a_stage_error_with_the_log(
    tmp_path: Path,
) -> None:
    unknown = {**RESULTS, "instances": [{"OD": "1->0", "Arc ID": "x", "Type": "Bus"}]}
    child = FakeChild(StepOutcome.done(log_excerpt="solver log"), results=unknown)

    outcome, _ = solve(tmp_path, child)

    assert outcome.failure_code == STAGE_ERROR
    assert (outcome.failure_reason or "").startswith("ValueError")
    assert outcome.log_excerpt == "solver log"
    assert outcome.solve is None


def test_a_child_stopped_by_the_worker_is_stopped(tmp_path: Path) -> None:
    outcome, _ = solve(tmp_path, FakeChild(StepOutcome(stopped=True)))

    assert outcome.stopped is True
    assert outcome.solve is None


def test_a_stop_set_before_the_solve_runs_no_child(tmp_path: Path) -> None:
    stop = threading.Event()
    stop.set()

    outcome, child = solve(tmp_path, FakeChild(), stop)

    assert outcome.stopped is True
    assert child.specs == []


def test_the_package_summary_the_child_wrote_is_on_the_solve_and_among_the_output_files(
    tmp_path: Path,
) -> None:
    record = {"Avg Bike Price (Multimodal, Flow ≥ 1)": 1.25, "Obj Value": 3.5, "Gap (%)": None}

    outcome, _ = solve(tmp_path, FakeChild(summary=json.dumps(record)))

    assert outcome.solve.package_summary == record
    assert list(outcome.output_files) == [
        "optimization_instance_results.json",
        "package_summary.json",
    ]


def test_the_goals_the_solve_ran_with_are_on_it_under_the_packages_names(tmp_path: Path) -> None:
    outcome, _ = solve(tmp_path, FakeChild())

    assert outcome.solve.package_parameters["cost_bike"] == GOALS["cost_bike_chf"]
    assert outcome.solve.package_parameters["P_bar"] == GOALS["lowest_price_chf"]
    assert outcome.solve.package_parameters["theta"] == GOALS["station_balance_weight"]
    assert "mult_A1" not in outcome.solve.package_parameters


def test_a_missing_package_summary_is_none_and_not_a_failure(tmp_path: Path) -> None:
    outcome, _ = solve(tmp_path, FakeChild())

    assert outcome.failure_code is None
    assert outcome.solve.package_summary is None
    assert list(outcome.output_files) == ["optimization_instance_results.json"]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", ""])
def test_a_malformed_package_summary_is_none_and_not_a_failure(tmp_path: Path, text: str) -> None:
    outcome, _ = solve(tmp_path, FakeChild(summary=text))

    assert outcome.failure_code is None
    assert outcome.solve.package_summary is None
    assert list(outcome.output_files) == ["optimization_instance_results.json"]
