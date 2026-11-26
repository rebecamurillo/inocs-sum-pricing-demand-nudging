from collections.abc import Mapping

from sqlalchemy import Engine, select

from pricing_demo.infrastructure.persistence.tables import component_reports, workers


class PostgresBuildSources:
    """What the API knows of the package and the trip planner's graph: the fingerprint of the
    worker that beat last and the manifest of the latest `trip_planner` report."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def package_fingerprint(self) -> str | None:
        query = (
            select(workers.c.package_fingerprint)
            .where(workers.c.package_fingerprint.is_not(None))
            .order_by(workers.c.heartbeat_at.desc(), workers.c.id)
            .limit(1)
        )
        with self._engine.connect() as connection:
            found: str | None = connection.execute(query).scalar()
        return found

    def graph_manifest(self) -> Mapping[str, object] | None:
        query = select(component_reports.c.details).where(
            component_reports.c.component == "trip_planner"
        )
        with self._engine.connect() as connection:
            details = connection.execute(query).scalar()
        manifest = (details or {}).get("graph_manifest")
        return manifest if isinstance(manifest, dict) else None
