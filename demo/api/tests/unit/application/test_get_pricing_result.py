from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.domain.derived_result import DERIVATION_VERSION
from pricing_demo.domain.pricing_versions import (
    PricingVersionNotFound,
    ResultNotFound,
    new_draft_goals,
)
from pricing_demo.domain.runs import RunState
from pricing_demo.domain.traveller_simulation import BalancedScore
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.pricing_versions import sealed_pricing_version
from tests.support.results import PERIOD, ResultRig
from tests.support.runs import T0
from tests.support.simulations import simulate_under


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_a_finished_version_has_a_result_with_every_number_sourced(rig: ResultRig) -> None:
    version = rig.finished()

    result = rig.result.execute(version)

    assert result.period_id == PERIOD
    assert result.headline["ridership"].source == "model"
    assert result.headline["mean_bike_price"].source == "derived"
    assert result.headline["stations_empty_start"].source == "input"
    assert {item.group for item in result.headline.values()} == {"headline"}
    assert set(result.model_split) == {
        "travellers_pt_bike",
        "travellers_pt_only",
        "travellers_car",
        "modal_split_pt_bike",
        "modal_split_pt_only",
        "modal_split_car",
    }
    assert {item.source for item in result.model_split.values()} == {"model"}
    assert sum(
        result.model_split[f"modal_split_{mode}"].value for mode in ("pt_bike", "pt_only", "car")
    ) == pytest.approx(1.0)


def test_each_goal_has_the_models_value_and_both_simulated_values_and_their_change(
    rig: ResultRig,
) -> None:
    version = rig.finished()

    result = rig.result.execute(version)

    assert [item.name for item in result.goals] == [
        "ridership",
        "revenue",
        "cost",
        "profit",
        "mean_bike_price",
        "stations_empty",
        "stations_full",
    ]
    # The placeholder rule sends every traveller of the fake city to public transport alone:
    # no bike ride, so no mean price per ride (absent, never 0).
    for goal in result.goals:
        assert goal.model is not None
        if goal.name == "mean_bike_price":
            assert (goal.model_prices, goal.flat, goal.change) == (None, None, None)
            continue
        assert goal.model_prices is not None
        assert goal.flat is not None
        assert goal.model_prices.source == goal.flat.source == "simulation"
        assert goal.change is not None
        assert goal.change.value == pytest.approx(goal.model_prices.value - goal.flat.value)
    ridership = result.goals[0]
    assert ridership.model is not None
    assert ridership.model.source == "model"
    revenue = next(item for item in result.goals if item.name == "revenue")
    assert revenue.model is not None
    assert revenue.model.source == "derived"


def test_the_simulated_goals_come_from_the_stored_simulations(rig: ResultRig) -> None:
    version = rig.finished()
    result = rig.result.execute(version)

    for simulation in result.simulations:
        stored = rig.rig.simulations.summary_of(simulation.link.simulation_key)
        assert stored is not None
        assert simulation.goals["ridership"].value == stored.travellers_per_mode.get("pt_bike", 0)
        assert simulation.goals["revenue"].value == stored.bike_revenue_chf
        assert simulation.goals["cost"].value == pytest.approx(0.6 * stored.bike_rides)
    assert [item.link.price_scheme for item in result.simulations] == ["model_prices", "flat"]


def test_a_simulation_says_whether_its_rule_is_the_current_one(rig: ResultRig) -> None:
    version = rig.finished()

    assert [item.rule_current for item in rig.result.execute(version).simulations] == [False, False]

    rig.current_rule(BalancedScore())
    assert [item.rule_current for item in rig.result.execute(version).simulations] == [True, True]

    rig.current_rule(BalancedScore(0.6, 0.4, rule_version=2))
    assert [item.rule_current for item in rig.result.execute(version).simulations] == [
        False,
        False,
    ]


