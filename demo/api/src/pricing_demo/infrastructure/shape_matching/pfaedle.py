"""pfaedle in Docker: draws the bus trips of a GTFS feed on the streets of an OSM extract.

The files go in and out with `docker cp`, not a bind mount, so the matcher works whatever
filesystem the Docker daemon sees (a remote or a virtual-machine daemon cannot read the
host's temporary folders). Only `shapes.txt` and the trips' `shape_id` leave the container:
everything else pfaedle writes (it adds `shape_dist_traveled` to `stop_times.txt`) is dropped.
"""

import contextlib
import csv
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path

from pricing_demo.application.errors import BusShapeMatchingFailed
from pricing_demo.application.ports.bus_shape_matcher import MatchedShapes
from pricing_demo.domain.city_datasets import NO_BUS_SHAPE_REASON

WORK = "/tmp/work"
OSM_NAME = "streets.osm.pbf"


class DockerPfaedleMatcher:
    def __init__(self, image: str, timeout_s: float = 3600) -> None:
        self._image = image
        self._timeout_s = timeout_s

    @property
    def image(self) -> str:
        return self._image

    def match(self, gtfs_zip: Path, osm_file: Path) -> MatchedShapes:
        with tempfile.TemporaryDirectory(prefix="pfaedle-") as folder:
            stage = Path(folder) / "stage"
            (stage / "in").mkdir(parents=True)
            with zipfile.ZipFile(gtfs_zip) as archive:
                archive.extractall(stage / "in")
            out = Path(folder) / "out"
            container = self._docker(
                "create",
                self._image,
                "-x",
                f"{WORK}/{OSM_NAME}",
                "-m",
                "bus",
                "-D",
                "-o",
                f"{WORK}/out",
                f"{WORK}/in",
            ).strip()
            try:
                self._docker("cp", str(stage), f"{container}:{WORK}")
                self._docker("cp", str(osm_file), f"{container}:{WORK}/{OSM_NAME}")
                self._start(container)
                try:
                    copied = subprocess.run(
                        ["docker", "cp", f"{container}:{WORK}/out", str(out)],
                        capture_output=True,
                        timeout=self._timeout_s,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    raise BusShapeMatchingFailed(self._timeout_reason()) from None
            finally:
                self._remove(container)
            if copied.returncode != 0:
                raise BusShapeMatchingFailed(NO_BUS_SHAPE_REASON)
            return _read_output(out)

    def _remove(self, container: str) -> None:
        # Best effort: a container left behind must not replace the reason the match ended with.
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["docker", "rm", "-f", container],
                capture_output=True,
                timeout=self._timeout_s,
                check=False,
            )

    def _docker(self, *arguments: str) -> str:
        try:
            done = subprocess.run(
                ["docker", *arguments],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except FileNotFoundError as error:
            raise BusShapeMatchingFailed(f"Docker is not available: {error}") from error
        except subprocess.TimeoutExpired:
            raise BusShapeMatchingFailed(self._timeout_reason()) from None
        if done.returncode != 0:
            raise BusShapeMatchingFailed(f"docker {arguments[0]} failed: {_last_line(done.stderr)}")
        return done.stdout

    def _start(self, container: str) -> None:
        try:
            done = subprocess.run(
                ["docker", "start", "--attach", container],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise BusShapeMatchingFailed(self._timeout_reason()) from None
        if done.returncode != 0:
            raise BusShapeMatchingFailed(
                f"pfaedle exited with code {done.returncode}: {_last_line(done.stderr)}"
            )

    def _timeout_reason(self) -> str:
        return f"pfaedle timed out after {self._timeout_s:g} s"


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "no message"


def _read_output(out: Path) -> MatchedShapes:
    shapes_file, trips_file = out / "shapes.txt", out / "trips.txt"
    if not shapes_file.is_file() or not trips_file.is_file():
        raise BusShapeMatchingFailed(NO_BUS_SHAPE_REASON)
    shapes_txt = shapes_file.read_bytes()
    try:
        shapes = csv.DictReader(io.StringIO(shapes_txt.decode("utf-8-sig")))
        reader = csv.DictReader(io.StringIO(trips_file.read_text("utf-8-sig")))
    except UnicodeDecodeError as error:
        raise BusShapeMatchingFailed(f"pfaedle wrote a file that is not UTF-8: {error}") from None
    # Output without the columns the copy is written from is no shape, not a failed import.
    if "shape_id" not in (shapes.fieldnames or []) or not {"trip_id", "shape_id"} <= set(
        reader.fieldnames or []
    ):
        raise BusShapeMatchingFailed(NO_BUS_SHAPE_REASON)
    has_row = any(shapes)
    trip_shapes = {
        row["trip_id"]: row["shape_id"].strip()
        for row in reader
        if (row.get("shape_id") or "").strip()
    }
    if not has_row or not trip_shapes:
        raise BusShapeMatchingFailed(NO_BUS_SHAPE_REASON)
    return MatchedShapes(shapes_txt, trip_shapes)
