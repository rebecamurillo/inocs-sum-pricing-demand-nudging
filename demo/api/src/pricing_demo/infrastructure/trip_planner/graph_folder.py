import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from pricing_demo.domain.trip_planner_graph import GraphManifest
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract

GTFS_NAME = "gtfs.zip"
BUILD_CONFIG_NAME = "build-config.json"
MANIFEST_NAME = "graph-manifest.json"


class LocalGraphFolder:
    """`otp/data/`: the inputs OpenTripPlanner reads and the graph and manifest it leaves."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def other_gtfs_zips(self) -> list[str]:
        if not self._path.is_dir():
            return []
        # OpenTripPlanner takes any file whose name holds "gtfs", in any case, as a timetable.
        return sorted(
            item.name
            for item in self._path.iterdir()
            if "gtfs" in item.name.lower()
            and item.name.lower().endswith(".zip")
            and item.name != GTFS_NAME
        )

    def osm_file(self) -> Path:
        return PbfStreetExtract().file(self._path)

    def put_gtfs(self, source: Path) -> Path:
        self._path.mkdir(parents=True, exist_ok=True)
        target = self._path / GTFS_NAME
        shutil.copyfile(source, target)
        return target

    def write_build_config(self, config: Mapping[str, str]) -> None:
        self._write_json(self._path / BUILD_CONFIG_NAME, dict(config))

    def remove_manifest(self) -> None:
        (self._path / MANIFEST_NAME).unlink(missing_ok=True)

    def write_manifest(self, manifest: GraphManifest) -> Path:
        return self._write_json(self._path / MANIFEST_NAME, manifest.to_json())

    def sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_json(self, path: Path, content: object) -> Path:
        self._path.mkdir(parents=True, exist_ok=True)
        # Written next to the target, then renamed over it: a reader never sees half a file.
        partial = path.with_name(f".{path.name}.partial")
        partial.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(partial, path)
        return path
