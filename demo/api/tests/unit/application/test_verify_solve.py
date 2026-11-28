import threading
from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.application.errors import SolveNotFound, SolveNotVerifiable
from pricing_demo.application.ports.pricing_solver import SolveOutcome, SolveRequest
from pricing_demo.application.use_cases.verify_solve import VerifySolve, VerifySolveResult
from pricing_demo.domain.failure_codes import SOLVER_NO_SOLUTION
from pricing_demo.domain.pricing_keys import solve_id
from pricing_demo.domain.solve_verification import report_lines
from pricing_demo.domain.traveller_simulation import BalancedScore, StationEnd
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from tests.support.pricing_runs import PricingRig


class Rig(PricingRig):
    def __init__(self, folder: Path) -> None:
        super().__init__(folder)
        self.folder = folder
        self.version_id = self.version()
        self.run(self.version_id)
        self.solve = solve_id(self.version_id, "mon-08")
        self.verify = VerifySolve(
            self.rig.solves,
            self.rig.pricing,
            self.rig.simulations,
            self.rig.artifacts,
            self.files,
            self.rig.read_model,
            FakePricingSolver(self.settings, self.rig.waiter),
            self.rig.clock,
        )

    def snapshot(self) -> tuple[object, ...]:
        solves, simulations = self.rig.solves, self.rig.simulations
        return (
            dict(solves._rows),
            dict(solves._versions),
            dict(solves._summaries),
            dict(simulations._simulations),
            dict(simulations._links),
            dict(self.rig.artifacts.links_of(self.version_id)),
        )

    def scratch_folders(self) -> list[Path]:
        runs = self.folder / "runs"
        return (
            [item for item in runs.iterdir() if item.name.startswith("verify-")]
            if runs.exists()
            else []
        )

    def key(self) -> str:
        key = self.rig.solves.solve_key_of(
            self.version_id, f"{self.version_id.rsplit('.', 1)[0]}.mon-08"
        )
        assert key is not None
        return key


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def result_of(rig: Rig) -> VerifySolveResult:
    return rig.verify.execute(rig.solve, threading.Event())


def test_a_stored_solve_re_run_on_the_same_fakes_matches(rig: Rig) -> None:
    before = rig.snapshot()

    result = result_of(rig)

    assert result.failure is None
    assert result.verification is not None
    assert result.verification.matches
    lines = report_lines(rig.solve, result.verification)
    assert lines[-1] == f"verify {rig.solve}: match"
    # The solve, then the modes, choices, pairs and stations of each scheme.
    assert len(result.verification.tables) == 1 + 4 * 2
    assert rig.snapshot() == before
    assert rig.scratch_folders() == []


def test_a_changed_stored_solve_row_is_reported_with_its_hub_pair_option_and_both_values(
    rig: Rig,
) -> None:
    key = rig.key()
    rows, ods = rig.rig.solves._rows[key]
    index = next(i for i, row in enumerate(rows) if row.type == "PT+Bike")
    stored_price = rows[index].bike_price
    rig.rig.solves._rows[key] = (
        (
            *rows[:index],
            replace(rows[index], bike_price=(stored_price or 0.0) + 1),
            *rows[index + 1 :],
        ),
        ods,
    )

    result = result_of(rig)

    assert result.verification is not None
    assert not result.verification.matches
    lines = [
        line
        for line in report_lines(rig.solve, result.verification)
        if line.startswith("solve_rows [")
    ]
    assert lines == [
        f"solve_rows [{rows[index].origin_hub}>{rows[index].destination_hub} {rows[index].arc_id}] "
        f"bike_price: stored {(stored_price or 0.0) + 1}, re-run {stored_price}"
    ]


