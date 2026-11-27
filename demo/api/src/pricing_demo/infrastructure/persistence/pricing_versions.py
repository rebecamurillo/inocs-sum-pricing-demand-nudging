from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from sqlalchemy import Connection, Engine, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from pricing_demo.domain.builds import DraftChanged, RunActive
from pricing_demo.domain.city_instances import InstanceVersionNotFound, Number, VersionSealed
from pricing_demo.domain.pricing_versions import (
    GOAL_NAMES,
    PricingGoals,
    PricingVersion,
    PricingVersionNotFound,
    PricingVersionSummary,
    UnknownBasedOn,
    pricing_letter,
    pricing_version_id,
    pricing_version_state,
)
from pricing_demo.domain.runs import Run, RunKind, RunState
from pricing_demo.infrastructure.persistence.run_repository import (
    run_of,
    run_values,
    step_values,
    steps_of,
    steps_query,
)
from pricing_demo.infrastructure.persistence.tables import (
    instance_versions,
    pricing_version_periods,
    pricing_version_simulations,
    pricing_versions,
    run_steps,
    runs,
    solves,
)

ACTIVE_SUBJECT_INDEX = "uq_runs_active_subject"

# "B" before "AA": a longer letter is a later one.
LETTER_ORDER = (func.length(pricing_versions.c.letter), pricing_versions.c.letter)


def _version(row) -> PricingVersion:  # type: ignore[no-untyped-def]
    return PricingVersion(
        id=row.id,
        instance_version_id=row.instance_version_id,
        letter=row.letter,
        name=row.name,
        status=row.status,
        based_on_id=row.based_on_id,
        goals=PricingGoals(
            **{name: getattr(row, name) for name in GOAL_NAMES},
            flat_price_kind=row.flat_price_kind,
        ),
        created_at=row.created_at,
        sealed_at=row.sealed_at,
    )


def pricing_version_values(version: PricingVersion) -> dict[str, object]:
    return {
        "id": version.id,
        "instance_version_id": version.instance_version_id,
        "letter": version.letter,
        "name": version.name,
        "status": version.status,
        "based_on_id": version.based_on_id,
        **version.goals.as_dict(),
        "flat_price_kind": version.goals.flat_price_kind,
        "created_at": version.created_at,
        "sealed_at": version.sealed_at,
    }


