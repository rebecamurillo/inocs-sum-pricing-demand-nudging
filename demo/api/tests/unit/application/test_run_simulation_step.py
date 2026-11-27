import threading
from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.application.ports.simulations import SimulationLink, StoredSimulation
from pricing_demo.domain.failure_codes import SIMULATION_CHECK_FAILED, SOLVER_NO_SOLUTION
from pricing_demo.domain.pricing_keys import KEPT_SIMULATION_REASON, KEPT_SOLVE_REASON
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import RunState, StepName, StepState
from pricing_demo.domain.traveller_simulation import (
    CHECK_CONSERVATION,
    BalancedScore,
    PriceScheme,
    SimulationCheckFailed,
    SimulationInstance,
    SimulationOutputs,
)
from pricing_demo.infrastructure.fakes.simulations import InMemorySimulations
from tests.support.pricing_runs import PERIOD, PricingRig


@pytest.fixture
def rig(tmp_path: Path) -> PricingRig:
    return PricingRig(tmp_path)


def links(rig: PricingRig, version: str) -> dict[str, str]:
    return {
        item.price_scheme: item.simulation_key for item in rig.rig.simulations.links_of(version)
    }


def simulation(rig: PricingRig, key: str) -> StoredSimulation:
    found = rig.rig.simulations.get(key)
    assert found is not None
    return found


class CountingRule(BalancedScore):
    """The rule, counting the simulations it runs."""

    calls = 0

    def simulate(self, instance: SimulationInstance, scheme: PriceScheme) -> SimulationOutputs:
        type(self).calls += 1
        return super().simulate(instance, scheme)


class BrokenRule(BalancedScore):
    def simulate(self, instance: SimulationInstance, scheme: PriceScheme) -> SimulationOutputs:
        raise SimulationCheckFailed(CHECK_CONSERVATION)


def test_a_run_simulates_with_the_models_prices_and_with_the_flat_price(rig: PricingRig) -> None:
    version = rig.version()

    run = rig.run(version)

    assert run.state is RunState.SUCCEEDED
    assert [item.state for item in run.steps] == [StepState.DONE, StepState.DONE]
    found = links(rig, version)
    assert set(found) == {"model_prices", "flat"}
    model, flat = simulation(rig, found["model_prices"]), simulation(rig, found["flat"])
    assert (model.scheme_kind, flat.scheme_kind) == ("model_prices", "flat")
    assert model.solve_key == rig.rig.solves.solve_key_of(version, PERIOD)
    assert (flat.flat_price_kind, flat.flat_price_amount_chf) == ("per_ride", 1.0)
    assert (flat.solve_key, model.flat_price_amount_chf) == (None, None)
    for stored in (model, flat):
        assert (stored.pt_fare_chf, stored.car_parking_fee_chf) == (2.0, 2.8)
        assert stored.outputs.rule_id == "balanced-score"
        assert stored.demonstrator_version == "0.1.0"
        assert stored.adapter == "domain"
    link = rig.rig.simulations.links_of(version)[0]
    assert (link.period_id, link.rule_id, link.rule_version) == (PERIOD, "balanced-score", 1)


def test_the_two_simulations_differ_when_the_flat_price_undercuts_the_model(
    rig: PricingRig,
) -> None:
    # A bike ride at a flat price of 0 costs a traveller the fare only, as public transport
    # alone does, and is a little faster: the flat scheme offers every bike option, the model
    # only the options it prices (and none from hub H6).
    version = rig.version(flat_price_per_ride_chf=0.0)
    rig.run(version)
    found = links(rig, version)

    model, flat = simulation(rig, found["model_prices"]), simulation(rig, found["flat"])

    assert flat.outputs.bike_rides > 0
    assert model.outputs.bike_rides == 0
    assert model.outputs.options != flat.outputs.options
    assert (
        sum(model.outputs.travellers_per_mode.values()) + model.outputs.unserved
        == sum(flat.outputs.travellers_per_mode.values()) + flat.outputs.unserved
    )


def test_the_step_reports_the_counts_of_each_simulation(rig: PricingRig) -> None:
    run = rig.run(rig.version())

    counts = run.steps[1].counts

    assert counts["reused"] == []
    for scheme in ("model_prices", "flat"):
        assert set(counts[scheme]) == {"travellers", "displaced", "bike_rides"}
        assert counts[scheme]["travellers"] > 0


def test_a_version_with_the_same_flat_price_fare_and_parking_fee_shares_the_flat_simulation(
    rig: PricingRig,
) -> None:
    first = rig.version()
    third = rig.version(cost_bike_chf=1.4, ridership_weight=3.0)
    rig.run(first)
    before = links(rig, first)

    run = rig.run(third)

    after = links(rig, third)
    assert after["flat"] == before["flat"]
    assert after["model_prices"] != before["model_prices"]
    assert run.steps[1].state is StepState.DONE
    assert run.steps[1].counts["reused"] == ["flat"]
    assert "flat" not in run.steps[1].counts
    flats = [
        key
        for key in {*links(rig, first).values(), *after.values()}
        if simulation(rig, key).scheme_kind == "flat"
    ]
    assert len(set(flats)) == 1


def test_a_different_fare_or_flat_price_makes_a_different_flat_simulation(rig: PricingRig) -> None:
    first = rig.version()
    rig.run(first)

    other_flat = rig.version(flat_price_per_ride_chf=2.5)
    rig.run(other_flat)

    assert links(rig, other_flat)["flat"] != links(rig, first)["flat"]
    # Same solver inputs: the model-price simulation is shared.
    assert links(rig, other_flat)["model_prices"] == links(rig, first)["model_prices"]


