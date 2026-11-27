from collections.abc import Collection, Mapping
from datetime import datetime

from pricing_demo.domain.builds import DraftChanged, RunActive
from pricing_demo.domain.city_instances import (
    CityInstanceNotFound,
    InstanceParameters,
    InstanceVersionNotFound,
)
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository

ACTIVE = (RunState.QUEUED, RunState.RUNNING)


class InMemoryBuilds:
    """The build runs on the in-memory run repository and instances; passes the same contract
    suite as the PostgreSQL adapter."""

    def __init__(
        self,
        runs: InMemoryRunRepository,
        instances: InMemoryCityInstances,
        artifacts: InMemoryArtifacts | None = None,
        route_failures: InMemoryRouteFailures | None = None,
    ) -> None:
        self._runs = runs
        self._instances = instances
        self._artifacts = artifacts
        self._route_failures = route_failures

    def _builds_of(self, version_id: str) -> list[Run]:
        return [
            run
            for run in self._runs.list_by_states(list(RunState))
            if run.kind is RunKind.BUILD and run.subject.id == version_id
        ]

    def latest_build_run(self, version_id: str) -> Run | None:
        builds = self._builds_of(version_id)
        return max(builds, key=lambda run: (run.queued_at, run.id), default=None)

    def latest_build_states(self, version_ids: Collection[str]) -> Mapping[str, RunState]:
        found = {version: self.latest_build_run(version) for version in version_ids}
        return {version: run.state for version, run in found.items() if run is not None}

    def last_duration_s(self, step: StepName, dataset_id: str, radius_m: float) -> float | None:
        best: tuple[datetime, float] | None = None
        for run in self._runs.list_by_states(list(RunState)):
            if run.kind is not RunKind.BUILD:
                continue
            version = self._instances.get_version(run.subject.id)
            instance = self._instances.get_instance(version.instance_id) if version else None
            if version is None or instance is None:
                continue
            if instance.dataset_id != dataset_id or version.parameters.radius_m != radius_m:
                continue
            for item in run.steps:
                if item.step is not step or item.state is not StepState.DONE:
                    continue
                if item.started_at is None or item.finished_at is None:
                    continue
                seconds = (item.finished_at - item.started_at).total_seconds()
                best = (
                    max(best, (item.finished_at, seconds)) if best else (item.finished_at, seconds)
                )
        return best[1] if best else None

    def queue_build(
        self,
        run: Run,
        seal_version_at: datetime | None,
        checked: InstanceParameters | None = None,
    ) -> None:
        version = self._instances.get_version(run.subject.id)
        if version is None:
            raise InstanceVersionNotFound(run.subject.id)
        sealing = seal_version_at is not None and version.status == "draft"
        if sealing and checked is not None and version.parameters != checked:
            raise DraftChanged(run.subject.id)
        active = [item for item in self._builds_of(run.subject.id) if item.state in ACTIVE]
        if active:
            raise RunActive(active[0].id)
        if sealing:
            assert seal_version_at is not None
            self._instances.seal(run.subject.id, seal_version_at)
        self._runs.add(run)

    def _refuse_active(self, version_ids: list[str]) -> None:
        for version_id in version_ids:
            active = [item for item in self._builds_of(version_id) if item.state in ACTIVE]
            if active:
                raise RunActive(active[0].id)

    def _drop(self, version_id: str) -> None:
        for run in self._runs.list_by_states(list(RunState)):
            if run.subject.id == version_id:
                self._runs.remove(run.id)
                if self._route_failures is not None:
                    self._route_failures.drop_run(run.id)
        if self._artifacts is not None:
            self._artifacts.drop_links(version_id)

    def delete_version(self, version_id: str) -> None:
        if self._instances.get_version(version_id) is None:
            raise InstanceVersionNotFound(version_id)
        self._refuse_active([version_id])
        self._drop(version_id)
        self._instances.remove_version(version_id)

    def delete_instance(self, instance_id: str) -> None:
        if self._instances.get_instance(instance_id) is None:
            raise CityInstanceNotFound(instance_id)
        ids = [item.id for item in self._instances.versions_of(instance_id)]
        self._refuse_active(ids)
        for version_id in ids:
            self._drop(version_id)
        self._instances.remove_instance(instance_id)
