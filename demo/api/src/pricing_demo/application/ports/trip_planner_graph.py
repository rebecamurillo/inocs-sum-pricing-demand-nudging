from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from pricing_demo.domain.trip_planner_graph import GraphFingerprint, GraphManifest


class GraphFolder(Protocol):
    """The folder OpenTripPlanner builds its graph from and into."""

    def other_gtfs_zips(self) -> Sequence[str]:
        """Every `*gtfs*.zip` in the folder except `gtfs.zip`, sorted."""
        ...

    def osm_file(self) -> Path:
        """The one `.osm.pbf`; raises StreetExtractNotFound unless there is exactly one."""
        ...

    def put_gtfs(self, source: Path) -> Path:
        """Copy `source` to `gtfs.zip`; returns its path."""
        ...

    def write_build_config(self, config: Mapping[str, str]) -> None: ...

    def remove_manifest(self) -> None: ...

    def write_manifest(self, manifest: GraphManifest) -> Path: ...

    def sha256(self, path: Path) -> str: ...


class GraphBuilder(Protocol):
    @property
    def image(self) -> str:
        """The OpenTripPlanner image the graph is built with."""
        ...

    def build(self) -> None:
        """Build the graph in the folder. Raises GraphBuildFailed."""
        ...


class GraphFingerprints(Protocol):
    def read(self) -> GraphFingerprint:
        """The manifest and the hash of `graph.obj`; never raises (unknown gives nulls)."""
        ...
