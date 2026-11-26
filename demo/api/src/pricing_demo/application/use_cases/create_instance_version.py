from pricing_demo.application.errors import UnknownStartVersion
from pricing_demo.application.instance_version_view import InstanceVersionView, build_view
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.clock import Clock
from pricing_demo.domain.city_instances import CityInstanceNotFound, first_period


class CreateInstanceVersion:
    def __init__(self, instances: CityInstances, datasets: CityDatasets, clock: Clock) -> None:
        self._instances = instances
        self._datasets = datasets
        self._clock = clock

    def execute(self, instance_id: str, based_on_id: str) -> InstanceVersionView:
        instance = self._instances.get_instance(instance_id)
        if instance is None:
            raise CityInstanceNotFound(instance_id)
        based_on = self._instances.get_version(based_on_id)
        if based_on is None:
            raise UnknownStartVersion(based_on_id)
        dataset = self._datasets.get(instance.dataset_id)
        assert dataset is not None  # the instance's foreign key
        draft = self._instances.create_draft(
            instance_id,
            based_on.id,
            based_on.parameters,
            self._clock.now(),
            lambda version: first_period(version, dataset),
        )
        return build_view(draft, self._instances, self._datasets)
