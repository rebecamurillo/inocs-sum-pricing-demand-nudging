from collections.abc import Collection, Mapping
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.city_instances import InstanceParameters
from pricing_demo.domain.runs import Run, RunState, StepName


class Builds(Protocol):
    """The build runs of instance versions."""

    def latest_build_run(self, version_id: str) -> Run | None:
        """The version's most recently queued build run."""
        ...

    def latest_build_states(self, version_ids: Collection[str]) -> Mapping[str, RunState]:
        """The state of each version's latest build run; a version without one is absent."""
        ...

    def last_duration_s(self, step: StepName, dataset_id: str, radius_m: float) -> float | None:
        """Seconds the most recent `done` step of that name took, on a version of the same data
        set and radius; None when none ended."""
        ...

    def queue_build(
        self,
        run: Run,
        seal_version_at: datetime | None,
        checked: InstanceParameters | None = None,
    ) -> None:
        """In one transaction, seal the draft when `seal_version_at` is given, and store the
        run with its steps. Raises `RunActive` when the version already has a queued or running
        run, `InstanceVersionNotFound` when the version is gone, and `DraftChanged` when the
        draft's values are no longer `checked` (the values the rules passed on); nothing is
        stored then."""
        ...

    def delete_version(self, version_id: str, including_pricing_versions: bool = False) -> None:
        """In one transaction, remove the version with its runs (their steps and route
        failures), step links and periods, and its instance when no version is left. Raises
        `InstanceVersionNotFound`; `RunActive` while a run of it or of one of its pricing
        versions is queued or running; then `HasPricingVersions` (every id, letter order) when
        it has any and `including_pricing_versions` is false; nothing is removed then. With the
        flag the pricing versions go too, with their periods, runs and steps. The instance's
        `next_number` is never decreased."""
        ...

    def delete_instance(self, instance_id: str, including_pricing_versions: bool = False) -> None:
        """In one transaction, remove every version of the instance as `delete_version` does,
        then the instance. Raises `CityInstanceNotFound`, `RunActive` and `HasPricingVersions`
        as `delete_version` does for any of its versions; nothing is removed then."""
        ...
