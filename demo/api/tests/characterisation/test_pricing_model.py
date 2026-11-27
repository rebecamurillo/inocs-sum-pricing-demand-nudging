"""Step 5 on the real package and its size-limited licence: the solve of the tiny instance
(tests 5 and 6 of ARCHITECTURE.md § 9.2). The real `PricingSolver` also passes the contract
suite in `tests/contract/test_pricing_solver.py` under this marker."""

import json
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.application.ports.pricing_solver import SolveRequest
from pricing_demo.domain.package_fingerprint import CHOICE_COEFFICIENT_NAMES
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.solves import Solve
from pricing_demo.infrastructure.pricing_model.choice_coefficients import read_choice_coefficients
from pricing_demo.infrastructure.pricing_model.package_fingerprint import PackageFingerprintReader
from pricing_demo.infrastructure.pricing_model.pricing_solver import PackagePricingSolver
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from tests.characterisation.rig import tiny_instance

pytestmark = pytest.mark.characterisation

DEFAULTS = {name: new_draft_goals(None).as_dict()[name] for name in SOLVER_GOALS}
# Goals under which the model sends travellers by bike, so the objective's four terms are not
# all zero.
BUSY = {
    **DEFAULTS,
    "ridership_weight": 100.0,
    "cost_bike_chf": 0.0,
    "lowest_price_chf": 0.0,
    "station_balance_weight": 5.0,
}
# Fixed at the first run on the committed synthetic city (`tiny_instance`, seed 1): the options
# of the solve under `BUSY` as (arc, type, flow, price per bike leg).
GOLDEN_BUSY_ROWS = [
    ("a1b", "PT+Bike", 2.0, 0.240502),
    ("a1c", "Car", 0.0, 0.0),
    ("a1p", "PT-Only", 15.0, 0.0),
    ("a2b", "PT+Bike", 0.0, 0.304533),
    ("a2c", "Car", 0.0, 0.0),
    ("a2p", "PT-Only", 34.0, 0.0),
    ("a3b", "PT+Bike", 4.0, 0.308808),
]
GOLDEN_BUSY_OBJECTIVE = 590.870827
# With the default goals nobody rides: the model prices every option but sends the travellers
# by public transport.
GOLDEN_DEFAULT_FLOWS = {"a1b": 0.0, "a1p": 17.0, "a2b": 0.0, "a2p": 38.0, "a3b": 0.0}


@pytest.fixture(scope="module")
def instance_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tiny_instance(tmp_path_factory.mktemp("tiny"))


def solve_in(
    instance_folder: Path, tmp_path: Path, goals: dict[str, Any], fingerprint: str = "f" * 64
) -> Solve:
    folder = tmp_path / "solve"
    shutil.copytree(instance_folder, folder)
    outcome = PackagePricingSolver(StageChild(), "test", "0" * 64).solve(
        SolveRequest("run-1", folder, goals, dict(FIXED_SOLVER_INPUTS), fingerprint),
        threading.Event(),
    )
    assert outcome.failure_code is None, outcome.failure_reason
    assert outcome.solve is not None
    return outcome.solve


def test_the_solve_of_the_tiny_instance_is_pinned(instance_folder: Path, tmp_path: Path) -> None:
    solve = solve_in(instance_folder, tmp_path, BUSY)

    assert [(r.arc_id, r.type, r.flow, round(r.bike_price or 0.0, 6)) for r in solve.rows] == (
        GOLDEN_BUSY_ROWS
    )
    assert solve.quality.objective_value == pytest.approx(GOLDEN_BUSY_OBJECTIVE, abs=1e-6)
    assert (solve.quality.solver_status_name, solve.quality.sol_count) == ("OPTIMAL", 2)
    assert len(solve.ods) == 2


def test_the_default_goals_send_everyone_by_public_transport(
    instance_folder: Path, tmp_path: Path
) -> None:
    solve = solve_in(instance_folder, tmp_path, DEFAULTS)

    assert {row.arc_id: row.flow for row in solve.rows if row.type != "Car"} == (
        GOLDEN_DEFAULT_FLOWS
    )


