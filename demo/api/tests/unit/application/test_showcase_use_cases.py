from pathlib import Path

import pytest

from pricing_demo.domain.derived_result import derived_pair_bike_rides, offered_rides
from pricing_demo.domain.pricing_versions import (
    IsShowcase,
    NoResult,
    NoShowcase,
    PricingVersionNotFound,
    ResultNotFound,
)
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.traveller_simulation import BalancedScore
from tests.support.results import PERIOD, ResultRig


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_nothing_is_showcased_at_first(rig: ResultRig) -> None:
    with pytest.raises(NoShowcase):
        rig.get_showcase.execute()


def test_a_finished_version_is_marked_and_read_back_with_its_headline_numbers(
    rig: ResultRig,
) -> None:
    version = rig.finished()

    mark = rig.mark.execute(version)
    view = rig.get_showcase.execute()

    assert (mark.pricing_version_id, mark.period_id) == (version, PERIOD)
    assert view.mark == mark
    assert view.letter == "A"
    assert view.instance_version_id == "geneva-3km.v1"
    assert view.instance_version_name == "Geneva 3 km v1"
    assert view.headline["ridership"].source == "model"
    assert {item.group for item in view.headline.values()} == {"headline"}
    assert view.headline == rig.result.execute(version).headline


def test_a_new_mark_replaces_the_old_one(rig: ResultRig) -> None:
    first = rig.finished()
    second = rig.finished(flat_price_per_ride_chf=2.5)
    rig.mark.execute(first)

    rig.mark.execute(second)

    assert rig.get_showcase.execute().mark.pricing_version_id == second


def test_a_version_without_a_result_cannot_be_marked(rig: ResultRig) -> None:
    draft = rig.version()

    with pytest.raises(NoResult):
        rig.mark.execute(draft)
    assert rig.rig.showcase.current() is None


def test_a_period_the_version_does_not_price_cannot_be_marked(rig: ResultRig) -> None:
    version = rig.finished()

    with pytest.raises(NoResult):
        rig.mark.execute(version, "geneva-3km.v1.tue-08")


def test_an_unknown_version_cannot_be_marked(rig: ResultRig) -> None:
    with pytest.raises(PricingVersionNotFound):
        rig.mark.execute("geneva-3km.v1.Z")


def test_the_showcased_version_is_not_deleted_and_another_is(rig: ResultRig) -> None:
    first, second = rig.finished(), rig.finished(flat_price_per_ride_chf=2.5)
    rig.mark.execute(first)

    with pytest.raises(IsShowcase):
        rig.rig.pricing.delete(first)
    rig.rig.pricing.delete(second)

    assert rig.rig.pricing.get(first) is not None
    assert rig.rig.pricing.get(second) is None


def test_a_marked_version_that_lost_a_part_of_its_result_is_not_returned_as_showcase(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    rig.mark.execute(version)
    rig.rig.solves._summaries.clear()

    with pytest.raises(ResultNotFound):
        rig.get_showcase.execute()


def test_the_showcase_carries_the_scope_the_flat_price_and_the_study_circle(
    rig: ResultRig,
) -> None:
    version = rig.finished(flat_price_per_ride_chf=1.25)
    rig.mark.execute(version)

    view = rig.get_showcase.execute()

    assert view.dataset_id
    assert (view.city, view.period_label) == ("Geneva", "Monday 08:00\u201309:00")
    assert view.radius_km.value == 3
    assert (view.radius_km.unit, view.radius_km.source) == ("km", "input")
    assert view.flat_price.value == 1.25
    assert view.flat_price.source == "input"
    instance_version = rig.rig.instances.get_version("geneva-3km.v1")
    assert instance_version is not None
    assert view.circle_centre.lat.value == instance_version.parameters.center_lat
    assert view.circle_radius_m.value == instance_version.parameters.radius_m
    assert view.hubs
    assert all(hub.centre.lat.source == "input" for hub in view.hubs)
    numbers = [
        view.radius_km,
        view.car_share_flat,
        view.car_share_version,
        view.car_share_difference,
        view.flat_price,
        view.circle_radius_m,
    ]
    assert {item.group for item in numbers} == {"headline"}


def test_the_car_shares_are_in_points_and_the_difference_is_flat_minus_version(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    rig.mark.execute(version)
    links = rig.rig.simulations.links_of(version)
    shares = {}
    for link in links:
        summary = rig.rig.simulations.summary_of(link.simulation_key)
        assert summary is not None
        shares[link.price_scheme] = (
            100 * summary.travellers_per_mode.get("car", 0) / summary.travellers
        )

    view = rig.get_showcase.execute()

    assert view.car_share_flat.value == pytest.approx(shares["flat"])
    assert view.car_share_version.value == pytest.approx(shares["model_prices"])
    assert view.car_share_difference.value == pytest.approx(shares["flat"] - shares["model_prices"])
    assert {view.car_share_flat.source, view.car_share_difference.source} == {"simulation"}
    assert view.car_share_flat.unit == "points"


def test_the_rule_is_current_only_while_the_live_worker_runs_it(rig: ResultRig) -> None:
    version = rig.finished()
    rig.mark.execute(version)

    stale = rig.get_showcase.execute()
    rig.current_rule(BalancedScore())
    current = rig.get_showcase.execute()

    assert (stale.rule_id, stale.rule_version) == (current.rule_id, current.rule_version)
    assert stale.rule_version >= 1
    assert (stale.rule_current, current.rule_current) == (False, True)
    rig.current_rule(BalancedScore(0.6, 0.4, rule_version=2))
    assert rig.get_showcase.execute().rule_current is False


def test_the_hub_pairs_are_the_pairs_with_bike_rides_with_their_hub_centres(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    rig.mark.execute(version)
    found = rig.lookup.find(version)
    instance_key = rig.rig.artifacts.links_of("geneva-3km.v1")[StepName.TRAVELLERS_AND_BIKES]
    expected = derived_pair_bike_rides(
        offered_rides(
            rig.rig.solves.rows(found.solve.key), rig.rig.read_model.route_options(instance_key)
        )
    )

    view = rig.get_showcase.execute()

    assert expected
    assert {(item.origin_hub, item.destination_hub) for item in view.hub_pairs} == set(expected)
    centres = {hub.hub_id: hub.centre for hub in view.hubs}
    for pair in view.hub_pairs:
        rides, mean = expected[(pair.origin_hub, pair.destination_hub)]
        assert pair.bike_rides.value == pytest.approx(rides)
        assert pair.mean_bike_price.value == pytest.approx(mean)
        assert (pair.mean_bike_price.source, pair.bike_rides.source) == ("derived", "derived")
        assert pair.origin == centres[pair.origin_hub]
        assert pair.destination == centres[pair.destination_hub]
