"""The rules a pricing version's goals are checked against. Rules report; they never correct."""

from dataclasses import dataclass

from pricing_demo.domain.city_instances import Number
from pricing_demo.domain.pricing_versions import PricingGoals

# The plain name of each amount, as the form labels it.
AMOUNT_NAMES = (
    ("cost_bike_chf", "Cost of one ride"),
    ("lowest_price_chf", "Lowest price of a ride"),
    ("ridership_weight", "Ridership weight"),
    ("station_balance_weight", "Station balance weight"),
    ("pt_fare_chf", "Public transport fare"),
    ("car_parking_fee_chf", "Car parking fee"),
    ("flat_price_per_ride_chf", "Flat price per ride"),
)
OPTIONS_FIELD = "max_displayed_options"


@dataclass(frozen=True)
class PricingRuleResult:
    rule: str
    passed: bool
    field: str
    value: Number
    message: str


def _shown(value: Number) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def check_pricing_rules(goals: PricingGoals) -> list[PricingRuleResult]:
    values = goals.as_dict()
    results = [
        PricingRuleResult(
            f"{field}_zero_or_more",
            values[field] >= 0,
            field,
            values[field],
            f"{name} must be 0 or more: now {_shown(values[field])}",
        )
        for field, name in AMOUNT_NAMES
    ]
    options = values[OPTIONS_FIELD]
    results.append(
        PricingRuleResult(
            "options_shown_at_least_1",
            options >= 1,
            OPTIONS_FIELD,
            options,
            f"Options shown per hub pair must be at least 1: now {_shown(options)}",
        )
    )
    return results
