import hashlib
import json
import os
from pathlib import Path

import pytest

from pricing_demo.infrastructure.trip_planner import graph_fingerprints
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def with_manifest(folder: Path) -> FileGraphFingerprints:
    (folder / "graph-manifest.json").write_text("{}")
    return FileGraphFingerprints(folder)


def test_without_a_manifest_both_values_are_null(tmp_path: Path) -> None:
    (tmp_path / "graph.obj").write_bytes(b"graph")

    assert FileGraphFingerprints(tmp_path).read().details() == {
        "graph_manifest": None,
        "graph_sha256": None,
    }


def test_the_manifest_and_the_graph_hash_are_read(tmp_path: Path) -> None:
    (tmp_path / "graph-manifest.json").write_text(json.dumps({"dataset_id": "d"}))
    (tmp_path / "graph.obj").write_bytes(b"graph")

    assert FileGraphFingerprints(tmp_path).read().details() == {
        "graph_manifest": {"dataset_id": "d"},
        "graph_sha256": sha(b"graph"),
    }


def test_a_manifest_without_a_graph_has_a_null_hash(tmp_path: Path) -> None:
    (tmp_path / "graph-manifest.json").write_text("{}")

    assert FileGraphFingerprints(tmp_path).read().details() == {
        "graph_manifest": {},
        "graph_sha256": None,
    }


def test_the_hash_is_not_recomputed_while_size_and_mtime_are_unchanged(tmp_path: Path) -> None:
    graph = tmp_path / "graph.obj"
    graph.write_bytes(b"aaaa")
    fingerprints = with_manifest(tmp_path)
    first = fingerprints.read().graph_sha256
    stat = graph.stat()

    graph.write_bytes(b"bbbb")
    os.utime(graph, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert fingerprints.read().graph_sha256 == first == sha(b"aaaa")


def test_the_hash_is_recomputed_when_the_mtime_or_the_size_changed(tmp_path: Path) -> None:
    graph = tmp_path / "graph.obj"
    graph.write_bytes(b"aaaa")
    fingerprints = with_manifest(tmp_path)
    fingerprints.read()
    stat = graph.stat()

    graph.write_bytes(b"bbbb")
    os.utime(graph, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert fingerprints.read().graph_sha256 == sha(b"bbbb")

    graph.write_bytes(b"cccccc")
    os.utime(graph, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert fingerprints.read().graph_sha256 == sha(b"cccccc")


def test_an_unchanged_graph_is_hashed_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "graph.obj").write_bytes(b"graph")
    calls: list[Path] = []
    real = graph_fingerprints.hash_file

    def spy(path: Path) -> str:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(graph_fingerprints, "hash_file", spy)
    fingerprints = with_manifest(tmp_path)

    fingerprints.read()
    fingerprints.read()

    assert len(calls) == 1


def test_an_unreadable_manifest_gives_nulls_and_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "graph-manifest.json").write_text("{not json")
    (tmp_path / "graph.obj").write_bytes(b"graph")

    with caplog.at_level("WARNING"):
        result = FileGraphFingerprints(tmp_path).read()

    assert result.details() == {"graph_manifest": None, "graph_sha256": None}
    assert "graph-manifest.json" in caplog.text


def test_a_manifest_that_is_not_an_object_is_unreadable(tmp_path: Path) -> None:
    (tmp_path / "graph-manifest.json").write_text("[1]")

    assert FileGraphFingerprints(tmp_path).read().manifest is None
