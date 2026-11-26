from collections.abc import Sequence

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.domain.city_instances import InstanceWithVersions


class ListCityInstances:
    def __init__(self, instances: CityInstances) -> None:
        self._instances = instances

    def execute(self) -> Sequence[InstanceWithVersions]:
        return self._instances.menu()
