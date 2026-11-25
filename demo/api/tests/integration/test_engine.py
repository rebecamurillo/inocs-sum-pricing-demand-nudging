import pytest
from sqlalchemy import text

from pricing_demo.infrastructure.persistence.engine import create_db_engine

pytestmark = pytest.mark.integration


def test_a_connection_the_server_closed_is_replaced_before_it_is_used(
    integration_database_url: str,
) -> None:
    engine = create_db_engine(integration_database_url)
    admin = create_db_engine(integration_database_url)
    try:
        with engine.connect() as connection:
            backend = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
        with admin.begin() as connection:
            connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": backend})

        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
        admin.dispose()
