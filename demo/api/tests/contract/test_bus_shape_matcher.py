"""The BusShapeMatcher port: one suite, run against the fake and the pfaedle Docker adapter."""

import csv
import io
from pathlib import Path

import pytest

from pricing_demo.application.ports.bus_shape_matcher import BusShapeMatcher
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
from tests.support.city_data import TINY_PBF, zip_gtfs


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("pfaedle", id="pfaedle", marks=pytest.mark.integration),
    ]
)
def matcher(request: pytest.FixtureRequest) -> BusShapeMatcher:
    if request.param == "fake":
        return FakeBusShapeMatcher()
    from pricing_demo.infrastructure.config.settings import DEFAULT_SHAPE_TOOL_IMAGE
    from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher

    return DockerPfaedleMatcher(DEFAULT_SHAPE_TOOL_IMAGE)


def test_the_bus_trip_gets_a_shape_and_the_tram_trip_none(
    matcher: BusShapeMatcher, tmp_path: Path
) -> None:
    result = matcher.match(zip_gtfs(tmp_path / "feed.zip"), TINY_PBF)

    assert "T1" in result.trip_shapes
    assert "T2" not in result.trip_shapes
    rows = list(csv.DictReader(io.StringIO(result.shapes_txt.decode("utf-8"))))
    assert {"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"} <= set(rows[0])
    assert result.trip_shapes["T1"] in {row["shape_id"] for row in rows}


def test_the_matcher_names_the_tool_it_runs(matcher: BusShapeMatcher) -> None:
    assert matcher.image
