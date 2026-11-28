"""Pricing versions for the tests: stored rows in PostgreSQL, a built version in memory."""

from datetime import datetime

from sqlalchemy import Engine, insert, select

from pricing_demo.domain.city_instances import InstanceVersion
from pricing_demo.domain.pricing_versions import (
    PricingVersion,
    new_draft_goals,
    pricing_version_id,
)
from pricing_demo.domain.runs import RunKind, RunState
from pricing_demo.infrastructure.persistence.pricing_versions import pricing_version_values
from pricing_demo.infrastructure.persistence.tables import (
    pricing_version_periods,
    pricing_versions,
)
from tests.support.builds import MemoryBuilds
from tests.support.instances import ensure_instance_versions
from tests.support.runs import T0, later, make_run


def insert_pricing_version(
    engine: Engine,
    instance_version_id: str = "geneva-3km.v1",
    letter: str = "A",
    status: str = "draft",
    **goals: float,
) -> str:
    """Store a pricing version (and the instance version and period it needs); returns its id."""
    period_id = f"{instance_version_id}.mon-08"
    ensure_instance_versions(engine, [instance_version_id], periods=[period_id])
    version = PricingVersion(
        id=pricing_version_id(instance_version_id, letter),
        instance_version_id=instance_version_id,
        letter=letter,
        name=f"Version {letter}",
        status="sealed" if status == "sealed" else "draft",
        based_on_id=None,
        goals=new_draft_goals(None).replacing(goals),
        created_at=T0,
        sealed_at=T0 if status == "sealed" else None,
    )
    with engine.begin() as connection:
        connection.execute(insert(pricing_versions).values(pricing_version_values(version)))
        connection.execute(
            insert(pricing_version_periods).values(
                pricing_version_id=version.id, period_id=period_id
            )
        )
    return version.id


def ensure_pricing_version(engine: Engine, pricing_version: str) -> None:
    """Store the pricing version an id `{instance version}.{letter}` names, if it is not."""
    instance_version, letter = pricing_version.rsplit(".", 1)
    with engine.connect() as connection:
        known = connection.execute(
            select(pricing_versions.c.id).where(pricing_versions.c.id == pricing_version)
        ).scalar()
    if known is None:
        insert_pricing_version(engine, instance_version, letter, status="sealed")


def built_in_memory(rig: MemoryBuilds, state: RunState = RunState.SUCCEEDED) -> InstanceVersion:
    """The rig's draft, sealed, with a build run that ended in `state`."""
    draft = rig.add_draft()
    rig.instances.seal(draft.id, T0)
    rig.runs.add(make_run("build-1", subject_id=draft.id, state=state, queued_at=later(1)))
    sealed = rig.instances.get_version(draft.id)
    assert sealed is not None
    return sealed


def sealed_pricing_version(rig: MemoryBuilds, version_id: str, run_state: RunState) -> None:
    """Seal a pricing version of the rig and give it a run in `run_state`."""
    rig.pricing.seal(version_id, datetime(2026, 11, 27, tzinfo=T0.tzinfo))
    rig.runs.add(
        make_run(
            f"pricing-{version_id}",
            kind=RunKind.PRICING,
            subject_id=version_id,
            state=run_state,
            queued_at=later(2),
        )
    )
