from collections.abc import Sequence

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.pricing_version_view import PricingVersionView, build_view
from pricing_demo.domain.city_instances import InstanceVersionNotFound


class ListPricingVersions:
    def __init__(self, instances: CityInstances, pricing: PricingVersions) -> None:
        self._instances = instances
        self._pricing = pricing

    def execute(self, instance_version_id: str) -> Sequence[PricingVersionView]:
        if self._instances.get_version(instance_version_id) is None:
            raise InstanceVersionNotFound(instance_version_id)
        return [
            build_view(item.version, item.state, self._instances, self._pricing)
            for item in self._pricing.list_for(instance_version_id)
        ]
