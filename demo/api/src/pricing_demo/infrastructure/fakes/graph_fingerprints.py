from pricing_demo.domain.trip_planner_graph import GraphFingerprint
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints

# What the fake worker reports when no graph was built in the folder, so a fake build always
# has a manifest and every routes key exists.
FAKE_GRAPH_MANIFEST: dict[str, object] = {
    "otp_image": "fake/opentripplanner:0",
    "dataset_id": "fake",
    "gtfs_sha256": "0" * 64,
    "osm_file": "fake.osm.pbf",
    "osm_sha256": "0" * 64,
    "build_config": {},
}
FAKE_GRAPH_SHA256 = "0" * 64


class FakeGraphFingerprints(FileGraphFingerprints):
    """The graph folder's manifest when there is one, else a fixed fake manifest."""

    def read(self) -> GraphFingerprint:
        found = super().read()
        if found.manifest is not None:
            return found
        return GraphFingerprint(FAKE_GRAPH_MANIFEST, FAKE_GRAPH_SHA256)
