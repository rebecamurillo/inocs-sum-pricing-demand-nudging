from datetime import datetime
from typing import Any

from sqlalchemy import Engine, null, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.domain.package_fingerprint import PackageFingerprint
from pricing_demo.infrastructure.persistence.tables import package_fingerprints


class PostgresPackageFingerprints:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, fingerprint: PackageFingerprint, at: datetime) -> None:
        insertion = insert(package_fingerprints)
        statement = insertion.values(
            fingerprint=fingerprint.fingerprint,
            version=fingerprint.version,
            git_commit=fingerprint.git_commit,
            git_dirty=fingerprint.git_dirty,
            defaults=fingerprint.defaults,
            # SQL null, not the JSON null a Python None would be stored as.
            choice_coefficients=fingerprint.choice_coefficients or null(),
            first_seen_at=at,
        ).on_conflict_do_update(
            index_elements=["fingerprint"],
            # A row recorded before the coefficients were read gets them once; nothing
            # else of a recorded row changes.
            set_={"choice_coefficients": insertion.excluded.choice_coefficients},
            where=package_fingerprints.c.choice_coefficients.is_(None),
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
        return None if row is None else _fingerprint(row)

    def get(self, fingerprint: str) -> PackageFingerprint | None:
        query = select(package_fingerprints).where(
            package_fingerprints.c.fingerprint == fingerprint
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        return None if row is None else _fingerprint(row)


def _fingerprint(row: Any) -> PackageFingerprint:
    return PackageFingerprint(
        fingerprint=row.fingerprint,
        version=row.version,
        git_commit=row.git_commit,
        git_dirty=row.git_dirty,
        defaults=row.defaults,
        choice_coefficients=row.choice_coefficients or {},
    )
