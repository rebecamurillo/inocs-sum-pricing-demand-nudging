from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.pricing_version_view import PricingVersionView, build_view
from pricing_demo.domain.city_instances import FIRST_PERIOD_KEY, InstanceVersionNotFound
from pricing_demo.domain.pricing_versions import (
    InstanceNotBuilt,
    UnknownBasedOn,
    duplicated_goals,
    new_draft_goals,
)
from pricing_demo.domain.runs import RunState


class CreatePricingVersion:
    """Starts a pricing version on a built instance version: from the defaults, keeping the
    fare, parking fee, options shown and flat price of the last sealed one, or as a copy of
    `based_on`."""

    def __init__(
        self,
        instances: CityInstances,
        builds: Builds,
        pricing: PricingVersions,
        clock: Clock,
    ) -> None:
        self._instances = instances
        self._builds = builds
        self._pricing = pricing
        self._clock = clock

    def execute(
        self, instance_version_id: str, name: str | None, based_on_id: str | None
    ) -> PricingVersionView:
        if self._instances.get_version(instance_version_id) is None:
            raise InstanceVersionNotFound(instance_version_id)
        built = self._builds.latest_build_states([instance_version_id])
        if built.get(instance_version_id) is not RunState.SUCCEEDED:
            raise InstanceNotBuilt(instance_version_id)
        if based_on_id is not None:
            source = self._pricing.get(based_on_id)
            if source is None or source.instance_version_id != instance_version_id:
                raise UnknownBasedOn(based_on_id)
            goals = duplicated_goals(source.goals)
            kept_from_id: str | None = based_on_id
        else:
            previous = self._pricing.previous_sealed(instance_version_id)
            goals = new_draft_goals(previous.goals if previous else None)
            kept_from_id = previous.id if previous else None
        version = self._pricing.create_draft(
            instance_version_id,
            name,
            goals,
            f"{instance_version_id}.{FIRST_PERIOD_KEY}",
            based_on_id,
            self._clock.now(),
            kept_from_id,
        )
        return build_view(version, "draft", self._instances, self._pricing)
