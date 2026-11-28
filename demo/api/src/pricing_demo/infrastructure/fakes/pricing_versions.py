from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from pricing_demo.domain.builds import DraftChanged, RunActive
from pricing_demo.domain.city_instances import InstanceVersionNotFound, Number, VersionSealed
from pricing_demo.domain.pricing_versions import (
    IsShowcase,
    PricingGoals,
    PricingVersion,
    PricingVersionNotFound,
    PricingVersionSummary,
    UnknownBasedOn,
    pricing_letter,
    pricing_version_id,
    pricing_version_state,
)
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, StepState
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.showcase import InMemoryShowcase
from pricing_demo.infrastructure.fakes.simulations import InMemorySimulations
from pricing_demo.infrastructure.fakes.solves import InMemorySolves

ACTIVE = (RunState.QUEUED, RunState.RUNNING)


def _order(version: PricingVersion) -> tuple[str, int, str]:
    return (version.instance_version_id, len(version.letter), version.letter)


class FakePricingVersions:
    """The pricing versions in dicts; passes the same contract suite as the PostgreSQL adapter.
    The runs come from the run repository, as the adapter reads them from `runs`."""

    def __init__(
        self,
        runs: InMemoryRunRepository,
        instances: InMemoryCityInstances | None = None,
        solves: InMemorySolves | None = None,
        simulations: InMemorySimulations | None = None,
        showcase: InMemoryShowcase | None = None,
    ) -> None:
        self._runs = runs
        self._instances = instances
        self._solves = solves
        self._simulations = simulations
        self._showcase = showcase
        self._versions: dict[str, PricingVersion] = {}
        self._periods: dict[str, list[str]] = {}
        self._next_index: dict[str, int] = {}
        self._duration_instances = instances

    def read_durations_from(self, instances: InMemoryCityInstances) -> None:
        """Let `last_pricing_model_duration_s` find a version's data set and radius, without
        making `create_draft` check the instance version (the other tests need none)."""
        self._duration_instances = instances

    def create_draft(
        self,
        instance_version_id: str,
        name: str | None,
        goals: PricingGoals,
        period_id: str,
        based_on_id: str | None,
        created_at: datetime,
        kept_from_id: str | None = None,
    ) -> PricingVersion:
        if self._instances is not None and self._instances.get_version(instance_version_id) is None:
            raise InstanceVersionNotFound(instance_version_id)
        if based_on_id is not None:
            source = self._versions.get(based_on_id)
            if source is None or source.instance_version_id != instance_version_id:
                raise UnknownBasedOn(based_on_id)
        index = self._next_index.get(instance_version_id, 0)
        self._next_index[instance_version_id] = index + 1
        letter = pricing_letter(index)
        version = PricingVersion(
            id=pricing_version_id(instance_version_id, letter),
            instance_version_id=instance_version_id,
            letter=letter,
            name=name or f"Version {letter}",
            status="draft",
            based_on_id=based_on_id,
            kept_from_id=kept_from_id,
            goals=goals,
            created_at=created_at,
        )
        self._versions[version.id] = version
        self._periods[version.id] = [period_id]
        return version

    def get(self, version_id: str) -> PricingVersion | None:
        return self._versions.get(version_id)

    def period_ids(self, version_id: str) -> Sequence[str]:
        return list(self._periods.get(version_id, []))

    def _last_run_state(self, version_id: str) -> RunState | None:
        latest = self.latest_run(version_id)
        return None if latest is None else latest.state

    def latest_run(self, version_id: str) -> Run | None:
        runs = [
            run
            for run in self._runs.list_by_states(list(RunState))
            if run.kind is RunKind.PRICING and run.subject.id == version_id
        ]
        return max(runs, key=lambda run: (run.queued_at, run.id), default=None)

    def queue_run(self, run: Run, seal_at: datetime | None, checked: PricingGoals | None) -> None:
        version = self._versions.get(run.subject.id)
        if version is None:
            raise PricingVersionNotFound(run.subject.id)
        sealing = seal_at is not None and version.status == "draft"
        if sealing and checked is not None and version.goals != checked:
            raise DraftChanged(run.subject.id)
        active = self.active_run_id([version.id])
        if active is not None:
            raise RunActive(active)
        if sealing:
            assert seal_at is not None
            self.seal(version.id, seal_at)
        self._runs.add(run)

    def _of(self, instance_version_id: str) -> list[PricingVersion]:
        return sorted(
            (v for v in self._versions.values() if v.instance_version_id == instance_version_id),
            key=_order,
        )

    def list_for(self, instance_version_id: str) -> Sequence[PricingVersionSummary]:
        return [
            PricingVersionSummary(
                version,
                pricing_version_state(version.status, self._last_run_state(version.id), version.id),
            )
            for version in self._of(instance_version_id)
        ]

    def previous_sealed(self, instance_version_id: str) -> PricingVersion | None:
        sealed = [v for v in self._of(instance_version_id) if v.status == "sealed"]
        return sealed[-1] if sealed else None

    def update_draft(
        self, version_id: str, changes: Mapping[str, Number], name: str | None = None
    ) -> PricingVersion:
        version = self._versions.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        if version.status == "sealed":
            raise VersionSealed(version_id)
        updated = replace(
            version,
            goals=version.goals.replacing(dict(changes)),
            name=version.name if name is None else name,
        )
        self._versions[version_id] = updated
        return updated

    def last_pricing_model_duration_s(self, dataset_id: str, radius_m: float) -> float | None:
        instances = self._duration_instances
        if instances is None:
            return None
        best: tuple[datetime, float] | None = None
        for run in self._runs.list_by_states(list(RunState)):
            version = self._versions.get(run.subject.id)
            if run.kind is not RunKind.PRICING or version is None:
                continue
            instance_version = instances.get_version(version.instance_version_id)
            instance = (
                instances.get_instance(instance_version.instance_id) if instance_version else None
            )
            if instance_version is None or instance is None:
                continue
            if (
                instance.dataset_id != dataset_id
                or instance_version.parameters.radius_m != radius_m
            ):
                continue
            for item in run.steps:
                if item.step is not StepName.PRICING_MODEL or item.state is not StepState.DONE:
                    continue
                if item.started_at is None or item.finished_at is None:
                    continue
                seconds = (item.finished_at - item.started_at).total_seconds()
                best = (
                    max(best, (item.finished_at, seconds)) if best else (item.finished_at, seconds)
                )
        return best[1] if best else None

    def delete(self, version_id: str) -> None:
        if version_id not in self._versions:
            raise PricingVersionNotFound(version_id)
        if self._showcase is not None:
            mark = self._showcase.current()
            if mark is not None and mark.pricing_version_id == version_id:
                raise IsShowcase(version_id)
        self.remove_all([version_id])

    def letters_by_instance_version(
        self, instance_version_ids: Collection[str]
    ) -> Mapping[str, Sequence[str]]:
        found = {item: [v.letter for v in self._of(item)] for item in instance_version_ids}
        return {item: letters for item, letters in found.items() if letters}

    # What the deletion of an instance version does; the port has no such method.
    def ids_for(self, instance_version_ids: Collection[str]) -> list[str]:
        return [
            v.id
            for v in sorted(self._versions.values(), key=_order)
            if v.instance_version_id in instance_version_ids
        ]

    def active_run_id(self, ids: str | Collection[str]) -> str | None:
        """The earliest queued or running run of the version (the port) or of any of the
        versions (what the deletion of an instance version asks)."""
        if isinstance(ids, str):
            ids = [ids]
        active = [run for run in self._runs.list_by_states(list(ACTIVE)) if run.subject.id in ids]
        return min(active, key=lambda run: (run.queued_at, run.id)).id if active else None

    def remove_all(self, ids: Collection[str]) -> None:
        active = self.active_run_id(ids)
        if active is not None:
            raise RunActive(active)
        for run in self._runs.list_by_states(list(RunState)):
            if run.subject.id in ids:
                self._runs.remove(run.id)
        if self._solves is not None:
            self._solves.drop_version(ids)
        if self._simulations is not None:
            self._simulations.drop_version(ids)
        if self._showcase is not None:
            self._showcase.drop_version(ids)
        for version_id in ids:
            self._versions.pop(version_id, None)
            self._periods.pop(version_id, None)
        for other_id, other in list(self._versions.items()):
            if other.based_on_id in ids:
                self._versions[other_id] = replace(other, based_on_id=None)
            if other.kept_from_id in ids:
                self._versions[other_id] = replace(self._versions[other_id], kept_from_id=None)

    def seal(self, version_id: str, at: datetime) -> None:
        """What queueing a run does to a draft; tests use it to get a sealed version."""
        self._versions[version_id] = replace(
            self._versions[version_id], status="sealed", sealed_at=at
        )
