from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    version_state,
)


@dataclass(frozen=True)
class InstanceMenuEntry:
    """An instance with its versions by number, and the state of each version."""

    instance: CityInstance
    versions: Sequence[InstanceVersion]
    states: Mapping[str, str]
    pricing_letters: Mapping[str, Sequence[str]]


class ListCityInstances:
    def __init__(self, instances: CityInstances, builds: Builds, pricing: PricingVersions) -> None:
        self._instances = instances
        self._builds = builds
        self._pricing = pricing

    def execute(self) -> Sequence[InstanceMenuEntry]:
        menu = self._instances.menu()
        ids = [version.id for entry in menu for version in entry.versions]
        latest = self._builds.latest_build_states(ids)
        letters = self._pricing.letters_by_instance_version(ids)
        return [
            InstanceMenuEntry(
                entry.instance,
                entry.versions,
                {
                    version.id: version_state(version.status, latest.get(version.id))
                    for version in entry.versions
                },
                {version.id: letters.get(version.id, ()) for version in entry.versions},
            )
            for entry in menu
        ]
