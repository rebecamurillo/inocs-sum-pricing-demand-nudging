from collections.abc import Mapping
from dataclasses import dataclass

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.package_fingerprints import PackageFingerprints
from pricing_demo.domain.build_plan import BuildPlan
from pricing_demo.domain.city_instances import (
    InstanceParameters,
    InstancePeriod,
    InstanceVersion,
    InstanceVersionNotFound,
    ParameterChange,
    parameters_from_defaults,
    what_changes,
)
from pricing_demo.domain.instance_rules import RuleResult, check_rules
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.read_model import RoutesSummary
from pricing_demo.domain.system_status import Verdict


@dataclass(frozen=True)
class InstanceVersionView:
    version: InstanceVersion
    periods: tuple[InstancePeriod, ...]
    rules: tuple[RuleResult, ...]
    changes: tuple[ParameterChange, ...]
    # `draft`, or the state of the latest build (`sealed` while none exists).
    state: str
    plan: BuildPlan
    build_verdict: Verdict
    # The five headline numbers and the routes summary: None until the version is built.
    counts: Mapping[str, Number] | None = None
    routes: RoutesSummary | None = None
    # The package's default values with the data set's preset, for a draft; None for a saved
    # version or while no package is recorded.
    package_defaults: InstanceParameters | None = None


def build_view(
    version: InstanceVersion,
    instances: CityInstances,
    datasets: CityDatasets,
    planning: BuildPlanning,
    built: BuiltCounts,
    fingerprints: PackageFingerprints,
) -> InstanceVersionView:
    """The version with its periods, the rule results of its values, what differs from the
    version it is based on, its build plan and the verdict on that plan."""
    periods = tuple(instances.periods_of(version.id))
    instance = instances.get_instance(version.instance_id)
    dataset = datasets.get(instance.dataset_id) if instance else None
    # A version always has an instance, a data set and a period (foreign keys, creation).
    if instance is None or dataset is None or not periods:
        raise InstanceVersionNotFound(version.id)
    rules = check_rules(version.parameters, dataset, periods[0])
    based_on = instances.get_version(version.based_on_id) if version.based_on_id else None
    changes = what_changes(based_on.parameters, version.parameters) if based_on else []
    plan = planning.plan(version)
    counts, routes = built.of(version.id)
    fingerprint = fingerprints.latest() if version.status == "draft" else None
    package_defaults = (
        parameters_from_defaults(fingerprint.defaults, dataset.preset) if fingerprint else None
    )
    return InstanceVersionView(
        version,
        periods,
        tuple(rules),
        tuple(changes),
        planning.state(version),
        plan,
        planning.verdict(plan),
        counts,
        routes,
        package_defaults,
    )
