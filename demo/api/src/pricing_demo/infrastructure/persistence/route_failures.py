from datetime import datetime

from sqlalchemy import Engine, insert, select

from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.infrastructure.persistence.tables import route_failures, run_steps


def _failure(row: object) -> RouteFailure:
    return RouteFailure(
        row.origin_hub,  # type: ignore[attr-defined]
        row.destination_hub,  # type: ignore[attr-defined]
        row.query,  # type: ignore[attr-defined]
        row.kind,  # type: ignore[attr-defined]
        row.message,  # type: ignore[attr-defined]
        row.attempts,  # type: ignore[attr-defined]
    )


class PostgresRouteFailures:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(
        self,
        run_id: str,
        position: int,
        period_id: str | None,
        failure: RouteFailure,
        occurred_at: datetime,
    ) -> None:
        step = (
            select(run_steps.c.id)
            .where(run_steps.c.run_id == run_id, run_steps.c.position == position)
            .scalar_subquery()
        )
        with self._engine.begin() as connection:
            connection.execute(
                insert(route_failures).values(
                    run_id=run_id,
                    run_step_id=step,
                    instance_period_id=period_id,
                    origin_hub=failure.origin_hub,
                    destination_hub=failure.destination_hub,
                    query=failure.query,
                    kind=failure.kind,
                    message=failure.message,
                    attempts=failure.attempts,
                    occurred_at=occurred_at,
                )
            )

    def clear(self, run_id: str, position: int) -> None:
        step = (
            select(run_steps.c.id)
            .where(run_steps.c.run_id == run_id, run_steps.c.position == position)
            .scalar_subquery()
        )
        with self._engine.begin() as connection:
            connection.execute(route_failures.delete().where(route_failures.c.run_step_id == step))

    def of_run(self, run_id: str) -> list[tuple[RouteFailure, str | None]]:
        query = select(route_failures).where(route_failures.c.run_id == run_id).order_by(*_ORDER)
        with self._engine.connect() as connection:
            return [(_failure(row), row.instance_period_id) for row in connection.execute(query)]

    def of_step(self, run_id: str, position: int) -> list[RouteFailure]:
        query = (
            select(route_failures)
            .join(run_steps, run_steps.c.id == route_failures.c.run_step_id)
            .where(run_steps.c.run_id == run_id, run_steps.c.position == position)
            .order_by(*_ORDER)
        )
        with self._engine.connect() as connection:
            return [_failure(row) for row in connection.execute(query)]


_ORDER = (
    route_failures.c.origin_hub,
    route_failures.c.destination_hub,
    route_failures.c.query,
)
