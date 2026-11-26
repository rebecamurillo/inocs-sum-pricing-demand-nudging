from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.application.ports.component_reports import ReportedComponents
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentReport,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.persistence.tables import component_reports, workers


class PostgresComponentReports:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(
        self,
        status: ComponentStatus,
        worker_id: str,
        at: datetime,
        details: Mapping[str, object] | None = None,
    ) -> None:
        statement = insert(component_reports).values(
            component=status.name.value,
            state=status.state.value,
            reason=status.reason,
            details=dict(details or {}),
            reported_at=at,
            worker_id=worker_id,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["component"],
            set_={
                "state": statement.excluded.state,
                "reason": statement.excluded.reason,
                "details": statement.excluded.details,
                "reported_at": statement.excluded.reported_at,
                "worker_id": statement.excluded.worker_id,
            },
        )
        with self._engine.begin() as connection:
            connection.execute(statement)

    def read(self) -> ReportedComponents:
        joined = component_reports.outerjoin(workers, workers.c.id == component_reports.c.worker_id)
        query = select(
            component_reports, workers.c.heartbeat_at.label("worker_heartbeat_at")
        ).select_from(joined)
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
            latest = connection.execute(select(func.max(workers.c.heartbeat_at))).scalar()
        probed = {name.value: name for name in PROBED_COMPONENTS}
        reports = tuple(
            ComponentReport(
                status=ComponentStatus(
                    ComponentName(row.component), ComponentState(row.state), row.reason
                ),
                reported_at=row.reported_at,
                worker_id=row.worker_id,
                worker_heartbeat_at=row.worker_heartbeat_at,
                details=row.details,
            )
            for row in rows
            if row.component in probed
        )
        return ReportedComponents(reports, latest)