def test_the_same_solve_twice_gives_identical_rows(instance_folder: Path, tmp_path: Path) -> None:
    first = solve_in(instance_folder, tmp_path / "a", BUSY)
    second = solve_in(instance_folder, tmp_path / "b", BUSY)

    assert first.rows == second.rows
    assert first.ods == second.ods


def test_a_bike_option_has_a_row_only_when_the_model_offers_it_and_then_a_price(
    instance_folder: Path, tmp_path: Path
) -> None:
    every = {"a1b", "a2b", "a3b"}
    shown_all = solve_in(instance_folder, tmp_path / "a", DEFAULTS)
    shown_one = solve_in(instance_folder, tmp_path / "b", {**DEFAULTS, "max_displayed_options": 1})

    bike_all = [row for row in shown_all.rows if row.type == "PT+Bike"]
    bike_one = [row for row in shown_one.rows if row.type == "PT+Bike"]
    assert {row.arc_id for row in bike_all} == every
    assert bike_one == []
    assert all(row.nu > 0.5 and (row.bike_price or 0) > 0 for row in bike_all)
    assert {row.type for row in shown_one.rows} == {"PT-Only", "Car"}


def test_the_four_objective_terms_add_up_to_the_objective_value(
    instance_folder: Path, tmp_path: Path
) -> None:
    solve = solve_in(instance_folder, tmp_path, BUSY)
    instance = json.loads((instance_folder / "Instance_1.json").read_text(encoding="utf-8"))
    legs = json.loads((instance_folder / "option_bike_legs.json").read_text(encoding="utf-8"))
    stations = instance["bike_stations"]
    bike = [row for row in solve.rows if row.type == "PT+Bike"]

    ridership = BUSY["ridership_weight"] * sum(row.flow for row in bike)
    revenue = sum((row.z_value or 0.0) * legs[row.arc_id] for row in bike)
    cost = sum(BUSY["cost_bike_chf"] * legs[row.arc_id] * row.flow for row in bike)
    balance = sum(
        row.flow
        * BUSY["station_balance_weight"]
        * sum(
            delta * (1 - stations["station_inventory"][name] / stations["station_capacity"][name])
            for name, delta in instance["delta_ia"][row.arc_id].items()
            if delta
        )
        for row in bike
    )

    assert ridership > 0
    assert solve.quality.objective_value == pytest.approx(
        ridership + revenue - cost + balance, rel=1e-6
    )


def test_the_solve_records_the_limited_licence_and_the_gurobi_version(
    instance_folder: Path, tmp_path: Path
) -> None:
    provenance = solve_in(instance_folder, tmp_path, DEFAULTS, "c" * 64).provenance

    assert provenance.licence_kind == "limited"
    assert provenance.gurobi_version.count(".") == 2
    assert provenance.platform
    assert provenance.package_fingerprint == "c" * 64
    assert provenance.solver_parameters["TimeLimit"] == 7200
    assert provenance.solver_parameters["Threads"] == 4


def test_the_twelve_coefficients_are_found_in_the_installed_solver() -> None:
    package = Path(__file__).resolve().parents[4] / "sum_nsm_dynamic_pricing"
    source = package / "src/sum_nsm_dynamic_pricing/optimizer/solver.py"

    found = read_choice_coefficients(source.read_text(encoding="utf-8"))

    assert set(found) == set(CHOICE_COEFFICIENT_NAMES)
    assert None not in found.values()
    assert found["ASC_PT"] == -0.756
    assert found["BETA_Cost_park"] == 0.532


def test_the_fingerprint_reader_reads_the_same_twelve_through_its_child() -> None:
    package = Path(__file__).resolve().parents[4] / "sum_nsm_dynamic_pricing"
    source = package / "src/sum_nsm_dynamic_pricing/optimizer/solver.py"

    fingerprint = PackageFingerprintReader(package).read()

    assert fingerprint.choice_coefficients == read_choice_coefficients(
        source.read_text(encoding="utf-8")
    )
    assert None not in fingerprint.choice_coefficients.values()
