from collections.abc import Mapping

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.instance_version_view import InstanceVersionView, build_view
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.domain.city_instances import (
    InstanceVersionNotFound,
    Number,
    VersionSealed,
)


class UpdateInstanceVersion:
    """Stores the values as sent and reports the rules; nothing is corrected."""

    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        planning: BuildPlanning,
        built: BuiltCounts,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._planning = planning
        self._built = built

    def execute(self, version_id: str, changes: Mapping[str, Number]) -> InstanceVersionView:
        version = self._instances.get_version(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        if version.status == "sealed":
            raise VersionSealed(version_id)
        updated = self._instances.update_draft_parameters(version_id, changes)
        return build_view(updated, self._instances, self._datasets, self._planning, self._built)
