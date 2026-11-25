"""The throwaway PostgreSQL of the integration tests.

Its URL comes from one variable that only `make test-integration` sets. The application's own
`PRICING_DEMO_DATABASE_URL` is never a fallback: these tests drop the `public` schema, and
that URL defaults to the database `make dev` uses.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

TEST_DATABASE_ENV = "PRICING_DEMO_TEST_DATABASE_URL"
ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"


def require_database_url(environ: Mapping[str, str]) -> str:
    url = environ.get(TEST_DATABASE_ENV)
    if not url:
        pytest.fail(
            f"{TEST_DATABASE_ENV} is not set. Integration tests empty the database they "
            "run on, so they never use the application's database: run `make test-integration`, "
            "which starts a throwaway PostgreSQL and sets it.",
            pytrace=False,
        )
    return url


def reset_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def migrate_to_head() -> None:
    """Apply every migration to the database that `PRICING_DEMO_DATABASE_URL` names."""
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
