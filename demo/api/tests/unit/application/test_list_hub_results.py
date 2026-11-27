from pathlib import Path

import pytest

from pricing_demo.domain.runs import StepName
from tests.support.results import PERIOD, ResultRig


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_each_hub_pair_of_the_instance_is_listed_in_order_with_its_options(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    instance_key = rig.rig.artifacts.links_of("geneva-3km.v1")[StepName.TRAVELLERS_AND_BIKES]

    items = rig.hub_pairs.execute(version)

    expected = [
        (pair.origin_hub, pair.destination_hub)
        for pair in rig.rig.read_model.hub_pairs(instance_key)
    ]
    assert [(item.numbers.origin_hub, item.numbers.destination_hub) for item in items] == expected
    options = [option for item in items for option in item.options]
    assert {option.arc_id for option in options} == {
        option.arc_id for option in rig.rig.read_model.route_options(instance_key)
    }
    assert all(option.duration_s.source == "trip_planner" for option in options)


def test_an_offered_option_has_its_price_and_riders_and_a_pair_without_one_has_no_price(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    rows = {
        row.arc_id: row
        for row in rig.rig.solves.rows(rig.rig.solves.solve_key_of(version, PERIOD) or "")
    }

    items = rig.hub_pairs.execute(version)

    offered = [option for item in items for option in item.options if option.bike_price is not None]
    assert offered
    for option in offered:
        assert option.bike_price is not None
        assert option.riders is not None
        assert option.bike_price.source == option.riders.source == "model"
        assert option.bike_price.value == rows[option.arc_id].bike_price
        assert option.bike_legs is not None
        assert option.bike_legs.source == "input"
    unpriced_pairs = [item for item in items if item.numbers.mean_bike_price is None]
    assert unpriced_pairs
    assert all(
        option.bike_price is None
        for item in unpriced_pairs
        for option in item.options
        if option.mode == "pt_bike"
    )
    priced = next(item for item in items if item.numbers.mean_bike_price is not None)
    assert priced.numbers.mean_bike_price is not None
    assert priced.numbers.mean_bike_price.source == "derived"
    assert priced.numbers.min_bike_price is not None
    assert priced.numbers.travellers["pt_bike"].source == "model"


def test_each_hub_is_listed_by_id_with_its_centre_and_rides(rig: ResultRig) -> None:
    version = rig.finished()

    items = rig.hubs.execute(version)

    assert [item.hub.hub_id for item in items] == sorted(item.hub.hub_id for item in items)
    assert items
    for item in items:
        assert item.numbers.hub_id == item.hub.hub_id
        assert item.numbers.rides_starting.source == "derived"
        assert item.numbers.rides_ending.value >= 0
    assert any(item.numbers.rides_starting.value > 0 for item in items)
    assert any(item.numbers.mean_bike_price is not None for item in items)
