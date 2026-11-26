from datetime import date

import pytest

from pricing_demo.domain.city_datasets import GtfsSnapshot
from pricing_demo.domain.trip_planner_graph import GraphFingerprint, GraphManifest, ServiceWindow


def snapshot(valid_from: date, valid_to: date) -> GtfsSnapshot:
    return GtfsSnapshot("f.zip", "a", "b", valid_from, valid_to, "Europe/Zurich")


def test_the_build_config_is_the_validity_of_the_feed() -> None:
    window = ServiceWindow.of(snapshot(date(2024, 12, 15), date(2025, 12, 13)))

    assert window.build_config() == {
        "transitServiceStart": "2024-12-15",
        "transitServiceEnd": "2025-12-13",
    }


def test_a_one_day_feed_is_a_window() -> None:
    day = date(2025, 3, 10)

    assert ServiceWindow.of(snapshot(day, day)).build_config()["transitServiceEnd"] == "2025-03-10"


def test_an_end_before_the_start_is_refused() -> None:
    with pytest.raises(ValueError, match="before"):
        ServiceWindow(date(2025, 1, 2), date(2025, 1, 1))


def test_the_manifest_json_has_the_documented_keys() -> None:
    manifest = GraphManifest(
        otp_image="img:1",
        dataset_id="geneva-2026-11-26",
        gtfs_sha256="g",
        osm_file="geneva.osm.pbf",
        osm_sha256="o",
        build_config={"transitServiceStart": "2024-12-15", "transitServiceEnd": "2025-12-13"},
    )

    assert manifest.to_json() == {
        "otp_image": "img:1",
        "dataset_id": "geneva-2026-11-26",
        "gtfs_sha256": "g",
        "osm_file": "geneva.osm.pbf",
        "osm_sha256": "o",
        "build_config": {"transitServiceStart": "2024-12-15", "transitServiceEnd": "2025-12-13"},
    }


def test_the_fingerprint_details_hold_the_manifest_and_the_hash() -> None:
    assert GraphFingerprint({"a": 1}, "h").details() == {
        "graph_manifest": {"a": 1},
        "graph_sha256": "h",
    }


def test_the_details_without_a_manifest_are_null() -> None:
    assert GraphFingerprint(None, None).details() == {
        "graph_manifest": None,
        "graph_sha256": None,
    }
