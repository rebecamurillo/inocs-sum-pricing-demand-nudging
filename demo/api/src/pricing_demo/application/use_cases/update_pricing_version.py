from collections.abc import Mapping

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.pricing_version_view import PricingVersionView, build_view
from pricing_demo.domain.city_instances import Number, VersionSealed
from pricing_demo.domain.pricing_versions import PricingVersionNotFound


class UpdatePricingVersion:
    """Stores the values as sent and reports the rules; nothing is corrected."""

    def __init__(self, instances: CityInstances, pricing: PricingVersions) -> None:
        self._instances = instances
        self._pricing = pricing

    def execute(
        self, version_id: str, changes: Mapping[str, Number], name: str | None = None
    ) -> PricingVersionView:
        version = self._pricing.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        if version.status == "sealed":
            raise VersionSealed(version_id)
        updated = self._pricing.update_draft(version_id, changes, name)
        return build_view(updated, "draft", self._instances, self._pricing)
