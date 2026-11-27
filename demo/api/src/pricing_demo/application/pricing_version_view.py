"""A pricing version as a client reads it: its state, its periods and the rule results."""

from dataclasses import dataclass

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.domain.city_instances import InstancePeriod
from pricing_demo.domain.pricing_rules import PricingRuleResult, check_pricing_rules
from pricing_demo.domain.pricing_versions import PricingState, PricingVersion


@dataclass(frozen=True)
class PricingVersionView:
    version: PricingVersion
    state: PricingState
    periods: tuple[InstancePeriod, ...]
    rules: tuple[PricingRuleResult, ...]


def build_view(
    version: PricingVersion,
    state: PricingState,
    instances: CityInstances,
    pricing: PricingVersions,
) -> PricingVersionView:
    period_ids = set(pricing.period_ids(version.id))
    periods = tuple(
        period
        for period in instances.periods_of(version.instance_version_id)
        if period.id in period_ids
    )
    return PricingVersionView(version, state, periods, tuple(check_pricing_rules(version.goals)))
