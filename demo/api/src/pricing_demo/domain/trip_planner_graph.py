"""The trip planner's graph: the service window it is built for and what it was built from."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from pricing_demo.domain.city_datasets import GtfsSnapshot


@dataclass(frozen=True)
class ServiceWindow:
    """The first and last day OpenTripPlanner keeps services for."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(
                f"The service window ends ({self.end}) before it starts ({self.start})."
            )

    @classmethod
    def of(cls, gtfs: GtfsSnapshot) -> "ServiceWindow":
        return cls(gtfs.valid_from, gtfs.valid_to)

    def build_config(self) -> dict[str, str]:
        return {
            "transitServiceStart": self.start.isoformat(),
            "transitServiceEnd": self.end.isoformat(),
        }


@dataclass(frozen=True)
class GraphManifest:
    """What a graph was built from; written next to it after a successful build."""

    otp_image: str
    dataset_id: str
    gtfs_sha256: str
    osm_file: str
    osm_sha256: str
    build_config: Mapping[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "otp_image": self.otp_image,
            "dataset_id": self.dataset_id,
            "gtfs_sha256": self.gtfs_sha256,
            "osm_file": self.osm_file,
            "osm_sha256": self.osm_sha256,
            "build_config": dict(self.build_config),
        }


@dataclass(frozen=True)
class GraphFingerprint:
    """The manifest and the hash of `graph.obj` the worker reports; null when unknown."""

    manifest: Mapping[str, object] | None
    graph_sha256: str | None

    def details(self) -> dict[str, object]:
        return {"graph_manifest": self.manifest, "graph_sha256": self.graph_sha256}


def timetable_matches(manifest: Mapping[str, object], gtfs: GtfsSnapshot) -> bool:
    """True when the graph was built from the data set's own timetable (its copy's hash)."""
    return manifest.get("gtfs_sha256") == gtfs.sha256