class PostgresPricingVersions:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_draft(
        self,
        instance_version_id: str,
        name: str | None,
        goals: PricingGoals,
        period_id: str,
        based_on_id: str | None,
        created_at: datetime,
    ) -> PricingVersion:
        with self._engine.begin() as connection:
            # The row lock serialises two drafts of one instance version, and a deletion of it:
            # each takes its own letter.
            index = connection.execute(
                select(instance_versions.c.next_pricing_letter)
                .where(instance_versions.c.id == instance_version_id)
                .with_for_update()
            ).scalar()
            if index is None:
                raise InstanceVersionNotFound(instance_version_id)
            # The source is checked again under a lock: deleted since the use case read it, the
            # foreign key of `based_on_id` would otherwise refuse the insert.
            if based_on_id is not None and (
                connection.execute(
                    select(pricing_versions.c.id)
                    .where(
                        pricing_versions.c.id == based_on_id,
                        pricing_versions.c.instance_version_id == instance_version_id,
                    )
                    .with_for_update(key_share=True)
                ).scalar()
                is None
            ):
                raise UnknownBasedOn(based_on_id)
            connection.execute(
                update(instance_versions)
                .where(instance_versions.c.id == instance_version_id)
                .values(next_pricing_letter=index + 1)
            )
            letter = pricing_letter(index)
            version = PricingVersion(
                id=pricing_version_id(instance_version_id, letter),
                instance_version_id=instance_version_id,
                letter=letter,
                name=name or f"Version {letter}",
                status="draft",
                based_on_id=based_on_id,
                goals=goals,
                created_at=created_at,
            )
            connection.execute(insert(pricing_versions).values(pricing_version_values(version)))
            connection.execute(
                insert(pricing_version_periods).values(
                    pricing_version_id=version.id, period_id=period_id
                )
            )
            return version

    def get(self, version_id: str) -> PricingVersion | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(pricing_versions).where(pricing_versions.c.id == version_id)
            ).first()
        return _version(row) if row else None

    def period_ids(self, version_id: str) -> Sequence[str]:
        with self._engine.connect() as connection:
            return list(
                connection.execute(
                    select(pricing_version_periods.c.period_id)
                    .where(pricing_version_periods.c.pricing_version_id == version_id)
                    .order_by(pricing_version_periods.c.period_id)
                ).scalars()
            )

    def list_for(self, instance_version_id: str) -> Sequence[PricingVersionSummary]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(pricing_versions)
                .where(pricing_versions.c.instance_version_id == instance_version_id)
                .order_by(*LETTER_ORDER)
            ).all()
            latest = _last_run_states(connection, [row.id for row in rows])
        return [
            PricingVersionSummary(
                _version(row), pricing_version_state(row.status, latest.get(row.id), row.id)
            )
            for row in rows
        ]

    def previous_sealed(self, instance_version_id: str) -> PricingVersion | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(pricing_versions)
                .where(
                    pricing_versions.c.instance_version_id == instance_version_id,
                    pricing_versions.c.status == "sealed",
                )
                .order_by(*(item.desc() for item in LETTER_ORDER))
                .limit(1)
            ).first()
        return _version(row) if row else None

    def update_draft(self, version_id: str, changes: Mapping[str, Number]) -> PricingVersion:
        with self._engine.begin() as connection:
            status = connection.execute(
                select(pricing_versions.c.status)
                .where(pricing_versions.c.id == version_id)
                .with_for_update()
            ).scalar()
            if status is None:
                raise PricingVersionNotFound(version_id)
            if status == "sealed":
                raise VersionSealed(version_id)
            if changes:
                connection.execute(
                    update(pricing_versions)
                    .where(pricing_versions.c.id == version_id)
                    .values(**changes)
                )
            row = connection.execute(
                select(pricing_versions).where(pricing_versions.c.id == version_id)
            ).one()
        return _version(row)

    def latest_run(self, version_id: str) -> Run | None:
        query = (
            select(runs)
            .where(runs.c.kind == RunKind.PRICING.value, runs.c.pricing_version_id == version_id)
            .order_by(runs.c.queued_at.desc(), runs.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
            if row is None:
                return None
            steps = steps_of(connection.execute(steps_query([row["id"]])).mappings())
        return run_of(row, steps.get(row["id"], ()))

    def queue_run(self, run: Run, seal_at: datetime | None, checked: PricingGoals | None) -> None:
        version_id = run.subject.id
        try:
            with self._engine.begin() as connection:
                # The row lock orders this request after a concurrent edit or deletion of the
                # draft, and before any that comes later (they lock the same row).
                status = connection.execute(
                    select(pricing_versions.c.status)
                    .where(pricing_versions.c.id == version_id)
                    .with_for_update()
                ).scalar()
                if status is None:
                    raise PricingVersionNotFound(version_id)
                if seal_at is not None and status == "draft":
                    seal = update(pricing_versions).where(pricing_versions.c.id == version_id)
                    if checked is not None:
                        # Seal only the values the rules were checked on.
                        seal = seal.where(
                            *(
                                pricing_versions.c[name] == value
                                for name, value in checked.as_dict().items()
                            )
                        )
                    sealed = connection.execute(seal.values(status="sealed", sealed_at=seal_at))
                    if sealed.rowcount == 0:
                        raise DraftChanged(version_id)
                # A draft another request sealed meanwhile is not sealed again; the run that
                # request queued then refuses this insert (`uq_runs_active_subject`).
                connection.execute(insert(runs).values(run_values(run)))
                connection.execute(
                    insert(run_steps), [step_values(run.id, item) for item in run.steps]
                )
        except IntegrityError as error:
            if getattr(getattr(error.orig, "diag", None), "constraint_name", None) != (
                ACTIVE_SUBJECT_INDEX
            ):
                raise
            with self._engine.connect() as connection:
                active = active_run_of(connection, [version_id])
            raise RunActive(active or "") from error

    def delete(self, version_id: str) -> None:
        with self._engine.begin() as connection:
            locked = connection.execute(
                select(pricing_versions.c.id)
                .where(pricing_versions.c.id == version_id)
                .with_for_update()
            ).scalar()
            if locked is None:
                raise PricingVersionNotFound(version_id)
            remove_pricing_versions(connection, [version_id])

    def letters_by_instance_version(
        self, instance_version_ids: Collection[str]
    ) -> Mapping[str, Sequence[str]]:
        if not instance_version_ids:
            return {}
        found: dict[str, list[str]] = {}
        with self._engine.connect() as connection:
            for instance_version, letter in connection.execute(
                select(pricing_versions.c.instance_version_id, pricing_versions.c.letter)
                .where(pricing_versions.c.instance_version_id.in_(list(instance_version_ids)))
                .order_by(pricing_versions.c.instance_version_id, *LETTER_ORDER)
            ):
                found.setdefault(instance_version, []).append(letter)
        return found


def _last_run_states(connection: Connection, ids: list[str]) -> dict[str, RunState]:
    if not ids:
        return {}
    latest: dict[str, RunState] = {}
    for version, state in connection.execute(
        select(runs.c.pricing_version_id, runs.c.state)
        .where(runs.c.pricing_version_id.in_(ids))
        .order_by(runs.c.queued_at.desc(), runs.c.id.desc())
    ):
        latest.setdefault(version, RunState(state))
    return latest


def active_run_of(connection: Connection, pricing_version_ids: list[str]) -> str | None:
    found = connection.execute(
        select(runs.c.id)
        .where(runs.c.pricing_version_id.in_(pricing_version_ids))
        .where(runs.c.state.in_(["queued", "running"]))
        .order_by(runs.c.queued_at, runs.c.id)
        .limit(1)
    ).scalar()
    return None if found is None else str(found)


def remove_pricing_versions(connection: Connection, ids: list[str]) -> None:
    """Inside the transaction that holds the rows: refuse while a run is active, then remove
    the versions' solves and links to simulations, the runs (steps first) and the versions
    (periods cascade); runs go before the versions so the foreign key of
    `runs.pricing_version_id` never blocks an allowed deletion."""
    if not ids:
        return
    active = active_run_of(connection, ids)
    if active is not None:
        raise RunActive(active)
    connection.execute(
        delete(pricing_version_simulations).where(
            pricing_version_simulations.c.pricing_version_id.in_(ids)
        )
    )
    connection.execute(delete(solves).where(solves.c.pricing_version_id.in_(ids)))
    run_ids = select(runs.c.id).where(runs.c.pricing_version_id.in_(ids))
    connection.execute(delete(run_steps).where(run_steps.c.run_id.in_(run_ids)))
    connection.execute(delete(runs).where(runs.c.pricing_version_id.in_(ids)))
    connection.execute(delete(pricing_versions).where(pricing_versions.c.id.in_(ids)))