def test_the_latest_simulation_of_each_scheme_is_shown_and_all_of_them_are_listed(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    newer = BalancedScore(0.6, 0.4, rule_version=2)
    simulate_under(rig.rig.simulations, version, PERIOD, newer)
    rig.current_rule(newer)

    result = rig.result.execute(version)

    assert [item.link.rule_version for item in result.simulations] == [2, 2]
    assert [item.rule_current for item in result.simulations] == [True, True]
    assert len(result.simulation_history) == 4
    for item in result.simulation_history:
        assert item.bike_rides.source == item.revenue.source == item.cost.source == "simulation"


def test_the_solve_quality_and_the_package_summary_are_in_the_advanced_group_only(
    rig: ResultRig,
) -> None:
    version = rig.finished()

    result = rig.result.execute(version)

    assert {item.group for item in result.advanced.values()} == {"advanced"}
    for name in ("solver_status", "objective_value", "gap_pct", "solution_time_s"):
        assert name in result.advanced
        assert name not in result.headline
    assert result.advanced["objective_value"].source == "model"
    assert result.advanced["package_avg_bike_price_offered"].source == "package_summary"
    assert result.advanced["package_avg_bike_price_multimodal"].source == "package_summary"
    assert result.advanced["parameter_cost_bike"].value == 0.6
    assert result.advanced["parameter_P_bar"].value == 0.6
    assert result.advanced["parameter_theta"].value == 0.5
    assert result.solver_status_name == "OPTIMAL"
    # The fake's objective is not the model's: the terms are not returned, the residual is.
    assert not any(name.startswith("objective_term_") for name in result.advanced)
    assert result.advanced["objective_residual"].value > 1e-6


def test_the_coefficients_come_from_the_fingerprint_and_are_null_without_it(
    tmp_path: Path,
) -> None:
    with_fingerprint = ResultRig(tmp_path / "a")
    version = with_fingerprint.finished()
    coefficients = with_fingerprint.result.execute(version).coefficients
    assert coefficients is not None
    assert coefficients["ASC_PT"] is not None
    assert coefficients["ASC_PT"].value == -0.756
    assert coefficients["ASC_PT"].source == "input"

    without = ResultRig(tmp_path / "b", with_fingerprint=False)
    assert without.result.execute(without.finished()).coefficients is None


def test_a_coefficient_the_package_source_did_not_show_is_null(tmp_path: Path) -> None:
    rig = ResultRig(tmp_path)
    rig.fingerprints.clear()
    rig.fingerprints.record(replace(FAKE_FINGERPRINT, choice_coefficients={"ASC_PT": -1.0}), T0)

    coefficients = rig.result.execute(rig.finished()).coefficients

    assert coefficients is not None
    assert coefficients["ASC_PT"] is not None
    assert coefficients["ASC_BIKE"] is None


def test_the_provenance_names_the_run_the_solver_the_inputs_and_the_dates(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    run = rig.rig.pricing.latest_run(version)
    assert run is not None

    provenance = rig.result.execute(version).provenance

    assert provenance.run_id == run.id
    assert provenance.derivation_version == DERIVATION_VERSION
    assert provenance.gurobi_version == "fake"
    assert provenance.licence_kind == "full"
    assert provenance.package_commit == "0" * 40
    assert provenance.package_dirty is False
    assert provenance.package_fingerprint == "f" * 64
    assert set(provenance.input_keys) == {"area", "hubs", "routes", "travellers_and_bikes"}
    assert provenance.gtfs_sha256 is not None
    assert provenance.gbfs_sha256 is not None
    assert provenance.timetable_valid_from is not None
    assert provenance.routing_date is not None
    assert provenance.routing_date_provisional is True
    assert provenance.bike_stations_fetched_at is not None


@pytest.mark.parametrize("use_case", ["result", "hub_pairs", "hubs"])
def test_an_unknown_version_is_not_found(rig: ResultRig, use_case: str) -> None:
    with pytest.raises(PricingVersionNotFound):
        getattr(rig, use_case).execute("geneva-3km.v1.Z")


@pytest.mark.parametrize("use_case", ["result", "hub_pairs", "hubs"])
def test_a_draft_has_no_result(rig: ResultRig, use_case: str) -> None:
    version = rig.version()

    with pytest.raises(ResultNotFound):
        getattr(rig, use_case).execute(version)


@pytest.mark.parametrize("state", [RunState.QUEUED, RunState.RUNNING, RunState.FAILED])
def test_a_version_whose_latest_run_did_not_succeed_has_no_result(
    rig: ResultRig, state: RunState
) -> None:
    version = rig.finished()
    run = rig.rig.pricing.latest_run(version)
    assert run is not None
    rig.rig.runs.update(run.id, lambda item: replace(item, state=state))

    with pytest.raises(ResultNotFound):
        rig.result.execute(version)


def test_a_version_whose_summary_is_missing_has_no_result(rig: ResultRig) -> None:
    version = rig.finished()
    rig.rig.solves._summaries.clear()

    with pytest.raises(ResultNotFound):
        rig.result.execute(version)


def test_a_version_missing_one_of_its_two_simulations_has_no_result(rig: ResultRig) -> None:
    version = rig.finished()
    rig.rig.simulations._links = {
        slot: link for slot, link in rig.rig.simulations._links.items() if slot[2] != "flat"
    }

    with pytest.raises(ResultNotFound):
        rig.result.execute(version)


def test_a_period_the_version_does_not_price_has_no_result(rig: ResultRig) -> None:
    version = rig.finished()

    with pytest.raises(ResultNotFound):
        rig.result.execute(version, "geneva-3km.v1.tue-08")
    assert rig.result.execute(version, PERIOD).period_id == PERIOD


def test_a_sealed_version_with_a_succeeded_run_and_no_stored_solve_has_no_result(
    rig: ResultRig,
) -> None:
    version = rig.rig.pricing.create_draft(
        "geneva-3km.v1", None, new_draft_goals(None), PERIOD, None, T0
    ).id
    sealed_pricing_version(rig.rig, version, RunState.SUCCEEDED)
    simulate_under(rig.rig.simulations, version, PERIOD, BalancedScore())

    with pytest.raises(ResultNotFound):
        rig.result.execute(version)
