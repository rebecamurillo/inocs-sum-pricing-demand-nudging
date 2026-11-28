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
    def set_pricing_model(self, value: dict[str, object] | None) -> None: ...
    def release_run(self, run_id: str) -> None: ...
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


def test_the_pricing_model_settings_are_read_back_beside_the_components(store: Store) -> None:
    store.set_component("solver", "limited", "Size-limited.")

    store.set_pricing_model(
        {"fail_at": {"step": "routes", "code": "stage_error"}, "routes_pace_ms": 5}
    )

    assert store.read() == {
        "components": {"solver": {"state": "limited", "reason": "Size-limited."}},
        "pricing_model": {
            "fail_at": {"step": "routes", "code": "stage_error"},
            "routes_pace_ms": 5,
        },
    }


def test_setting_the_pricing_model_replaces_it_and_none_returns_it_to_its_defaults(
    store: Store,
) -> None:
    store.set_pricing_model({"hold_at": "hubs"})
    store.set_pricing_model({"routes_pace_ms": 5})

    assert store.read() == {"pricing_model": {"routes_pace_ms": 5}}

    store.set_pricing_model(None)

    assert store.read() == {}


def test_setting_a_component_keeps_the_pricing_model_settings(store: Store) -> None:
    store.set_pricing_model({"hold_at": "hubs"})

    store.set_component("solver", "available", None)

    assert store.read()["pricing_model"] == {"hold_at": "hubs"}  # type: ignore[index]


def test_a_released_run_is_listed_once_and_the_releases_accumulate(store: Store) -> None:
    store.release_run("run-1")
    store.release_run("run-2")
    store.release_run("run-1")

    assert store.read() == {"released_runs": ["run-1", "run-2"]}


def test_the_defaults_forget_the_pricing_model_and_the_releases(store: Store) -> None:
    store.set_pricing_model({"hold_at": "hubs"})
    store.release_run("run-1")

    store.write_defaults()

    assert "pricing_model" not in store.read()  # type: ignore[operator]
    assert "released_runs" not in store.read()  # type: ignore[operator]
