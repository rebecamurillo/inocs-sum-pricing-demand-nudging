from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.read_model import HubRow
from pricing_demo.domain.runs import StepName


class ListHubs:
    """The hubs of the version, read from the read model; none until it is built."""

    def __init__(
        self, instances: CityInstances, artifacts: Artifacts, read_model: ReadModel
    ) -> None:
        self._instances = instances
        self._artifacts = artifacts
        self._read_model = read_model

    def execute(self, version_id: str) -> list[HubRow]:
        if self._instances.get_version(version_id) is None:
            raise InstanceVersionNotFound(version_id)
        key = self._artifacts.links_of(version_id).get(StepName.HUBS)
        return self._read_model.hubs(key) if key else []
