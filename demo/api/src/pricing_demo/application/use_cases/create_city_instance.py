from dataclasses import dataclass

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.errors import (
    PackageDefaultsMissing,
    UnknownCityDataset,
    UnknownStartVersion,
)
from pricing_demo.application.instance_version_view import InstanceVersionView, build_view
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.package_fingerprints import PackageFingerprints
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    first_period,
    instance_slug,
    parameters_from_defaults,
    version_id,
)


@dataclass(frozen=True)
class FromPackageDefaults:
    pass


@dataclass(frozen=True)
class FromCopy:
    instance_version_id: str


StartFrom = FromPackageDefaults | FromCopy


class CreateCityInstance:
    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        fingerprints: PackageFingerprints,
        clock: Clock,
        planning: BuildPlanning,
        built: BuiltCounts,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._fingerprints = fingerprints
        self._clock = clock
        self._planning = planning
        self._built = built

    def execute(self, name: str, dataset_id: str, start_from: StartFrom) -> InstanceVersionView:
        slug = instance_slug(name)
        dataset = self._datasets.get(dataset_id)
        if dataset is None:
            raise UnknownCityDataset(dataset_id)
        if isinstance(start_from, FromCopy):
            source = self._instances.get_version(start_from.instance_version_id)
            if source is None:
                raise UnknownStartVersion(start_from.instance_version_id)
            parameters, based_on_id = source.parameters, source.id
        else:
            fingerprint = self._fingerprints.latest()
            if fingerprint is None:
                raise PackageDefaultsMissing()
            parameters = parameters_from_defaults(fingerprint.defaults, dataset.preset)
            based_on_id = None
        now = self._clock.now()
        draft_id = version_id(slug, 1)
        instance = CityInstance(slug, name, dataset_id, next_number=2, created_at=now)
        draft = InstanceVersion(draft_id, slug, 1, based_on_id, "draft", parameters, now)
        self._instances.create(instance, draft, first_period(draft_id, dataset))
        return build_view(draft, self._instances, self._datasets, self._planning, self._built)
