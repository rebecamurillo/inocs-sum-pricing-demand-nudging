from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.read_model import RoutePairRow
from pricing_demo.domain.runs import StepName


class ListRoutePairs:
    """The hub pairs the routes step of the version routed: available once step 3 is linked to
    the version, so a map can draw the pairs while step 4 still runs."""

    def __init__(
        self, instances: CityInstances, artifacts: Artifacts, read_model: ReadModel
    ) -> None:
        self._instances = instances
        self._artifacts = artifacts
        self._read_model = read_model

    def execute(self, version_id: str) -> list[RoutePairRow]:
        if self._instances.get_version(version_id) is None:
            raise InstanceVersionNotFound(version_id)
        key = self._artifacts.links_of(version_id).get(StepName.ROUTES)
        return self._read_model.route_pairs(key) if key else []
