from pathlib import Path

import pytest

from pricing_demo.application.use_cases.quote_trip import TripQuote
from pricing_demo.domain.pricing_versions import PricingVersionNotFound, ResultNotFound
from pricing_demo.domain.trip_quotes import MalformedPoint, NoPoint, PeriodNotPriced
from tests.support.results import ResultRig
from tests.support.trips import INSTANCE_CHANGES, ROUTE_FAILURES, at, near


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path, route_failures=ROUTE_FAILURES, instance_changes=INSTANCE_CHANGES)


@pytest.fixture
def version(rig: ResultRig) -> str:
    return rig.finished()


def quote(rig: ResultRig, version: str, origin: str | None, destination: str | None) -> TripQuote:
    return rig.quote.execute(version, None, origin, destination)


def test_two_points_in_hubs_of_a_pair_with_options_are_priced(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, near("H1"), near("H3"))

    assert found.status == "priced"
    assert found.no_car_option is False
    assert found.from_point is not None
    assert found.from_point.status == "matched"
    assert found.from_point.hub_id == "H1"
    assert found.from_point.hub_name.startswith("Fake stop H1-")  # type: ignore[union-attr]
    assert found.from_point.nearest_stop_name
    assert found.from_point.distance_to_hub_centre_m is not None
    assert found.from_point.distance_to_hub_centre_m.value == pytest.approx(20, rel=0.05)
    assert found.from_point.distance_to_hub_centre_m.unit == "m"
    assert (found.origin_hub.hub_id, found.destination_hub.hub_id) == ("H1", "H3")  # type: ignore[union-attr]
    assert [option.mode for option in found.options] == ["pt_bike", "pt_only", "car"]


def test_the_price_make_up_of_every_option_is_the_domain_function_of_the_goals(
    rig: ResultRig, version: str
) -> None:
    goals = rig.rig.pricing.get(version).goals  # type: ignore[union-attr]
    found = quote(rig, version, near("H1"), near("H3"))

    by_mode = {option.mode: option for option in found.options}
    bike = by_mode["pt_bike"]
    assert bike.bike_price is not None
    assert bike.price.value == bike.bike_legs.value * bike.bike_price.value + goals.pt_fare_chf
    assert by_mode["pt_only"].price.value == goals.pt_fare_chf
    car = by_mode["car"]
    assert car.car_cost is not None
    assert car.price.value == car.car_cost.value + goals.car_parking_fee_chf
    for option in found.options:
        assert option.duration_s.value > 0
        assert option.legs
        assert option.flow is not None


def test_exactly_one_option_per_mode_is_the_most_taken(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, near("H1"), near("H3"))

    assert [option.mode for option in found.options if option.most_taken] == [
        "pt_bike",
        "pt_only",
        "car",
    ]


def test_a_quote_with_only_a_from_point_is_one_point(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, near("H1"), None)

    assert found.status == "one_point"
    assert found.from_point is not None
    assert found.to_point is None
    assert found.origin_hub is not None
    assert found.destination_hub is None
    assert found.options == ()


def test_a_quote_with_only_a_to_point_is_one_point(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, None, near("H3"))

    assert found.status == "one_point"
    assert found.destination_hub is not None


def test_a_point_outside_the_circle_is_outside_zone(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, near("H1"), at(4000, 0))

    assert found.status == "outside_zone"
    assert found.to_point is not None
    assert found.to_point.status == "outside_zone"
    assert found.to_point.hub_id is None


def test_a_point_far_from_every_hub_outline_is_no_hub_here(rig: ResultRig, version: str) -> None:
    found = quote(rig, version, near("H1"), at(0, 1800))

    assert found.status == "no_hub_here"
    assert found.to_point is not None
    assert found.to_point.nearest_hub_id == "H6"
    assert found.to_point.distance_from_outline_m is not None
    assert found.to_point.distance_from_outline_m.value > 300


def test_two_points_in_one_hub_are_same_hub(rig: ResultRig, version: str) -> None:
    assert quote(rig, version, near("H1", 10), near("H1", -10)).status == "same_hub"


def test_two_hubs_closer_than_the_minimum_trip_distance_are_under_minimum_distance(
    rig: ResultRig, version: str
) -> None:
    found = quote(rig, version, near("H1"), near("H2"))

    assert found.status == "under_minimum_distance"
    assert found.min_trip_distance_m is not None
    assert (found.min_trip_distance_m.value, found.min_trip_distance_m.unit) == (600, "m")
    assert found.options == ()


def test_a_pair_with_a_pt_bike_route_failure_is_no_route(rig: ResultRig, version: str) -> None:
    assert quote(rig, version, near("H1"), near("H6")).status == "no_route"


def test_a_pair_the_quality_check_removed_is_removed_by_the_quality_check(
    rig: ResultRig, version: str
) -> None:
    assert quote(rig, version, near("H3"), near("H4")).status == "removed_by_quality_check"


def test_a_pair_without_a_pt_bike_option_returns_the_other_options(
    rig: ResultRig, version: str
) -> None:
    found = quote(rig, version, near("H5"), near("H1"))

    assert found.status == "no_bike_option"
    assert [option.mode for option in found.options] == ["pt_only", "car"]
    assert found.no_car_option is False


def test_a_pair_with_a_car_route_failure_carries_no_car_option(
    rig: ResultRig, version: str
) -> None:
    found = quote(rig, version, near("H4"), near("H1"))

    assert found.status == "priced"
    assert found.no_car_option is True
    assert [option.mode for option in found.options] == ["pt_bike", "pt_only"]


def test_statuses_without_options_carry_no_car_flag(rig: ResultRig, version: str) -> None:
    assert quote(rig, version, near("H1"), near("H2")).no_car_option is None


def test_a_period_key_the_version_did_not_price_is_refused(rig: ResultRig, version: str) -> None:
    with pytest.raises(PeriodNotPriced):
        rig.quote.execute(version, "tue-17", near("H1"), near("H3"))


def test_the_period_key_of_the_version_is_accepted(rig: ResultRig, version: str) -> None:
    assert rig.quote.execute(version, "mon-08", near("H1"), near("H3")).status == "priced"


def test_no_point_is_refused(rig: ResultRig, version: str) -> None:
    with pytest.raises(NoPoint):
        quote(rig, version, None, None)


def test_a_malformed_point_is_refused_before_the_version_is_read(rig: ResultRig) -> None:
    with pytest.raises(MalformedPoint):
        quote(rig, "nope", "abc", None)


def test_an_unknown_pricing_version_is_refused(rig: ResultRig) -> None:
    with pytest.raises(PricingVersionNotFound):
        quote(rig, "geneva-3km.v1.Z", near("H1"), near("H3"))


def test_a_version_without_a_finished_result_has_no_result(rig: ResultRig) -> None:
    draft = rig.version()

    with pytest.raises(ResultNotFound):
        quote(rig, draft, near("H1"), near("H3"))
