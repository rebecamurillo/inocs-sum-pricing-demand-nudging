from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from pricing_demo.domain.city_instances import (
    CityInstance,
    CityInstanceNameTaken,
    CityInstanceNotFound,
    DraftExists,
    InstanceParameters,
    InstancePeriod,
    InstanceVersion,
    InstanceVersionNotFound,
    InstanceWithVersions,
    Number,
    VersionSealed,
    version_id,
)


class InMemoryCityInstances:
    """The instances in dicts; passes the same contract suite as the PostgreSQL adapter."""

    def __init__(self) -> None:
        self._instances: dict[str, CityInstance] = {}
        self._versions: dict[str, InstanceVersion] = {}
        self._periods: dict[str, list[InstancePeriod]] = {}

    def create(
        self, instance: CityInstance, draft: InstanceVersion, period: InstancePeriod
    ) -> None:
        if instance.id in self._instances or any(
            item.name == instance.name for item in self._instances.values()
        ):
            raise CityInstanceNameTaken(instance.name)
        self._instances[instance.id] = instance
        self._versions[draft.id] = draft
        self._periods[draft.id] = [period]

    def get_instance(self, instance_id: str) -> CityInstance | None:
        return self._instances.get(instance_id)

    def create_draft(
        self,
        instance_id: str,
        based_on_id: str | None,
        parameters: InstanceParameters,
        created_at: datetime,
        period_for: Callable[[str], InstancePeriod],
    ) -> InstanceVersion:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise CityInstanceNotFound(instance_id)
        for existing in self._versions.values():
            if existing.instance_id == instance_id and existing.status == "draft":
                raise DraftExists(instance_id, existing.id)
        number = instance.next_number
        self._instances[instance_id] = replace(instance, next_number=number + 1)
        draft = InstanceVersion(
            id=version_id(instance_id, number),
            instance_id=instance_id,
            number=number,
            based_on_id=based_on_id,
            status="draft",
            parameters=parameters,
            created_at=created_at,
        )
        self._versions[draft.id] = draft
        self._periods[draft.id] = [period_for(draft.id)]
        return draft

    def get_version(self, version_id: str) -> InstanceVersion | None:
        return self._versions.get(version_id)

    def periods_of(self, version_id: str) -> Sequence[InstancePeriod]:
        return list(self._periods.get(version_id, []))

    def update_draft_parameters(
        self, version_id: str, changes: Mapping[str, Number]
    ) -> InstanceVersion:
        version = self._versions.get(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        if version.status == "sealed":
            raise VersionSealed(version_id)
        updated = replace(version, parameters=version.parameters.replacing(changes))
        self._versions[version_id] = updated
        return updated

    def delete_draft(self, version_id: str) -> None:
        version = self._versions.get(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        if version.status == "sealed":
            raise VersionSealed(version_id)
        del self._versions[version_id]
        self._periods.pop(version_id, None)
        for other_id, other in list(self._versions.items()):
            if other.based_on_id == version_id:
                self._versions[other_id] = replace(other, based_on_id=None)
        if not any(item.instance_id == version.instance_id for item in self._versions.values()):
            del self._instances[version.instance_id]

    def menu(self) -> Sequence[InstanceWithVersions]:
        return [
            InstanceWithVersions(
                instance,
                sorted(
                    (v for v in self._versions.values() if v.instance_id == instance.id),
                    key=lambda v: v.number,
                ),
            )
            for instance in sorted(self._instances.values(), key=lambda i: (i.created_at, i.id))
        ]

    def clear(self) -> None:
        self._instances.clear()
        self._versions.clear()
        self._periods.clear()

    def seal(self, version_id: str, at: datetime) -> None:
        """What story 2-5's build will do; tests use it to get a sealed version."""
        self._versions[version_id] = replace(
            self._versions[version_id], status="sealed", sealed_at=at
        )
