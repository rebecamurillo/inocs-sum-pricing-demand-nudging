from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.id_source import IdSource
from pricing_demo.domain.builds import (
    AlreadyBuilt,
    ComponentUnavailable,
    DraftChanged,
    RuleBroken,
    RunActive,
)
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.instance_rules import check_rules
from pricing_demo.domain.runs import (
    Run,
    RunKind,
    RunState,
    RunStep,
    Subject,
    SubjectType,
)

# A draft edited between the rule check and the seal is checked again on its new values; a
# draft that keeps changing faster than that is left to the client's next request.
ATTEMPTS = 3


class BuildInstanceVersion:
    """Validate a draft, seal it and queue its build; or queue the build of a sealed version
    whose last build failed or was cancelled (the resume: kept steps cost nothing).

    The refusals come in this order: the version is unknown; a rule of the draft is broken; a
    run of the version is queued or running; the version is already built; a component the
    plan needs is not available.
    """

    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        builds: Builds,
        planning: BuildPlanning,
        ids: IdSource,
        clock: Clock,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._builds = builds
        self._planning = planning
        self._ids = ids
        self._clock = clock

    def execute(self, version_id: str) -> Run:
        for _ in range(ATTEMPTS - 1):
            try:
                return self._attempt(version_id)
            except DraftChanged:
                continue
        return self._attempt(version_id)

    def _attempt(self, version_id: str) -> Run:
        version = self._instances.get_version(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        periods = self._instances.periods_of(version_id)
        instance = self._instances.get_instance(version.instance_id)
        dataset = self._datasets.get(instance.dataset_id) if instance else None
        if dataset is None or not periods:
            raise InstanceVersionNotFound(version_id)
        if version.status == "draft":
            failing = [
                result
                for result in check_rules(version.parameters, dataset, periods[0])
                if not result.passed
            ]
            if failing:
                raise RuleBroken(failing)
        latest = self._builds.latest_build_run(version_id)
        if latest is not None and latest.state in (RunState.QUEUED, RunState.RUNNING):
            raise RunActive(latest.id)
        if latest is not None and latest.state is RunState.SUCCEEDED:
            raise AlreadyBuilt(version_id)
        plan = self._planning.plan(version)
        verdict = self._planning.verdict(plan)
        if not verdict.allowed:
            raise ComponentUnavailable(verdict.reasons)
        now = self._clock.now()
        run = Run(
            id=self._ids.new_run_id(),
            kind=RunKind.BUILD,
            subject=Subject(SubjectType.INSTANCE_VERSION, version_id),
            state=RunState.QUEUED,
            queued_at=now,
            steps=tuple(
                RunStep(
                    position=item.position,
                    step=item.step,
                    period=item.period_id,
                    input_key=item.input_key,
                )
                for item in plan.steps
            ),
        )
        if version.status == "draft":
            self._builds.queue_build(run, now, checked=version.parameters)
        else:
            self._builds.queue_build(run, None)
        return run
