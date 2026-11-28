"""How long a step last took on the instance a run belongs to, for the run's reader."""

from collections.abc import Mapping

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.domain.runs import Run, RunKind, StepName


class StepDurations:
    """The seconds the pricing model last took on the data set and radius of a pricing run's
    instance version. Build steps have no figure here: their planned durations are the plan's."""

    def __init__(self, pricing_versions: PricingVersions, city_instances: CityInstances) -> None:
        self._pricing_versions = pricing_versions
        self._city_instances = city_instances

    def of(self, run: Run) -> Mapping[StepName, float]:
        if run.kind is not RunKind.PRICING:
            return {}
        version = self._pricing_versions.get(run.subject.id)
        instance_version = (
            self._city_instances.get_version(version.instance_version_id) if version else None
        )
        instance = (
            self._city_instances.get_instance(instance_version.instance_id)
            if instance_version
            else None
        )
        if instance_version is None or instance is None:
            return {}
        seconds = self._pricing_versions.last_pricing_model_duration_s(
            instance.dataset_id, instance_version.parameters.radius_m
        )
        return {} if seconds is None else {StepName.PRICING_MODEL: seconds}
