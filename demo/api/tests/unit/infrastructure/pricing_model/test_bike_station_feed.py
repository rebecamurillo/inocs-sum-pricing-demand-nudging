import json
import subprocess
from pathlib import Path

import pytest

from pricing_demo.application.errors import BikeStationFetchFailed
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed


def child(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str = "", stderr: str = ""
) -> None:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert command[1:3] == [
            "-m",
            "pricing_demo.infrastructure.pricing_model.fetch_bike_stations",
        ]
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)


def test_the_childs_json_line_is_the_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    line = json.dumps({"file": str(tmp_path / "f.json"), "source_url": "https://x/gbfs.json"})
    child(monkeypatch, 0, f"noise\n{line}\n")

    fetched = PackageBikeStationFeed().fetch(tmp_path)

    assert (fetched.file, fetched.source_url) == (tmp_path / "f.json", "https://x/gbfs.json")


def test_a_failing_child_reports_its_last_stderr_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    child(monkeypatch, 1, stderr="Traceback\nConnectionError: no route\n")

    with pytest.raises(BikeStationFetchFailed, match="ConnectionError: no route"):
        PackageBikeStationFeed().fetch(tmp_path)


def test_a_child_that_prints_nothing_usable_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    child(monkeypatch, 0, "not json\n")

    with pytest.raises(BikeStationFetchFailed, match="unexpected"):
        PackageBikeStationFeed().fetch(tmp_path)


def test_a_child_that_takes_too_long_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 120)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(BikeStationFetchFailed, match="120 s"):
        PackageBikeStationFeed().fetch(tmp_path)
