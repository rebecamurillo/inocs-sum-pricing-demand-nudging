from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.pricing_version_view import PricingVersionView, build_view
from pricing_demo.domain.pricing_versions import PricingVersionNotFound


class GetPricingVersion:
    def __init__(self, instances: CityInstances, pricing: PricingVersions) -> None:
        self._instances = instances
        self._pricing = pricing

    def execute(self, version_id: str) -> PricingVersionView:
        version = self._pricing.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        for item in self._pricing.list_for(version.instance_version_id):
            if item.version.id == version_id:
                return build_view(item.version, item.state, self._instances, self._pricing)
        raise PricingVersionNotFound(version_id)
