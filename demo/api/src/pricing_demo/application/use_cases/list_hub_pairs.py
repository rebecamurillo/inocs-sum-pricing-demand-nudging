from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.domain.city_instances import InstanceVersionNotFound, PeriodNotFound
from pricing_demo.domain.read_model import HubPairRow
from pricing_demo.domain.runs import StepName


class ListHubPairs:
    """The hub pairs of one period of the version; the version's only period when none is
    named, nothing until it is built."""

    def __init__(
        self, instances: CityInstances, artifacts: Artifacts, read_model: ReadModel
    ) -> None:
        self._instances = instances
        self._artifacts = artifacts
        self._read_model = read_model

    def execute(self, version_id: str, period_id: str | None) -> list[HubPairRow]:
        if self._instances.get_version(version_id) is None:
            raise InstanceVersionNotFound(version_id)
        periods = self._instances.periods_of(version_id)
        if period_id is None:
            period_id = periods[0].id
        elif period_id not in {period.id for period in periods}:
            raise PeriodNotFound(version_id, period_id)
        key = self._artifacts.links_of(version_id).get(StepName.TRAVELLERS_AND_BIKES)
        return self._read_model.hub_pairs(key) if key else []
