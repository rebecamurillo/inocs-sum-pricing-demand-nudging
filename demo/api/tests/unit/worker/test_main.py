import os
import socket
from pathlib import Path

import pytest

from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.worker.main import build_worker, worker_id_for


def settings_for(tmp_path: Path, **fields: object) -> Settings:
    return Settings(data_dir=tmp_path / "data", **fields)  # type: ignore[arg-type]


def test_the_worker_id_is_host_and_pid_when_none_is_set(tmp_path: Path) -> None:
    assert worker_id_for(settings_for(tmp_path), "laptop", 4242) == "laptop-4242"


def test_the_worker_id_is_the_configured_one_when_set(tmp_path: Path) -> None:
    assert worker_id_for(settings_for(tmp_path, worker_id="w-1"), "laptop", 4242) == "w-1"


def test_building_the_worker_creates_the_data_directory(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    assert not settings.data_dir.exists()

    built = build_worker(settings)
    built.engine.dispose()

    assert (settings.data_dir).is_dir()


def test_the_built_worker_identifies_itself_with_the_host_and_the_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICING_DEMO_WORKER_ID", raising=False)

    built = build_worker(settings_for(tmp_path))
    built.engine.dispose()

    assert built.identity.host == socket.gethostname()
    assert built.identity.pid == os.getpid()
    assert built.identity.id == f"{socket.gethostname()}-{os.getpid()}"


def test_a_configured_worker_id_is_the_built_workers_id(tmp_path: Path) -> None:
    built = build_worker(settings_for(tmp_path, worker_id="w-9"))
    built.engine.dispose()

    assert built.identity.id == "w-9"
