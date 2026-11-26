from dataclasses import dataclass

from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.domain.city_instances import (
    InstancePeriod,
    InstanceVersion,
    InstanceVersionNotFound,
    ParameterChange,
    what_changes,
)
from pricing_demo.domain.instance_rules import RuleResult, check_rules


@dataclass(frozen=True)
class InstanceVersionView:
    version: InstanceVersion
    periods: tuple[InstancePeriod, ...]
    rules: tuple[RuleResult, ...]
    changes: tuple[ParameterChange, ...]
    # The version's status until story 2-5 adds the build states.
    state: str


def build_view(
    version: InstanceVersion, instances: CityInstances, datasets: CityDatasets
) -> InstanceVersionView:
    """The version with its periods, the rule results of its values and what differs from
    the version it is based on."""
    periods = tuple(instances.periods_of(version.id))
    instance = instances.get_instance(version.instance_id)
    dataset = datasets.get(instance.dataset_id) if instance else None
    # A version always has an instance, a data set and a period (foreign keys, creation).
    if instance is None or dataset is None or not periods:
        raise InstanceVersionNotFound(version.id)
    rules = check_rules(version.parameters, dataset, periods[0])
    based_on = instances.get_version(version.based_on_id) if version.based_on_id else None
    changes = what_changes(based_on.parameters, version.parameters) if based_on else []
    return InstanceVersionView(version, periods, tuple(rules), tuple(changes), version.status)
