"""Two runs that stored the same artefact key ingest it at the same time: the second waits for
the first and replaces its rows; neither fails."""

import threading
import time
from collections.abc import Sequence
from typing import Any

import pytest
from sqlalchemy import Connection, Table, text

from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.persistence import read_model as adapter
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from tests.integration.test_builds import Rig, rig  # noqa: F401

pytestmark = pytest.mark.integration

WAIT_S = 10.0


def _waiting_on_a_lock(stack: Rig) -> bool:
    query = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE wait_event_type = 'Lock' AND datname = current_database()"
    )
    with stack.engine.connect() as connection:
        return bool(connection.execute(query).scalar())


def test_a_second_ingestion_of_the_same_key_waits_and_replaces_the_first(
    rig: Rig,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = rig.build.execute(rig.draft())
    rig.process.execute()
    key = rig.run_of(queued.id).steps[0].input_key or ""
    model = PostgresReadModel(rig.engine)
    batch = IngestionBatch(
        key, StepName.AREA, {"stops": 30, "bike_stations": 12}, stations=model.stations(key)
    )
    with rig.engine.begin() as connection:
        connection.execute(text("DELETE FROM stations"))
        connection.execute(text("UPDATE artifacts SET counts = NULL, ingested_at = NULL"))

    inserted, release = threading.Event(), threading.Event()
    original = adapter._insert_all

    def pausing(connection: Connection, table: Table, values: Sequence[dict[str, Any]]) -> None:
        original(connection, table, values)
        if threading.current_thread().name == "first" and table.name == "stations":
            inserted.set()
            release.wait(WAIT_S)

    monkeypatch.setattr(adapter, "_insert_all", pausing)
    errors: list[BaseException] = []

    def ingest() -> None:
        try:
            model.ingest(batch)
        except BaseException as error:  # reported by the assertion below
            errors.append(error)

    first = threading.Thread(target=ingest, name="first")
    second = threading.Thread(target=ingest, name="second")
    first.start()
    assert inserted.wait(WAIT_S)
    second.start()
    deadline = time.monotonic() + WAIT_S
    while not _waiting_on_a_lock(rig):
        assert time.monotonic() < deadline, "the second ingestion never waited"
        time.sleep(0.05)
    release.set()
    first.join(WAIT_S)
    second.join(WAIT_S)

    assert errors == []
    assert len(rig.rows("stations")) == 42
    assert model.is_ingested(key) is True
