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
    kept_from: tuple[str, str] | None  # id and letter of the version the kept values came from
    last_duration_s: float | None  # the last pricing model step on this data set and radius


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
    kept = pricing.get(version.kept_from_id) if version.kept_from_id else None
    instance_version = instances.get_version(version.instance_version_id)
    instance = instances.get_instance(instance_version.instance_id) if instance_version else None
    duration = (
        pricing.last_pricing_model_duration_s(
            instance.dataset_id, instance_version.parameters.radius_m
        )
        if instance_version and instance
        else None
    )
    return PricingVersionView(
        version,
        state,
        periods,
        tuple(check_pricing_rules(version.goals)),
        (kept.id, kept.letter) if kept else None,
        duration,
    )
