"""ComposeGraphBuilder with a stand-in `docker` on PATH: the graph is never built for real."""

import os
import stat
from pathlib import Path

import pytest

from pricing_demo.application.errors import GraphBuildFailed
from pricing_demo.infrastructure.config.settings import DEMO_DIR
from pricing_demo.infrastructure.trip_planner.graph_builder import (
    ComposeGraphBuilder,
    otp_image_from_compose,
)

STAND_IN = """#!/bin/sh
echo "$PWD|$@" >> "$LOG"
exit ${EXIT:-0}
"""


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "docker"
    script.write_text(STAND_IN)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "docker.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LOG", str(log))
    return log


def demo_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "compose.yaml").write_text(
        "services:\n  otp:\n    image: other:1\n  otp-build:\n    profiles: [otp]\n"
        "    image: example/otp:9\n    command: ['--build']\n  web:\n    image: web:1\n"
    )
    return folder


def test_the_image_is_the_one_of_the_otp_build_service_of_the_real_compose_file() -> None:
    assert otp_image_from_compose(DEMO_DIR / "compose.yaml") == (
        "opentripplanner/opentripplanner:2.10.0"
    )


def test_a_compose_file_without_otp_build_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "compose.yaml"
    path.write_text("services:\n  otp:\n    image: x:1\n")

    with pytest.raises(GraphBuildFailed, match=r"compose\.yaml"):
        otp_image_from_compose(path)


def test_the_builder_names_its_image(tmp_path: Path) -> None:
    assert ComposeGraphBuilder(demo_dir(tmp_path)).image == "example/otp:9"


def test_the_build_runs_the_compose_service_in_the_demo_folder(
    tmp_path: Path, docker: Path
) -> None:
    folder = demo_dir(tmp_path)

    ComposeGraphBuilder(folder).build()

    (call,) = docker.read_text().splitlines()
    assert call.split("|") == [str(folder.resolve()), "compose --profile otp run --rm otp-build"]


def test_a_non_zero_exit_is_a_reason(
    tmp_path: Path, docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXIT", "3")

    with pytest.raises(GraphBuildFailed, match="exited with code 3"):
        ComposeGraphBuilder(demo_dir(tmp_path)).build()


def test_a_missing_docker_binary_is_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = demo_dir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))

    with pytest.raises(GraphBuildFailed, match="Docker is not available"):
        ComposeGraphBuilder(folder).build()


def test_a_graph_folder_compose_does_not_mount_is_refused_before_docker_runs(
    tmp_path: Path, docker: Path
) -> None:
    folder = demo_dir(tmp_path)

    with pytest.raises(GraphBuildFailed, match="PRICING_DEMO_OTP_GRAPH_DIR"):
        ComposeGraphBuilder(folder, graph_dir=tmp_path / "elsewhere").build()

    assert not docker.exists()


def test_the_mounted_graph_folder_is_built(tmp_path: Path, docker: Path) -> None:
    folder = demo_dir(tmp_path)

    ComposeGraphBuilder(folder, graph_dir=folder / "otp" / "data").build()

    assert len(docker.read_text().splitlines()) == 1
