import json
from pathlib import Path
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pricing_demo import bootstrap
from pricing_demo.bootstrap import create_application
from pricing_demo.export_openapi import main, render_openapi
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.persistence.metadata import metadata

RESET = "/api/test-control/reset"
SOLVER = "/api/test-control/components/solver"


def application(adapters: Literal["fake", "real"]) -> FastAPI:
    return create_application(Settings(adapters=adapters))


def test_the_test_control_routes_are_absent_with_the_real_adapters() -> None:
    client = TestClient(application("real"))

    assert client.post(RESET).status_code == 404
    assert client.put(SOLVER, json={"available": True}).status_code == 404


def test_the_test_control_routes_are_present_with_the_fake_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The metadata now holds the run tables, so the reset reaches for a database; the
    # integration suite (test_truncate.py) covers the real emptying.
    emptied: list[object] = []
    monkeypatch.setattr(
        bootstrap, "truncate_all", lambda engine, metadata: emptied.append(metadata)
    )
    client = TestClient(application("fake"))

    assert client.post(RESET).status_code == 204
    assert emptied == [metadata]
    assert (
        client.put(
            SOLVER, json={"available": False, "reason": "No Gurobi licence was found."}
        ).status_code
        == 204
    )


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
    "schema", ["SystemStatusResponse", "ComponentStatusResponse", "ProblemDetails"]
)
def test_the_contract_names_its_schemas(schema: str) -> None:
    assert schema in json.loads(render_openapi())["components"]["schemas"]
