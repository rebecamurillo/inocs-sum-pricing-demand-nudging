from collections.abc import Collection, Mapping
from datetime import datetime

from sqlalchemy import Connection, Engine, delete, extract, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from pricing_demo.domain.builds import DraftChanged, RunActive
from pricing_demo.domain.city_instances import (
    CityInstanceNotFound,
    InstanceParameters,
    InstanceVersionNotFound,
)
from pricing_demo.domain.runs import Run, RunKind, RunState, StepName, StepState
from pricing_demo.infrastructure.persistence.run_repository import (
    run_of,
    run_values,
    step_values,
    steps_of,
    steps_query,
)
from pricing_demo.infrastructure.persistence.tables import (
    city_instances,
    instance_versions,
    run_steps,
    runs,
)

ACTIVE_SUBJECT_INDEX = "uq_runs_active_subject"


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


class PostgresBuilds:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def latest_build_run(self, version_id: str) -> Run | None:
        query = (
            select(runs)
            .where(runs.c.kind == RunKind.BUILD.value, runs.c.instance_version_id == version_id)
            .order_by(runs.c.queued_at.desc(), runs.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).mappings().first()
            if row is None:
                return None
            steps = steps_of(connection.execute(steps_query([row["id"]])).mappings())
        return run_of(row, steps.get(row["id"], ()))

    def latest_build_states(self, version_ids: Collection[str]) -> Mapping[str, RunState]:
        if not version_ids:
            return {}
        query = (
            select(runs.c.instance_version_id, runs.c.state)
            .where(
                runs.c.kind == RunKind.BUILD.value,
                runs.c.instance_version_id.in_(list(version_ids)),
            )
            .order_by(runs.c.queued_at.desc(), runs.c.id.desc())
        )
        latest: dict[str, RunState] = {}
        with self._engine.connect() as connection:
            for version, state in connection.execute(query):
                latest.setdefault(version, RunState(state))
        return latest

    def last_duration_s(self, step: StepName, dataset_id: str, radius_m: float) -> float | None:
        seconds = extract("epoch", run_steps.c.finished_at - run_steps.c.started_at)
        query = (
            select(seconds)
            .select_from(
                run_steps.join(runs, runs.c.id == run_steps.c.run_id)
                .join(instance_versions, instance_versions.c.id == runs.c.instance_version_id)
                .join(city_instances, city_instances.c.id == instance_versions.c.instance_id)
            )
            .where(
                runs.c.kind == RunKind.BUILD.value,
                run_steps.c.step == step.value,
                run_steps.c.state == StepState.DONE.value,
                run_steps.c.started_at.is_not(None),
                run_steps.c.finished_at.is_not(None),
                city_instances.c.dataset_id == dataset_id,
                instance_versions.c.radius_m == radius_m,
            )
            .order_by(run_steps.c.finished_at.desc(), run_steps.c.id.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            found = connection.execute(query).scalar()
        return None if found is None else float(found)

    def queue_build(
        self,
        run: Run,
        seal_version_at: datetime | None,
        checked: InstanceParameters | None = None,
    ) -> None:
        version_id = run.subject.id
        try:
            with self._engine.begin() as connection:
                # The row lock orders this request after a concurrent edit or deletion of the
                # draft, and before any that comes later (they lock the same row).
                status = connection.execute(
                    select(instance_versions.c.status)
                    .where(instance_versions.c.id == version_id)
                    .with_for_update()
                ).scalar()
                if status is None:
                    raise InstanceVersionNotFound(version_id)
                if seal_version_at is not None and status == "draft":
                    seal = update(instance_versions).where(instance_versions.c.id == version_id)
                    if checked is not None:
                        # Seal only the values the rules were checked on.
                        seal = seal.where(
                            *(
                                instance_versions.c[name] == value
                                for name, value in checked.as_dict().items()
                            )
                        )
                    sealed = connection.execute(
                        seal.values(status="sealed", sealed_at=seal_version_at)
                    )
                    if sealed.rowcount == 0:
                        raise DraftChanged(version_id)
                # A draft another request sealed meanwhile is not sealed again; the run that
                # request queued then refuses this insert (`uq_runs_active_subject`).
                connection.execute(insert(runs).values(run_values(run)))
                connection.execute(
                    insert(run_steps), [step_values(run.id, item) for item in run.steps]
                )
        except IntegrityError as error:
            if _constraint(error) != ACTIVE_SUBJECT_INDEX:
                raise
            raise RunActive(self._active_run_id(version_id)) from error

    def _active_run_id(self, version_id: str) -> str:
        query = (
            select(runs.c.id)
            .where(runs.c.instance_version_id == version_id)
            .where(runs.c.state.in_(["queued", "running"]))
            .limit(1)
        )
        with self._engine.connect() as connection:
            return str(connection.execute(query).scalar() or "")

    def delete_version(self, version_id: str) -> None:
        with self._engine.begin() as connection:
            instance_id = connection.execute(
                select(instance_versions.c.instance_id).where(instance_versions.c.id == version_id)
            ).scalar()
            if instance_id is None:
                raise InstanceVersionNotFound(version_id)
            # The instance row first (as `create_draft` locks it), then the version row (as
            # `queue_build` does): a concurrent draft, build request or deletion is ordered
            # against this one.
            connection.execute(
                select(city_instances.c.id)
                .where(city_instances.c.id == instance_id)
                .with_for_update()
            ).scalar()
            locked = connection.execute(
                select(instance_versions.c.id)
                .where(instance_versions.c.id == version_id)
                .with_for_update()
            ).scalar()
            if locked is None:
                raise InstanceVersionNotFound(version_id)
            self._remove_versions(connection, [version_id])
            remaining = connection.execute(
                select(func.count())
                .select_from(instance_versions)
                .where(instance_versions.c.instance_id == instance_id)
            ).scalar_one()
            if remaining == 0:
                connection.execute(delete(city_instances).where(city_instances.c.id == instance_id))

    def delete_instance(self, instance_id: str) -> None:
        with self._engine.begin() as connection:
            locked = connection.execute(
                select(city_instances.c.id)
                .where(city_instances.c.id == instance_id)
                .with_for_update()
            ).scalar()
            if locked is None:
                raise CityInstanceNotFound(instance_id)
            version_ids = list(
                connection.execute(
                    select(instance_versions.c.id)
                    .where(instance_versions.c.instance_id == instance_id)
                    .order_by(instance_versions.c.id)
                    .with_for_update()
                ).scalars()
            )
            self._remove_versions(connection, version_ids)
            connection.execute(delete(city_instances).where(city_instances.c.id == instance_id))

    @staticmethod
    def _remove_versions(connection: Connection, version_ids: list[str]) -> None:
        """Inside the transaction that holds the version rows: refuse while a run is active,
        then remove the runs and the versions (periods and step links cascade)."""
        if not version_ids:
            return
        active = connection.execute(
            select(runs.c.id)
            .where(runs.c.instance_version_id.in_(version_ids))
            .where(runs.c.state.in_(["queued", "running"]))
            .order_by(runs.c.queued_at, runs.c.id)
            .limit(1)
        ).scalar()
        if active is not None:
            raise RunActive(str(active))
        run_ids = select(runs.c.id).where(runs.c.instance_version_id.in_(version_ids))
        connection.execute(delete(run_steps).where(run_steps.c.run_id.in_(run_ids)))
        connection.execute(delete(runs).where(runs.c.instance_version_id.in_(version_ids)))
        connection.execute(delete(instance_versions).where(instance_versions.c.id.in_(version_ids)))
