from pathlib import Path

import pytest

from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.trip_quotes import HubPairNotFound, UnknownPeriodKey
from tests.support.results import ResultRig

VERSION = "geneva-3km.v1"


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_a_pair_has_its_options_with_legs_line_kinds_and_geometry(rig: ResultRig) -> None:
    found = rig.route_options.execute(VERSION, None, "H1", "H3")

    assert found.bus_shapes is True
    assert sorted(option.mode for option in found.items) == ["car", "pt_bike", "pt_only"]
    bike = next(option for option in found.items if option.mode == "pt_bike")
    assert [leg.mode for leg in bike.legs] == ["BICYCLE", "BUS"]
    assert [leg.line_kind for leg in bike.legs] == ["street_path", "timetable_shape"]
    assert (bike.bike_legs.value, bike.transfers.value) == (1, 1)
    assert bike.duration_s.source == "trip_planner"
    # The fake geometry is `[lat, lon]` pairs of the two hubs; GeoJSON positions are `[lon, lat]`.
    geometry = bike.legs[0].geometry
    assert geometry is not None
    assert geometry["type"] == "LineString"
    lon, lat = geometry["coordinates"][0]  # type: ignore[index]
    assert 6.0 < lon < 6.3
    assert 46.0 < lat < 46.4


def test_a_tram_leg_without_a_shape_is_a_straight_line(rig: ResultRig) -> None:
    kinds = {
        leg.line_kind
        for pair in (("H1", "H2"), ("H1", "H3"), ("H1", "H4"), ("H2", "H1"))
        for option in rig.route_options.execute(VERSION, None, *pair).items
        for leg in option.legs
    }

    assert {"street_path", "timetable_shape", "straight_line"} <= kinds


def test_a_period_key_of_the_version_is_accepted(rig: ResultRig) -> None:
    assert rig.route_options.execute(VERSION, "mon-08", "H1", "H3").items


def test_a_period_key_the_version_does_not_have_is_refused(rig: ResultRig) -> None:
    with pytest.raises(UnknownPeriodKey):
        rig.route_options.execute(VERSION, "tue-17", "H1", "H3")


def test_an_unknown_instance_version_is_refused(rig: ResultRig) -> None:
    with pytest.raises(InstanceVersionNotFound):
        rig.route_options.execute("nope.v1", None, "H1", "H3")


def test_a_pair_that_is_not_in_the_instance_is_refused(rig: ResultRig) -> None:
    with pytest.raises(HubPairNotFound):
        rig.route_options.execute(VERSION, None, "H3", "H4")
