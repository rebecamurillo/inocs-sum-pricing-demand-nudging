from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.application.ports.showcase import ShowcaseMark
from pricing_demo.infrastructure.persistence.tables import showcase

ROW_ID = 1


class PostgresShowcase:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def mark(self, pricing_version_id: str, period_id: str, at: datetime) -> None:
        statement = insert(showcase).values(
            id=ROW_ID, pricing_version_id=pricing_version_id, period_id=period_id, marked_at=at
        )
        with self._engine.begin() as connection:
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "pricing_version_id": statement.excluded.pricing_version_id,
                        "period_id": statement.excluded.period_id,
                        "marked_at": statement.excluded.marked_at,
                    },
                )
            )

    def current(self) -> ShowcaseMark | None:
        with self._engine.connect() as connection:
            row = connection.execute(select(showcase).where(showcase.c.id == ROW_ID)).first()
        if row is None:
            return None
        return ShowcaseMark(row.pricing_version_id, row.period_id, row.marked_at)
