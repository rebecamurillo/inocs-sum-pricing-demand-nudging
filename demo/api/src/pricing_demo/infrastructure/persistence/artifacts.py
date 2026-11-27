from collections.abc import Collection, Mapping, Sequence
from typing import Any

from sqlalchemy import Engine, delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.application.ports.artifacts import Artifact, StoredFile
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.persistence.tables import artifacts, instance_version_steps


def _artifact(row: Any) -> Artifact:
    return Artifact(
        input_key=row.input_key,
        step=StepName(row.step),
        inputs=row.inputs,
        files=tuple(StoredFile(item["name"], item["sha256"], item["bytes"]) for item in row.files),
        path=row.path,
        package_fingerprint=row.package_fingerprint,
        created_at=row.created_at,
        run_id=row.run_id,
        reported_counts=row.reported_counts,
    )


class PostgresArtifacts:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def stored_keys(self, keys: Collection[str]) -> set[str]:
        if not keys:
            return set()
        query = select(artifacts.c.input_key).where(artifacts.c.input_key.in_(list(keys)))
        with self._engine.connect() as connection:
            return set(connection.execute(query).scalars())

    def get(self, key: str) -> Artifact | None:
        with self._engine.connect() as connection:
            row = connection.execute(select(artifacts).where(artifacts.c.input_key == key)).first()
        return None if row is None else _artifact(row)

    def unreferenced(self) -> Sequence[Artifact]:
        query = select(artifacts).where(
            ~exists().where(instance_version_steps.c.input_key == artifacts.c.input_key)
        )
        with self._engine.connect() as connection:
            return [
                _artifact(row) for row in connection.execute(query.order_by(artifacts.c.input_key))
            ]

    def remove(self, key: str) -> bool:
        with self._engine.begin() as connection:
            # The lock on the artefact orders this against a link that is being made.
            locked = connection.execute(
                select(artifacts.c.input_key).where(artifacts.c.input_key == key).with_for_update()
            ).scalar()
            if locked is None:
                return False
            linked = connection.execute(
                select(instance_version_steps.c.input_key)
                .where(instance_version_steps.c.input_key == key)
                .limit(1)
            ).scalar()
            if linked is not None:
                return False
            connection.execute(delete(artifacts).where(artifacts.c.input_key == key))
        return True

    def add(self, artifact: Artifact) -> None:
        statement = (
            insert(artifacts)
            .values(
                input_key=artifact.input_key,
                step=artifact.step.value,
                inputs=dict(artifact.inputs),
                files=[
                    {"name": item.name, "sha256": item.sha256, "bytes": item.bytes}
                    for item in artifact.files
                ],
                path=artifact.path,
                package_fingerprint=artifact.package_fingerprint,
                created_at=artifact.created_at,
                run_id=artifact.run_id,
                reported_counts=dict(artifact.reported_counts),
            )
            .on_conflict_do_nothing(index_elements=["input_key"])
        )
        with self._engine.begin() as connection:
            connection.execute(statement)

    def link(self, version_id: str, step: StepName, period_id: str | None, key: str) -> None:
        statement = insert(instance_version_steps).values(
            instance_version_id=version_id, step=step.value, period_id=period_id, input_key=key
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_instance_version_steps_instance_version_id",
            set_={"input_key": statement.excluded.input_key},
        )
        with self._engine.begin() as connection:
            connection.execute(statement)

    def links_of(self, version_id: str) -> Mapping[StepName, str]:
        query = select(instance_version_steps.c.step, instance_version_steps.c.input_key).where(
            instance_version_steps.c.instance_version_id == version_id
        )
        with self._engine.connect() as connection:
            return {StepName(step): key for step, key in connection.execute(query)}
