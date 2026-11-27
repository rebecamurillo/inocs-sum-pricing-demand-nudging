from dataclasses import dataclass

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.showcase import Showcase, ShowcaseMark
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.application.use_cases.get_pricing_result import headline_numbers
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import NoShowcase


@dataclass(frozen=True)
class ShowcaseView:
    mark: ShowcaseMark
    letter: str
    instance_version_id: str
    instance_version_name: str
    headline: dict[str, Number]


class GetShowcase:
    """The showcased pricing version with its instance version's name, its letter and the
    headline numbers of its result. Raises `NoShowcase` when none is marked, and
    `ResultNotFound` when the marked version has lost a part of its result."""

    def __init__(self, showcase: Showcase, lookup: ResultLookup, instances: CityInstances) -> None:
        self._showcase = showcase
        self._lookup = lookup
        self._instances = instances

    def execute(self) -> ShowcaseView:
        mark = self._showcase.current()
        if mark is None:
            raise NoShowcase()
        found = self._lookup.find(mark.pricing_version_id, mark.period_id)
        version = found.version
        instance_version = self._instances.get_version(version.instance_version_id)
        instance = (
            None
            if instance_version is None
            else self._instances.get_instance(instance_version.instance_id)
        )
        name = (
            version.instance_version_id
            if instance is None or instance_version is None
            else f"{instance.name} v{instance_version.number}"
        )
        return ShowcaseView(
            mark,
            version.letter,
            version.instance_version_id,
            name,
            headline_numbers(found.summary.numbers),
        )
