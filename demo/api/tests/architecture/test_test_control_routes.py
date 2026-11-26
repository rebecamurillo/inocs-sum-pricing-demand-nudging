import json
from pathlib import Path
from types import ModuleType
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from pricing_demo import bootstrap
from pricing_demo.bootstrap import create_application
from pricing_demo.export_openapi import main, render_openapi
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.metadata import metadata
from pricing_demo.worker import main as worker_main

RESET = "/api/test-control/reset"
SOLVER = "/api/test-control/components/solver"


def application(adapters: Literal["fake", "real"]) -> FastAPI:
    return create_application(Settings(adapters=adapters))


def recording_settings(monkeypatch: pytest.MonkeyPatch, *namespaces: ModuleType) -> list[object]:
    """Replace the `fake_settings` store in the given modules by one that records its building."""
    built: list[object] = []

    class Recording(PostgresFakeSettings):
        def __init__(self, engine: Engine) -> None:
            built.append(engine)
            super().__init__(engine)

    for namespace in namespaces:
        monkeypatch.setattr(namespace, "PostgresFakeSettings", Recording)
    return built


def test_the_test_control_routes_are_absent_with_the_real_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    built = recording_settings(monkeypatch, bootstrap, worker_main)
    client = TestClient(application("real"))

    assert client.post(RESET).status_code == 404
    assert client.put(SOLVER, json={"state": "available"}).status_code == 404
    worker = worker_main.build_worker(Settings(adapters="real", data_dir=tmp_path / "data"))
    worker.engine.dispose()
    assert built == [], "the fake_settings store is never constructed with real adapters"


def test_the_fake_settings_store_is_built_by_the_fake_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    built = recording_settings(monkeypatch, bootstrap, worker_main)

    TestClient(application("fake"))
    worker = worker_main.build_worker(Settings(adapters="fake", data_dir=tmp_path / "data"))
    worker.engine.dispose()

    assert len(built) == 2


def test_the_test_control_routes_are_present_with_the_fake_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # make check has no database; truncation is covered by the integration and e2e suites.
    emptied: list[object] = []
    written: list[tuple[str, object]] = []
    monkeypatch.setattr(
        bootstrap, "truncate_all", lambda engine, metadata: emptied.append(metadata)
    )
    monkeypatch.setattr(
        PostgresFakeSettings, "write_defaults", lambda self: written.append(("defaults", None))
    )
    monkeypatch.setattr(
        PostgresFakeSettings,
        "set_component",
        lambda self, name, state, reason: written.append((name, (state, reason))),
    )
    client = TestClient(application("fake"))

    assert client.post(RESET).status_code == 204
    assert len(emptied) == 1
    assert emptied[0] is metadata
    assert written == [("defaults", None)]
    assert (
        client.put(
            SOLVER, json={"state": "unavailable", "reason": "No Gurobi licence was found."}
        ).status_code
        == 204
    )
    assert written[-1] == ("solver", ("unavailable", "No Gurobi licence was found."))


def test_the_test_control_routes_are_not_in_the_exported_contract(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    assert main([str(target)]) == 0

    contract = target.read_text(encoding="utf-8")
    assert "/api/v1/system-status" in json.loads(contract)["paths"]
    assert "test-control" not in contract


def test_the_exported_contract_is_deterministic() -> None:
    first = render_openapi()

    assert render_openapi() == first
    assert first == json.dumps(json.loads(first), indent=2, sort_keys=True) + "\n"


def test_the_export_needs_a_path() -> None:
    assert main([]) == 2


@pytest.mark.parametrize(
    "schema",
    [
        "SystemStatusResponse",
        "ComponentStatusResponse",
        "VerdictResponse",
        "BlockingReasonResponse",
        "ProblemDetails",
    ],
)
def test_the_contract_names_its_schemas(schema: str) -> None:
    assert schema in json.loads(render_openapi())["components"]["schemas"]
