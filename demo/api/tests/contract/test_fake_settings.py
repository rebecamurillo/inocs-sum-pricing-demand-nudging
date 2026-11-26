"""The fake settings store: one suite, run against the in-memory and the PostgreSQL store."""

from collections.abc import Iterator
from typing import Protocol

import pytest
from sqlalchemy import Engine

from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings


class Store(Protocol):
    def read(self) -> object: ...
    def set_component(self, name: str, state: str, reason: str | None) -> None: ...
    def write_defaults(self) -> None: ...


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def store(request: pytest.FixtureRequest) -> Iterator[Store]:
    if request.param == "memory":
        yield InMemoryFakeSettings()
    else:
        engine: Engine = request.getfixturevalue("migrated_database")
        yield PostgresFakeSettings(engine)


def test_the_store_is_empty_until_something_is_written(store: Store) -> None:
    assert store.read() == {}


def test_a_component_set_is_read_back(store: Store) -> None:
    store.set_component("solver", "limited", "Size-limited.")

    assert store.read() == {
        "components": {"solver": {"state": "limited", "reason": "Size-limited."}}
    }


def test_setting_a_component_replaces_its_entry_and_keeps_the_others(store: Store) -> None:
    store.set_component("solver", "limited", "Size-limited.")
    store.set_component("trip_planner", "unavailable", "No answer.")

    store.set_component("solver", "available", None)

    assert store.read() == {
        "components": {
            "solver": {"state": "available", "reason": None},
            "trip_planner": {"state": "unavailable", "reason": "No answer."},
        }
    }


def test_the_defaults_make_every_probed_component_available(store: Store) -> None:
    store.set_component("solver", "limited", "Size-limited.")

    store.write_defaults()

    assert store.read() == {
        "components": {
            "solver": {"state": "available", "reason": None},
            "package": {"state": "available", "reason": None},
            "trip_planner": {"state": "available", "reason": None},
        }
    }