def test_a_version_identical_in_every_goal_keeps_both_steps(rig: PricingRig) -> None:
    first, second = rig.version(), rig.version()
    rig.run(first)

    run = rig.run(second)

    assert [item.state for item in run.steps] == [StepState.KEPT, StepState.KEPT]
    assert run.steps[0].reason == KEPT_SOLVE_REASON
    assert run.steps[1].reason == KEPT_SIMULATION_REASON
    assert run.state is RunState.SUCCEEDED
    assert links(rig, second) == links(rig, first)


def test_a_stopped_simulation_writes_nothing(rig: PricingRig) -> None:
    version = rig.version()
    queued = rig.rig.run_pricing.execute(version)
    rig.process.execute()
    rig.rig.runs.update(
        queued.id,
        lambda run: replace(
            run,
            state=RunState.RUNNING,
            steps=(run.steps[0], replace(run.steps[1], state=StepState.PENDING)),
        ),
    )
    stored_run = rig.stored(queued.id)
    rig.rig.simulations.drop_version([version])
    rig.rig.simulations.remove_unlinked()
    stop = threading.Event()
    stop.set()

    outcome = rig.simulation.execute(stored_run, stored_run.steps[1], stop)

    assert outcome.stopped is True
    assert rig.rig.simulations.links_of(version) == []


def test_a_broken_check_fails_the_step_keeps_the_solve_and_writes_no_simulation(
    rig: PricingRig,
) -> None:
    rig.use_rule(BrokenRule())
    version = rig.version()

    run = rig.run(version)

    assert (run.state, run.steps[0].state, run.steps[1].state) == (
        RunState.FAILED,
        StepState.DONE,
        StepState.FAILED,
    )
    assert run.failure is not None
    assert (run.failure.step, run.failure.code) == ("traveller_simulation", SIMULATION_CHECK_FAILED)
    assert "conservation" in run.failure.reason
    assert rig.rig.solves.solve_key_of(version, PERIOD) is not None
    assert rig.rig.simulations.links_of(version) == []


def test_run_again_after_a_broken_check_keeps_the_solve_and_simulates(rig: PricingRig) -> None:
    rig.use_rule(BrokenRule())
    version = rig.version()
    rig.run(version)
    rig.use_rule(BalancedScore())

    run = rig.run(version)

    assert run.state is RunState.SUCCEEDED
    assert [item.state for item in run.steps] == [StepState.KEPT, StepState.DONE]
    assert set(links(rig, version)) == {"model_prices", "flat"}


def test_a_solve_that_failed_leaves_the_simulation_step_unrun(rig: PricingRig) -> None:
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "pricing_model", "code": SOLVER_NO_SOLUTION}}
    )

    run = rig.run(rig.version())

    assert run.steps[1].state is StepState.PENDING


def test_a_simulation_runs_only_for_the_schemes_not_stored(rig: PricingRig) -> None:
    CountingRule.calls = 0
    rig.use_rule(CountingRule())
    first, third = rig.version(), rig.version(cost_bike_chf=1.4)

    rig.run(first)
    assert CountingRule.calls == 2
    rig.run(third)

    assert CountingRule.calls == 3


def test_a_version_without_a_stored_solve_fails_the_step_with_its_reason(rig: PricingRig) -> None:
    version = rig.version()
    queued = rig.rig.run_pricing.execute(version)

    outcome = rig.simulation.execute(queued, queued.steps[1], threading.Event())

    assert outcome.failure_code == STAGE_ERROR
    assert "solve" in (outcome.failure_reason or "")
    assert rig.simulation.keep(queued, queued.steps[1]) is False


def test_an_instance_stored_without_the_car_costs_fails_the_step_as_a_stage_error(
    rig: PricingRig,
) -> None:
    instance_key = rig.rig.artifacts.links_of("geneva-3km.v1")[StepName.TRAVELLERS_AND_BIKES]
    batch = rig.rig.read_model._batch(instance_key)  # the fake read model keeps its batches
    assert batch is not None
    bare = tuple(
        replace(row, car_cost_chf=None, parking_time_min=None) for row in batch.route_options
    )
    rig.rig.read_model.ingest(replace(batch, route_options=bare))
    version = rig.version()

    run = rig.run(version)

    assert run.state is RunState.FAILED
    assert run.failure is not None
    assert (run.failure.step, run.failure.code) == ("traveller_simulation", STAGE_ERROR)
    assert "ValueError" in run.failure.reason


class FailingStore(InMemorySimulations):
    def store(self, new: object, links: object) -> None:
        raise RuntimeError("the database went away")


def test_a_failed_store_fails_the_step_as_a_stage_error(rig: PricingRig) -> None:
    rig.simulation._simulations = FailingStore()
    version = rig.version()

    run = rig.run(version)

    assert run.failure is not None
    assert (run.failure.code, run.failure.reason) == (
        STAGE_ERROR,
        "RuntimeError: the database went away",
    )


def test_the_link_names_the_rule_it_was_made_with(rig: PricingRig) -> None:
    version = rig.version()
    rig.run(version)

    found: list[SimulationLink] = rig.rig.simulations.links_of(version)

    assert {(item.rule_id, item.rule_version) for item in found} == {("balanced-score", 1)}
