from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceParameters,
    InstancePeriod,
    InstanceVersion,
    InstanceWithVersions,
    Number,
)


class CityInstances(Protocol):
    """City instances, their versions and their periods."""

    def create(
        self, instance: CityInstance, draft: InstanceVersion, period: InstancePeriod
    ) -> None:
        """Store the three together. Raises `CityInstanceNameTaken` when the id or the name is
        used."""
        ...

    def get_instance(self, instance_id: str) -> CityInstance | None: ...

    def create_draft(
        self,
        instance_id: str,
        based_on_id: str | None,
        parameters: InstanceParameters,
        created_at: datetime,
        period_for: Callable[[str], InstancePeriod],
    ) -> InstanceVersion:
        """Take `next_number` of the instance and increment it in one transaction, and store
        the draft and its period `period_for(version id)`. Raises `CityInstanceNotFound` and
        `DraftExists`."""
        ...

    def get_version(self, version_id: str) -> InstanceVersion | None: ...

    def periods_of(self, version_id: str) -> Sequence[InstancePeriod]: ...

    def update_draft_parameters(
        self, version_id: str, changes: Mapping[str, Number]
    ) -> InstanceVersion:
        """Set the named parameters, leaving the others as stored, so two changes of different
        parameters sent at once both stay. Raises `InstanceVersionNotFound` and
        `VersionSealed`."""
        ...

    def delete_draft(self, version_id: str) -> None:
        """Delete the draft, and its instance when it was the instance's only version. Raises
        `InstanceVersionNotFound` and `VersionSealed`."""
        ...

    def menu(self) -> Sequence[InstanceWithVersions]:
        """Every instance, oldest first, with its versions by number."""
        ...
