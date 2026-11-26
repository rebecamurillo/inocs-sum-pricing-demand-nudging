from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_instances import CityInstances
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


class ListCityInstances:
    def __init__(self, instances: CityInstances, builds: Builds) -> None:
        self._instances = instances
        self._builds = builds

    def execute(self) -> Sequence[InstanceMenuEntry]:
        menu = self._instances.menu()
        latest = self._builds.latest_build_states(
            [version.id for entry in menu for version in entry.versions]
        )
        return [
            InstanceMenuEntry(
                entry.instance,
                entry.versions,
                {
                    version.id: version_state(version.status, latest.get(version.id))
                    for version in entry.versions
                },
            )
            for entry in menu
        ]
