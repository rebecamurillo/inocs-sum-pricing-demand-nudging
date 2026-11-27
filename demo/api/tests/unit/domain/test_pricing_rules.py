import pytest

from pricing_demo.domain.pricing_rules import check_pricing_rules
from pricing_demo.domain.pricing_versions import PricingGoals, new_draft_goals

AMOUNTS = [
    ("cost_bike_chf", "Cost of one ride"),
    ("lowest_price_chf", "Lowest price of a ride"),
    ("ridership_weight", "Ridership weight"),
    ("station_balance_weight", "Station balance weight"),
    ("pt_fare_chf", "Public transport fare"),
    ("car_parking_fee_chf", "Car parking fee"),
    ("flat_price_per_ride_chf", "Flat price per ride"),
]


def _with(**changes: float) -> PricingGoals:

    return new_draft_goals(None).replacing(changes)


def test_the_defaults_break_no_rule() -> None:
    results = check_pricing_rules(new_draft_goals(None))

    assert len(results) == 8
    assert all(item.passed for item in results)


@pytest.mark.parametrize(("field", "name"), AMOUNTS)
def test_an_amount_under_zero_fails_with_its_value(field: str, name: str) -> None:
    results = check_pricing_rules(_with(**{field: -0.01}))

    failed = [item for item in results if not item.passed]
    assert [(item.field, item.value, item.message) for item in failed] == [
        (field, -0.01, f"{name} must be 0 or more: now -0.01")
    ]


@pytest.mark.parametrize(("field", "name"), AMOUNTS)
def test_zero_passes(field: str, name: str) -> None:
    assert all(item.passed for item in check_pricing_rules(_with(**{field: 0})))


def test_options_shown_must_be_at_least_one() -> None:
    failed = [i for i in check_pricing_rules(_with(max_displayed_options=0)) if not i.passed]

    assert [i.message for i in failed] == ["Options shown per hub pair must be at least 1: now 0"]
    assert all(i.passed for i in check_pricing_rules(_with(max_displayed_options=1)))


def test_a_value_is_reported_as_sent() -> None:
    goals = _with(max_displayed_options=1.5, cost_bike_chf=-3)

    results = check_pricing_rules(goals)

    assert goals.max_displayed_options == 1.5
    assert [i.message for i in results if not i.passed] == [
        "Cost of one ride must be 0 or more: now -3"
    ]
