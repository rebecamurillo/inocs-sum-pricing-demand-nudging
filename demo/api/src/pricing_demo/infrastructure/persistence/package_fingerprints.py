from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.domain.package_fingerprint import PackageFingerprint
from pricing_demo.infrastructure.persistence.tables import package_fingerprints


class PostgresPackageFingerprints:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, fingerprint: PackageFingerprint, at: datetime) -> None:
        statement = (
            insert(package_fingerprints)
            .values(
                fingerprint=fingerprint.fingerprint,
                version=fingerprint.version,
                git_commit=fingerprint.git_commit,
                git_dirty=fingerprint.git_dirty,
                defaults=fingerprint.defaults,
                first_seen_at=at,
            )
            .on_conflict_do_nothing(index_elements=["fingerprint"])
        )
        with self._engine.begin() as connection:
            connection.execute(statement)

    def latest(self) -> PackageFingerprint | None:
        query = (
            select(package_fingerprints)
            .order_by(
                package_fingerprints.c.first_seen_at.desc(), package_fingerprints.c.fingerprint
            )
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        if row is None:
            return None
        return PackageFingerprint(
            fingerprint=row.fingerprint,
            version=row.version,
            git_commit=row.git_commit,
            git_dirty=row.git_dirty,
            defaults=row.defaults,
        )
