"""The PricingSolver port: one suite, run against the fake. The real adapter (story 3-4) passes
it too, under the marker `characterisation`; the tests that pin the fake's formula are on `rig`."""

import json
import shutil
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from pricing_demo.application.ports.pricing_solver import PricingSolver, SolveOutcome, SolveRequest
from pricing_demo.domain.failure_codes import SOLVER_NO_SOLUTION, SOLVER_SIZE_LIMITED
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.solves import Solve, model_bike_prices
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from tests.support.city_files import FakeCity

GOALS = {name: new_draft_goals(None).as_dict()[name] for name in SOLVER_GOALS}
FINGERPRINT = "f" * 64


@dataclass
class Rig:
    port: PricingSolver
    settings: InMemoryFakeSettings
    folder: Path
    instance: Mapping[str, object]

    def solve(
        self, goals: Mapping[str, float] | None = None, stop: threading.Event | None = None
    ) -> SolveOutcome:
        return self.port.solve(
            SolveRequest(
                "run-1", self.folder, goals or GOALS, dict(FIXED_SOLVER_INPUTS), FINGERPRINT
            ),
            stop or threading.Event(),
        )


@pytest.fixture(params=[pytest.param("fake", id="fake")])
def rig(request: pytest.FixtureRequest, tmp_path: Path) -> Rig:
    city = FakeCity(tmp_path)
    for name in list(tmp_path.iterdir()):
        if name.name != "Instance_1.json":
            name.unlink() if name.is_file() else shutil.rmtree(name)
    settings = InMemoryFakeSettings()
    return Rig(FakePricingSolver(settings), settings, tmp_path, city.files["Instance_1.json"])


def solved(rig: Rig, goals: Mapping[str, float] | None = None) -> Solve:
    outcome = rig.solve(goals)
    assert outcome.failure_code is None, outcome.failure_reason
    assert not outcome.stopped
    assert outcome.solve is not None
    return outcome.solve


def arcs(rig: Rig, name: str) -> list[dict[str, object]]:
    return [arc for found in rig.instance[name].values() for arc in found]  # type: ignore[attr-defined]


def test_the_same_inputs_give_the_same_solve(rig: Rig) -> None:
    assert solved(rig) == solved(rig)


def test_the_solve_names_the_file_it_wrote_into_the_working_directory(rig: Rig) -> None:
    outcome = rig.solve()

    assert list(outcome.output_files) == ["solution.json"]
    written = json.loads((rig.folder / "solution.json").read_text(encoding="utf-8"))
    assert len(written) == len(outcome.solve.rows)  # type: ignore[union-attr]


def test_a_bike_option_has_a_row_only_when_the_model_offers_it_and_then_a_price(rig: Rig) -> None:
    solve = solved(rig)

    bike = [row for row in solve.rows if row.type == "PT+Bike"]
    offered = {row.arc_id for row in bike}
    every_bike_arc = {str(arc["arc_id"]) for arc in arcs(rig, "arcs_pt_bike")}
    assert offered
    assert offered < every_bike_arc
    assert all(row.bike_price is not None and row.bike_price > 0 for row in bike)
    assert all(row.nu == 1 for row in bike)
    assert set(model_bike_prices(solve.rows)) == offered


def test_the_other_modes_have_a_row_for_every_option(rig: Rig) -> None:
    solve = solved(rig)

    for row_type, name in (("PT-Only", "arcs_pt_only"), ("Car", "car_paths")):
        found = {row.arc_id for row in solve.rows if row.type == row_type}
        assert found == {str(arc["arc_id"]) for arc in arcs(rig, name)}


def test_every_hub_pair_has_a_gamma(rig: Rig) -> None:
    solve = solved(rig)

    pairs = {(str(item["origin"]), str(item["destination"])) for item in rig.instance["OD_pairs"]}  # type: ignore[attr-defined]
    assert {(item.origin_hub, item.destination_hub) for item in solve.ods} == pairs


def test_the_flows_of_a_pair_add_up_to_its_demand(rig: Rig) -> None:
    solve = solved(rig)

    for item in rig.instance["OD_pairs"]:  # type: ignore[attr-defined]
        flow = sum(
            row.flow
            for row in solve.rows
            if (row.origin_hub, row.destination_hub) == (item["origin"], item["destination"])
        )
        assert flow == pytest.approx(item["demand"])


def test_goals_that_differ_give_a_different_price_on_at_least_one_offered_option(
    rig: Rig,
) -> None:
    other = {**GOALS, "ridership_weight": GOALS["ridership_weight"] + 5}

    first, second = model_bike_prices(solved(rig).rows), model_bike_prices(solved(rig, other).rows)

    assert any(first[arc] != second[arc] for arc in first.keys() & second.keys())


def test_the_price_respects_the_lowest_price(rig: Rig) -> None:
    high = {**GOALS, "lowest_price_chf": 50.0}

    assert set(model_bike_prices(solved(rig, high).rows).values()) == {50.0}


def test_the_solve_reports_an_optimal_solution_labelled_fake(rig: Rig) -> None:
    solve = solved(rig)

    assert (solve.quality.solver_status, solve.quality.solver_status_name) == (2, "OPTIMAL")
    assert (solve.quality.gap_pct, solve.quality.sol_count) == (0.0, 1)
    assert solve.quality.time_limit_reached is False
    assert solve.provenance.gurobi_version == "fake"
    assert solve.provenance.platform == "fake"
    assert solve.provenance.package_fingerprint == FINGERPRINT
    assert solve.provenance.licence_kind == "full"


def test_the_licence_kind_is_the_one_the_settings_name(rig: Rig) -> None:
    rig.settings.set_pricing_model({"licence_kind": "limited"})

    assert solved(rig).provenance.licence_kind == "limited"


@pytest.mark.parametrize("code", [SOLVER_SIZE_LIMITED, SOLVER_NO_SOLUTION, STAGE_ERROR])
def test_a_failure_the_settings_name_is_the_outcome_with_its_reason(rig: Rig, code: str) -> None:
    rig.settings.set_pricing_model({"fail_at": {"step": "pricing_model", "code": code}})

    outcome = rig.solve()

    assert outcome.failure_code == code
    assert outcome.failure_reason
    assert outcome.solve is None
    assert not (rig.folder / "solution.json").exists()


def test_a_failure_named_for_another_step_does_not_fail_the_solve(rig: Rig) -> None:
    rig.settings.set_pricing_model({"fail_at": {"step": "routes", "code": STAGE_ERROR}})

    assert rig.solve().failure_code is None


def test_a_stop_signal_stops_the_solve_and_writes_nothing(rig: Rig) -> None:
    stop = threading.Event()
    stop.set()

    outcome = rig.solve(stop=stop)

    assert outcome.stopped is True
    assert outcome.solve is None
    assert not (rig.folder / "solution.json").exists()


def test_the_model_offers_fewer_options_than_the_flat_scheme(rig: Rig) -> None:
    offered = {row.arc_id for row in solved(rig).rows if row.type == "PT+Bike"}

    assert len(offered) < len(arcs(rig, "arcs_pt_bike"))