@pytest.mark.parametrize("scheme", ["flat", "model_prices"])
def test_a_changed_stored_station_row_is_reported_under_its_scheme(rig: Rig, scheme: str) -> None:
    link = next(
        item for item in rig.rig.simulations.links_of(rig.version_id) if item.price_scheme == scheme
    )
    simulation = rig.rig.simulations._simulations[link.simulation_key]
    ends = simulation.outputs.stations_end
    moved = StationEnd(ends[0].station_id, ends[0].bikes + 1, ends[0].capacity)
    rig.rig.simulations._simulations[link.simulation_key] = replace(
        simulation, outputs=replace(simulation.outputs, stations_end=(moved, *ends[1:]))
    )

    result = result_of(rig)

    assert result.verification is not None
    lines = [
        line
        for line in report_lines(rig.solve, result.verification)
        if line.startswith("simulation_stations ") and "[" in line
    ]
    assert lines == [
        f"simulation_stations {scheme} (balanced-score v1) [{moved.station_id}] bikes_end: "
        f"stored {moved.bikes}, re-run {ends[0].bikes}"
    ]
    assert report_lines(rig.solve, result.verification)[-1] == f"verify {rig.solve}: differ"


def test_a_changed_stored_choice_is_reported_with_the_scheme_and_its_key(rig: Rig) -> None:
    link = next(
        item for item in rig.rig.simulations.links_of(rig.version_id) if item.price_scheme == "flat"
    )
    simulation = rig.rig.simulations._simulations[link.simulation_key]
    first = simulation.outputs.options[0]
    changed = replace(first, travellers=first.travellers + 1)
    rig.rig.simulations._simulations[link.simulation_key] = replace(
        simulation,
        outputs=replace(simulation.outputs, options=(changed, *simulation.outputs.options[1:])),
    )

    result = result_of(rig)

    assert result.verification is not None
    assert (
        f"simulation_choices flat (balanced-score v1) "
        f"[{first.origin_hub}>{first.destination_hub} {first.arc_id}] travellers: "
        f"stored {changed.travellers}, re-run {first.travellers}"
    ) in report_lines(rig.solve, result.verification)


def test_an_unknown_solve_id_cannot_be_verified(rig: Rig) -> None:
    with pytest.raises(SolveNotFound):
        rig.verify.execute("geneva-3km.v1.Z.mon-08", threading.Event())


def test_a_solve_without_a_stored_simulation_cannot_be_verified(rig: Rig) -> None:
    rig.rig.simulations.drop_version([rig.version_id])
    before = rig.snapshot()

    with pytest.raises(SolveNotVerifiable):
        result_of(rig)

    assert rig.snapshot() == before
    assert rig.scratch_folders() == []


def test_a_rule_the_worker_cannot_build_cannot_be_verified(tmp_path: Path) -> None:
    rig = PricingRig(tmp_path, BalancedScore(rule_id="other-rule"))
    version = rig.version()
    rig.run(version)
    verify = VerifySolve(
        rig.rig.solves,
        rig.rig.pricing,
        rig.rig.simulations,
        rig.rig.artifacts,
        rig.files,
        rig.rig.read_model,
        FakePricingSolver(rig.settings, rig.rig.waiter),
        rig.rig.clock,
    )

    with pytest.raises(SolveNotVerifiable, match="other-rule"):
        verify.execute(solve_id(version, "mon-08"), threading.Event())


def test_a_re_solve_that_fails_is_a_failure_and_leaves_no_folder(rig: Rig) -> None:
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "pricing_model", "code": SOLVER_NO_SOLUTION}}
    )
    before = rig.snapshot()

    result = result_of(rig)

    assert result.verification is None
    assert result.failure is not None
    assert result.failure[0] == SOLVER_NO_SOLUTION
    assert rig.snapshot() == before
    assert rig.scratch_folders() == []


def test_a_stopped_re_run_is_a_failure_and_leaves_no_folder(rig: Rig) -> None:
    stop = threading.Event()
    stop.set()

    result = rig.verify.execute(rig.solve, stop)

    assert result.verification is None
    assert result.failure is not None
    assert result.failure[0] == "stopped"
    assert rig.scratch_folders() == []


def test_the_scratch_folder_is_removed_when_the_solver_raises(rig: Rig) -> None:
    class Raising:
        def solve(self, request: SolveRequest, stop: object) -> SolveOutcome:
            assert request.working_dir.exists()
            raise RuntimeError("the solver crashed")

    verify = VerifySolve(
        rig.rig.solves,
        rig.rig.pricing,
        rig.rig.simulations,
        rig.rig.artifacts,
        rig.files,
        rig.rig.read_model,
        Raising(),
        rig.rig.clock,
    )

    with pytest.raises(RuntimeError, match="crashed"):
        verify.execute(rig.solve, threading.Event())

    assert rig.scratch_folders() == []
