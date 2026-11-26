"""The build plan of an instance version, gathered from what is stored: one place for the API's
view, the `POST` that queues the build and the worker's recomputation of a step's key."""

from collections.abc import Callable
from typing import Any

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.build_sources import BuildSources
from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.domain.build_plan import (
    BUILD_STEPS,
    BuildPlan,
    input_key,
    plan_build,
    step_inputs,
)
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import (
    InstancePeriod,
    InstanceVersion,
    InstanceVersionNotFound,
    version_state,
)
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.system_status import SystemStatus, Verdict, build_verdict


def plan_for(
    version: InstanceVersion,
    instances: CityInstances,
    datasets: CityDatasets,
    artifacts: Artifacts,
    sources: BuildSources,
    builds: Builds | None = None,
) -> BuildPlan:
    """The four steps of `version`: their keys, whether each is kept, and why a step differs
    from the version it is based on (the inputs stored with that version's artefacts)."""
    context = _context(version, instances, datasets)
    instance_dataset, period = context
    fingerprint, manifest = sources.package_fingerprint(), sources.graph_manifest()
    inputs = step_inputs(version.parameters, instance_dataset, period, fingerprint, manifest)
    stored = artifacts.stored_keys([input_key(item) for item in inputs.values() if item])
    based_on_inputs: dict[StepName, Any] | None = None
    if version.based_on_id is not None:
        based_on_inputs = {}
        for step, key in artifacts.links_of(version.based_on_id).items():
            artifact = artifacts.get(key)
            if artifact is not None:
                based_on_inputs[step] = artifact.inputs
    durations = {
        step: builds.last_duration_s(step, instance_dataset.id, version.parameters.radius_m)
        for step in BUILD_STEPS
        if builds is not None
    }
    return plan_build(
        version.parameters,
        instance_dataset,
        period,
        fingerprint,
        manifest,
        stored,
        based_on_inputs,
        durations,
    )


def _context(
    version: InstanceVersion, instances: CityInstances, datasets: CityDatasets
) -> tuple[CityDataset, InstancePeriod]:
    instance = instances.get_instance(version.instance_id)
    dataset = datasets.get(instance.dataset_id) if instance else None
    periods = instances.periods_of(version.id)
    # A version always has an instance, a data set and a period (foreign keys, creation).
    if dataset is None or not periods:
        raise InstanceVersionNotFound(version.id)
    return dataset, periods[0]


class BuildPlanning:
    """The plan, the verdict on it and the state of a version, for the use cases that show or
    queue a build."""

    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        artifacts: Artifacts,
        sources: BuildSources,
        builds: Builds,
        system_status: Callable[[], SystemStatus],
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._artifacts = artifacts
        self._sources = sources
        self._builds = builds
        self._system_status = system_status

    def plan(self, version: InstanceVersion) -> BuildPlan:
        return plan_for(
            version, self._instances, self._datasets, self._artifacts, self._sources, self._builds
        )

    def verdict(self, plan: BuildPlan) -> Verdict:
        return build_verdict(
            self._system_status(),
            plan.needs_trip_planner,
            package_missing=plan.package_missing,
            manifest_missing=plan.manifest_missing,
        )

    def state(self, version: InstanceVersion) -> str:
        run = self._builds.latest_build_run(version.id)
        return version_state(version.status, run.state if run else None)
