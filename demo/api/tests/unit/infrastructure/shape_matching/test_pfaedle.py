"""DockerPfaedleMatcher with a stand-in `docker` on PATH: no real Docker is needed."""

import os
import stat
from pathlib import Path

import pytest

from pricing_demo.application.errors import BusShapeMatchingFailed
from pricing_demo.domain.city_datasets import NO_BUS_SHAPE_REASON
from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher
from tests.support.city_data import TINY_PBF, zip_gtfs

IMAGE = "example/pfaedle@sha256:abc"

# A stand-in for the Docker CLI. It logs every call; `create` prints a container id, `cp` into the
# container does nothing, `start` behaves as MODE says, `cp` out of the container writes the
# output folder, `rm` logs.
STAND_IN = """#!/bin/sh
echo "$@" >> "$LOG"
case "$1" in
  create) echo cid123 ;;
  cp)
    case "$2" in
      cid123:*)
        mkdir -p "$3"
        case "$MODE" in
          ok)
            printf 'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\\ns1,46.2,6.1,1\\n' \\
              > "$3/shapes.txt"
            printf 'route_id,service_id,trip_id,shape_id\\nR1,WD,T1,s1\\nR2,WD,T2,\\n' \\
              > "$3/trips.txt"
            printf 'junk' > "$3/stop_times.txt" ;;
          header_only)
            printf 'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\\n' > "$3/shapes.txt"
            printf 'route_id,service_id,trip_id,shape_id\\nR1,WD,T1,\\n' > "$3/trips.txt" ;;
          no_trip_id)
            printf 'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\\ns1,46.2,6.1,1\\n' \\
              > "$3/shapes.txt"
            printf 'route_id,service_id,shape_id\\nR1,WD,s1\\n' > "$3/trips.txt" ;;
          copy_hang) sleep 5 ;;
        esac ;;
    esac ;;
  start)
    case "$MODE" in
      fail) echo "loading" >&2; echo "ERROR: boom" >&2; echo "" >&2; exit 3 ;;
      hang) sleep 5 ;;
    esac ;;
esac
exit 0
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
    monkeypatch.setenv("MODE", "ok")
    return log


def run(tmp_path: Path, **options: float) -> object:
    return DockerPfaedleMatcher(IMAGE, **options).match(zip_gtfs(tmp_path / "f.zip"), TINY_PBF)


def test_the_matcher_names_its_image() -> None:
    assert DockerPfaedleMatcher(IMAGE).image == IMAGE


def test_the_shapes_and_the_trip_shape_ids_are_read_and_nothing_else_is_kept(
    tmp_path: Path, docker: Path
) -> None:
    result = DockerPfaedleMatcher(IMAGE).match(zip_gtfs(tmp_path / "f.zip"), TINY_PBF)

    assert result.shapes_txt.startswith(b"shape_id,shape_pt_lat")
    assert result.trip_shapes == {"T1": "s1"}


def test_the_container_gets_the_image_the_bus_mode_and_the_paths(
    tmp_path: Path, docker: Path
) -> None:
    DockerPfaedleMatcher(IMAGE).match(zip_gtfs(tmp_path / "f.zip"), TINY_PBF)

    calls = docker.read_text().splitlines()
    create = next(call for call in calls if call.startswith("create"))
    assert IMAGE in create
    for flag in ("-m bus", "-D", "-x ", "-o "):
        assert flag in create
    assert [call.split()[0] for call in calls] == ["create", "cp", "cp", "start", "cp", "rm"]
    assert calls[-1] == "rm -f cid123"


def test_a_missing_docker_binary_is_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))

    with pytest.raises(BusShapeMatchingFailed, match="Docker is not available"):
        run(tmp_path)


def test_a_non_zero_exit_gives_the_code_and_the_last_stderr_line(
    tmp_path: Path, docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODE", "fail")

    with pytest.raises(BusShapeMatchingFailed) as error:
        run(tmp_path)

    assert error.value.reason == "pfaedle exited with code 3: ERROR: boom"
    assert docker.read_text().splitlines()[-1] == "rm -f cid123"


def test_a_timeout_names_the_timeout(
    tmp_path: Path, docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODE", "hang")

    with pytest.raises(BusShapeMatchingFailed, match=r"timed out after 0\.2 s"):
        run(tmp_path, timeout_s=0.2)

    assert docker.read_text().splitlines()[-1] == "rm -f cid123"


@pytest.mark.parametrize("mode", ["no_output", "header_only", "no_trip_id"])
def test_no_shape_file_or_no_shape_row_is_no_bus_shape(
    tmp_path: Path, docker: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("MODE", mode)

    with pytest.raises(BusShapeMatchingFailed) as error:
        run(tmp_path)

    assert error.value.reason == NO_BUS_SHAPE_REASON


def test_a_timeout_copying_the_output_out_names_the_timeout(
    tmp_path: Path, docker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODE", "copy_hang")

    with pytest.raises(BusShapeMatchingFailed, match=r"timed out after 0\.2 s"):
        run(tmp_path, timeout_s=0.2)

    assert docker.read_text().splitlines()[-1] == "rm -f cid123"
