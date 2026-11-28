import json
from pathlib import Path

import pytest

from pricing_demo.application.errors import StreetExtractNotFound
from pricing_demo.domain.trip_planner_graph import GraphManifest
from pricing_demo.infrastructure.trip_planner.graph_folder import LocalGraphFolder
from tests.support.city_data import osm_folder, zip_gtfs


def test_another_gtfs_zip_is_found_and_gtfs_zip_is_not(tmp_path: Path) -> None:
    for name in ("gtfs.zip", "tpg_gtfs.zip", "a_gtfs_b.zip", "other.zip", "gtfs.txt"):
        (tmp_path / name).write_bytes(b"x")

    assert LocalGraphFolder(tmp_path).other_gtfs_zips() == ["a_gtfs_b.zip", "tpg_gtfs.zip"]


def test_a_missing_folder_has_no_other_timetable(tmp_path: Path) -> None:
    assert LocalGraphFolder(tmp_path / "none").other_gtfs_zips() == []


def test_the_timetable_is_copied_byte_for_byte_to_gtfs_zip(tmp_path: Path) -> None:
    source = zip_gtfs(tmp_path / "src" / "tpg_gtfs.zip")
    folder = LocalGraphFolder(tmp_path / "graph")

    target = folder.put_gtfs(source)

    assert target == tmp_path / "graph" / "gtfs.zip"
    assert target.read_bytes() == source.read_bytes()


def test_the_one_street_extract_is_found_and_none_or_two_are_refused(tmp_path: Path) -> None:
    graph = osm_folder(tmp_path / "graph")
    assert LocalGraphFolder(graph).osm_file() == graph / "geneva.osm.pbf"

    osm_folder(graph, ("a.osm.pbf", "b.osm.pbf"))
    with pytest.raises(StreetExtractNotFound):
        LocalGraphFolder(graph).osm_file()
    with pytest.raises(StreetExtractNotFound):
        LocalGraphFolder(tmp_path / "empty").osm_file()


def test_the_build_config_and_the_manifest_are_written_as_sorted_json(tmp_path: Path) -> None:
    folder = LocalGraphFolder(tmp_path)
    folder.write_build_config({"transitServiceStart": "2024-12-15", "transitServiceEnd": "x"})
    manifest = GraphManifest("img", "d", "g", "o.osm.pbf", "o", {"a": "b"})

    path = folder.write_manifest(manifest)

    assert path == tmp_path / "graph-manifest.json"
    assert json.loads(path.read_text()) == manifest.to_json()
    assert path.read_text().endswith("}\n")
    assert json.loads((tmp_path / "build-config.json").read_text())["transitServiceEnd"] == "x"


def test_removing_a_missing_manifest_is_fine_and_removes_an_existing_one(tmp_path: Path) -> None:
    folder = LocalGraphFolder(tmp_path)
    folder.remove_manifest()
    (tmp_path / "graph-manifest.json").write_text("{}")

    folder.remove_manifest()

    assert not (tmp_path / "graph-manifest.json").exists()


def test_the_sha256_of_a_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_bytes(b"abc")

    assert LocalGraphFolder(tmp_path).sha256(tmp_path / "f") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_another_gtfs_zip_is_found_whatever_the_case_of_its_name(tmp_path: Path) -> None:
    (tmp_path / "TPG_GTFS.ZIP").write_bytes(b"x")

    assert LocalGraphFolder(tmp_path).other_gtfs_zips() == ["TPG_GTFS.ZIP"]


def test_a_rewritten_manifest_leaves_no_partial_file(tmp_path: Path) -> None:
    folder = LocalGraphFolder(tmp_path)
    folder.write_manifest(GraphManifest("img", "d", "g", "o.osm.pbf", "o", {}))
    folder.write_manifest(GraphManifest("img", "e", "g", "o.osm.pbf", "o", {}))

    assert sorted(path.name for path in tmp_path.iterdir()) == ["graph-manifest.json"]
    assert json.loads((tmp_path / "graph-manifest.json").read_text())["dataset_id"] == "e"
