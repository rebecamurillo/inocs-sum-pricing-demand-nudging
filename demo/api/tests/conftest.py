"""Rules of every test session, and the throwaway database the integration tests share."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from pricing_demo.infrastructure.persistence.engine import create_db_engine
from tests.support.database import migrate_to_head, require_database_url, reset_schema

_not_run: set[str] = set()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    # An xfail is reported as skipped, and an unexpected pass carries `wasxfail` too.
    if report.skipped or hasattr(report, "wasxfail"):
        _not_run.add(report.nodeid)


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.skipped:
        _not_run.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    if _not_run and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if _not_run:
        terminalreporter.section("skipped or xfailed tests", red=True)
        terminalreporter.write_line(
            "A test that does not run proves nothing (AGENTS.md rule 4): fix it or delete it."
        )
        for node_id in sorted(_not_run):
            terminalreporter.write_line(node_id)


@pytest.fixture
def integration_database_url(monkeypatch: pytest.MonkeyPatch) -> str:
    """The throwaway database's URL, also given to the application's own settings.

    Anything under test that reads `Settings().database_url` (the Alembic environment, the
    application factory) then reaches the throwaway database, never another.
    """
    url = require_database_url(os.environ)
    monkeypatch.setenv("PRICING_DEMO_DATABASE_URL", url)
    return url


@pytest.fixture
def empty_database(integration_database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(integration_database_url)
    reset_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    migrate_to_head()
    return empty_database
