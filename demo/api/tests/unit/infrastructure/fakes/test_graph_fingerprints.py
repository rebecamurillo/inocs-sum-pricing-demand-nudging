import json
from pathlib import Path

from pricing_demo.infrastructure.fakes.graph_fingerprints import (
    FAKE_GRAPH_MANIFEST,
    FakeGraphFingerprints,
)
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints
from pricing_demo.infrastructure.worker_build_sources import WorkerBuildSources


def test_without_a_graph_the_fake_reports_a_fixed_manifest(tmp_path: Path) -> None:
    found = FakeGraphFingerprints(tmp_path).read()

    assert found.manifest == FAKE_GRAPH_MANIFEST
    assert found.graph_sha256 == "0" * 64


def test_a_graph_that_was_built_is_reported_as_it_is(tmp_path: Path) -> None:
    (tmp_path / "graph-manifest.json").write_text(json.dumps({"dataset_id": "d"}))
    (tmp_path / "graph.obj").write_bytes(b"graph")

    found = FakeGraphFingerprints(tmp_path).read()

    assert found.manifest == {"dataset_id": "d"}
    assert found.graph_sha256 != "0" * 64


def test_the_worker_sources_are_the_fingerprint_it_has_read_and_the_graph_manifest(
    tmp_path: Path,
) -> None:
    sources = WorkerBuildSources(lambda: "abc", FakeGraphFingerprints(tmp_path))

    assert sources.package_fingerprint() == "abc"
    assert sources.graph_manifest() == FAKE_GRAPH_MANIFEST


def test_the_worker_sources_know_no_manifest_when_the_graph_has_none(tmp_path: Path) -> None:
    sources = WorkerBuildSources(lambda: None, FileGraphFingerprints(tmp_path))

    assert sources.package_fingerprint() is None
    assert sources.graph_manifest() is None
