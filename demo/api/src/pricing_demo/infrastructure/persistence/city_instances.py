from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from sqlalchemy import Connection, Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from pricing_demo.domain.city_instances import (
    PARAMETER_NAMES,
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
from pricing_demo.infrastructure.persistence.tables import (
    city_instances,
    instance_periods,
    instance_versions,
)

NAME_CONSTRAINTS = {"pk_city_instances", "uq_city_instances_name"}


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _version(row) -> InstanceVersion:  # type: ignore[no-untyped-def]
    return InstanceVersion(
        id=row.id,
        instance_id=row.instance_id,
        number=row.number,
        based_on_id=row.based_on_id,
        status=row.status,
        parameters=InstanceParameters(**{name: getattr(row, name) for name in PARAMETER_NAMES}),
        created_at=row.created_at,
        sealed_at=row.sealed_at,
    )


def version_values(version: InstanceVersion) -> dict[str, object]:
    return {
        "id": version.id,
        "instance_id": version.instance_id,
        "number": version.number,
        "based_on_id": version.based_on_id,
        "status": version.status,
        **version.parameters.as_dict(),
        "created_at": version.created_at,
        "sealed_at": version.sealed_at,
    }


def period_values(period: InstancePeriod) -> dict[str, object]:
    return {
        "id": period.id,
        "instance_version_id": period.instance_version_id,
        "key": period.key,
        "label": period.label,
        "weekday": period.weekday,
        "start_time": period.start_time,
        "end_time": period.end_time,
        "routing_date": period.routing_date,
        "routing_time": period.routing_time,
        "arrive_by": period.arrive_by,
        "routing_date_provisional": period.routing_date_provisional,
    }


class PostgresCityInstances:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self, instance: CityInstance, draft: InstanceVersion, period: InstancePeriod
    ) -> None:
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    city_instances.insert().values(
                        id=instance.id,
                        name=instance.name,
                        dataset_id=instance.dataset_id,
                        next_number=instance.next_number,
                        created_at=instance.created_at,
                    )
                )
                connection.execute(instance_versions.insert().values(version_values(draft)))
                connection.execute(instance_periods.insert().values(period_values(period)))
        except IntegrityError as error:
            if _constraint(error) in NAME_CONSTRAINTS:
                raise CityInstanceNameTaken(instance.name) from error
            raise

    def get_instance(self, instance_id: str) -> CityInstance | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(city_instances).where(city_instances.c.id == instance_id)
            ).first()
        return self._instance(row) if row else None

    def create_draft(
        self,
        instance_id: str,
        based_on_id: str | None,
        parameters: InstanceParameters,
        created_at: datetime,
        period_for: Callable[[str], InstancePeriod],
    ) -> InstanceVersion:
        try:
            with self._engine.begin() as connection:
                # The row lock serialises two drafts of one instance: the second sees the
                # first's draft, or its incremented number.
                instance = connection.execute(
                    select(city_instances)
                    .where(city_instances.c.id == instance_id)
                    .with_for_update()
                ).first()
                if instance is None:
                    raise CityInstanceNotFound(instance_id)
                existing = self._draft_id(connection, instance_id)
                if existing is not None:
                    raise DraftExists(instance_id, existing)
                number = instance.next_number
                connection.execute(
                    update(city_instances)
                    .where(city_instances.c.id == instance_id)
                    .values(next_number=number + 1)
                )
                draft = InstanceVersion(
                    version_id(instance_id, number),
                    instance_id,
                    number,
                    based_on_id,
                    "draft",
                    parameters,
                    created_at,
                )
                connection.execute(instance_versions.insert().values(version_values(draft)))
                connection.execute(
                    instance_periods.insert().values(period_values(period_for(draft.id)))
                )
                return draft
        except IntegrityError as error:
            if _constraint(error) != "uq_instance_versions_one_draft":
                raise
            with self._engine.connect() as connection:
                existing = self._draft_id(connection, instance_id)
            raise DraftExists(instance_id, existing or "") from error

    def get_version(self, version_id: str) -> InstanceVersion | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(instance_versions).where(instance_versions.c.id == version_id)
            ).first()
        return _version(row) if row else None

    def periods_of(self, version_id: str) -> Sequence[InstancePeriod]:
        query = (
            select(instance_periods)
            .where(instance_periods.c.instance_version_id == version_id)
            .order_by(instance_periods.c.id)
        )
        with self._engine.connect() as connection:
            return [
                InstancePeriod(
                    id=row.id,
                    instance_version_id=row.instance_version_id,
                    key=row.key,
                    label=row.label,
                    weekday=row.weekday,
                    start_time=row.start_time,
                    end_time=row.end_time,
                    routing_date=row.routing_date,
                    routing_time=row.routing_time,
                    arrive_by=row.arrive_by,
                    routing_date_provisional=row.routing_date_provisional,
                )
                for row in connection.execute(query)
            ]

    def update_draft_parameters(
        self, version_id: str, changes: Mapping[str, Number]
    ) -> InstanceVersion:
        with self._engine.begin() as connection:
            self._lock_draft(connection, version_id)
            # Only the named columns are written: a change sent at the same time to another
            # parameter is kept, not overwritten by the value this request read before it.
            if changes:
                connection.execute(
                    update(instance_versions)
                    .where(instance_versions.c.id == version_id)
                    .values(**changes)
                )
            row = connection.execute(
                select(instance_versions).where(instance_versions.c.id == version_id)
            ).one()
        return _version(row)

    def delete_draft(self, version_id: str) -> None:
        with self._engine.begin() as connection:
            instance_id = self._lock_draft(connection, version_id)
            connection.execute(
                delete(instance_versions).where(instance_versions.c.id == version_id)
            )
            remaining = connection.execute(
                select(func.count())
                .select_from(instance_versions)
                .where(instance_versions.c.instance_id == instance_id)
            ).scalar_one()
            if remaining == 0:
                connection.execute(delete(city_instances).where(city_instances.c.id == instance_id))

    def menu(self) -> Sequence[InstanceWithVersions]:
        with self._engine.connect() as connection:
            instances = [
                self._instance(row)
                for row in connection.execute(
                    select(city_instances).order_by(
                        city_instances.c.created_at, city_instances.c.id
                    )
                )
            ]
            versions = [
                _version(row)
                for row in connection.execute(
                    select(instance_versions).order_by(
                        instance_versions.c.instance_id, instance_versions.c.number
                    )
                )
            ]
        return [
            InstanceWithVersions(
                instance, [item for item in versions if item.instance_id == instance.id]
            )
            for instance in instances
        ]

    @staticmethod
    def _lock_draft(connection: Connection, version_id: str) -> str:
        """Lock the version's row and return its instance id; refuses a missing or sealed one."""
        row = connection.execute(
            select(instance_versions.c.instance_id, instance_versions.c.status)
            .where(instance_versions.c.id == version_id)
            .with_for_update()
        ).first()
        if row is None:
            raise InstanceVersionNotFound(version_id)
        if row.status == "sealed":
            raise VersionSealed(version_id)
        return str(row.instance_id)

    @staticmethod
    def _draft_id(connection: Connection, instance_id: str) -> str | None:
        found = connection.execute(
            select(instance_versions.c.id).where(
                instance_versions.c.instance_id == instance_id,
                instance_versions.c.status == "draft",
            )
        ).scalar()
        return None if found is None else str(found)

    @staticmethod
    def _instance(row) -> CityInstance:  # type: ignore[no-untyped-def]
        return CityInstance(row.id, row.name, row.dataset_id, row.next_number, row.created_at)
