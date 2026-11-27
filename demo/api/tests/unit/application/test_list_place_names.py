from pathlib import Path

import pytest

from pricing_demo.domain.city_instances import InstanceVersionNotFound, first_period
from tests.support.results import ResultRig

VERSION = "geneva-3km.v1"


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_a_typed_name_finds_the_stops_of_the_hub_whatever_its_case(rig: ResultRig) -> None:
    lines = rig.place_names.execute(VERSION, "FAKE STOP h1")

    assert [line.name for line in lines] == [f"Fake stop H1-{n}" for n in range(1, 6)]
    assert {(line.kind, line.hub_id) for line in lines} == {("stop", "H1")}


def test_a_bike_station_is_a_line_of_its_own_kind(rig: ResultRig) -> None:
    lines = rig.place_names.execute(VERSION, "bikes h3")

    assert [(line.name, line.kind, line.hub_id) for line in lines] == [
        ("Fake bikes H3-1", "bike_station", "H3"),
        ("Fake bikes H3-2", "bike_station", "H3"),
    ]


def test_at_most_ten_lines_are_returned(rig: ResultRig) -> None:
    assert len(rig.place_names.execute(VERSION, "fake")) == 10


def test_a_query_under_two_characters_returns_no_line(rig: ResultRig) -> None:
    assert rig.place_names.execute(VERSION, "f") == []


def test_an_unknown_instance_version_is_refused(rig: ResultRig) -> None:
    with pytest.raises(InstanceVersionNotFound):
        rig.place_names.execute("nope.v1", "fake")


def test_an_instance_version_that_is_not_built_has_no_line(rig: ResultRig) -> None:
    instances = rig.rig.instances
    version = instances.get_version(VERSION)
    dataset = rig.rig.datasets.get("geneva-2026-11-26")
    assert version is not None
    assert dataset is not None
    instances.create_draft(
        "geneva-3km",
        VERSION,
        version.parameters,
        rig.rig.clock.now(),
        lambda draft: first_period(draft, dataset),
    )

    assert rig.place_names.execute("geneva-3km.v2", "fake") == []
