import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from pricing_demo import bootstrap
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.persistence.engine import create_db_engine

UNREACHABLE_DATABASE = "postgresql+psycopg://user:secret@127.0.0.1:1/missing"


def test_the_database_engine_is_disposed_when_the_application_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engines: list[Engine] = []

    def build_engine(database_url: str) -> Engine:
        engines.append(create_db_engine(database_url))
        return engines[-1]

    monkeypatch.setattr(bootstrap, "create_db_engine", build_engine)
    app = bootstrap.create_application(Settings(adapters="fake", database_url=UNREACHABLE_DATABASE))
    pool_in_service = engines[0].pool

    with TestClient(app):
        assert engines[0].pool is pool_in_service

    assert engines[0].pool is not pool_in_service


def test_liveness_needs_no_component_of_the_real_adapters() -> None:
    app = bootstrap.create_application(Settings(adapters="real", database_url=UNREACHABLE_DATABASE))

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
