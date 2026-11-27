from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from pricing_demo.domain.city_instances import Number
from pricing_demo.domain.pricing_versions import PricingGoals, PricingVersion, PricingVersionSummary
from pricing_demo.domain.runs import Run


class PricingVersions(Protocol):
    """Pricing versions and the periods they price."""

    def create_draft(
        self,
        instance_version_id: str,
        name: str | None,
        goals: PricingGoals,
        period_id: str,
        based_on_id: str | None,
        created_at: datetime,
    ) -> PricingVersion:
        """Take `next_pricing_letter` of the instance version and increment it under a row
        lock, in one transaction with the insert of the draft (named `Version {letter}` when
        `name` is None) and its period. Raises `InstanceVersionNotFound`, and `UnknownBasedOn`
        when `based_on_id` is not (or no longer) a pricing version of the instance version."""
        ...

    def get(self, version_id: str) -> PricingVersion | None: ...

    def period_ids(self, version_id: str) -> Sequence[str]:
        """The ids of the instance periods the version prices."""
        ...

    def list_for(self, instance_version_id: str) -> Sequence[PricingVersionSummary]:
        """The instance version's pricing versions in letter order, with their state."""
        ...

    def previous_sealed(self, instance_version_id: str) -> PricingVersion | None:
        """The sealed pricing version of the instance version with the highest letter."""
        ...

    def update_draft(self, version_id: str, changes: Mapping[str, Number]) -> PricingVersion:
        """Set the named goals, leaving the others as stored. Raises `PricingVersionNotFound`
        and `VersionSealed`."""
        ...

    def latest_run(self, version_id: str) -> Run | None:
        """The version's most recently queued pricing run (never a simulation run), with its
        steps."""
        ...

    def active_run_id(self, version_id: str) -> str | None:
        """The id of the version's queued or running run of any kind, or None."""
        ...

    def queue_run(self, run: Run, seal_at: datetime | None, checked: PricingGoals | None) -> None:
        """In one transaction under the version's row lock: seal the draft when `seal_at` is
        given (only when its goals still equal `checked`; `DraftChanged` otherwise), then store
        the run with its steps. Raises `PricingVersionNotFound`, and `RunActive` when the
        version already has a queued or running run; nothing is stored then."""
        ...

    def delete(self, version_id: str) -> None:
        """In one transaction, remove the version with its periods, its solves, its links to
        simulations and its finished runs (their steps). Raises `PricingVersionNotFound`, and
        `RunActive` while a run of it is queued or running, and `IsShowcase` while it is the
        showcase; nothing is removed then. The
        instance version's next letter never decreases."""
        ...

    def letters_by_instance_version(
        self, instance_version_ids: Collection[str]
    ) -> Mapping[str, Sequence[str]]:
        """The letters of each instance version's pricing versions, in letter order; a version
        without any is absent."""
        ...
