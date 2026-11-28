from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.instance_version_view import InstanceVersionView, build_view
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.package_fingerprints import PackageFingerprints
from pricing_demo.domain.city_instances import InstanceVersionNotFound


class GetInstanceVersion:
    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        planning: BuildPlanning,
        built: BuiltCounts,
        fingerprints: PackageFingerprints,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._planning = planning
        self._built = built
        self._fingerprints = fingerprints

    def execute(self, version_id: str) -> InstanceVersionView:
        version = self._instances.get_version(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        return build_view(
            version,
            self._instances,
            self._datasets,
            self._planning,
            self._built,
            self._fingerprints,
        )
