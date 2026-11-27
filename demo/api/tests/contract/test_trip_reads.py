"""The TripReads port: one suite, run against the fake and the PostgreSQL adapter, each over a
built fake city whose routes step had two failed queries."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from pricing_demo.application.ports.trip_reads import TripReads
from pricing_demo.infrastructure.fakes.trip_reads import InMemoryTripReads
from tests.integration.test_builds import Rig, rig  # noqa: F401
from tests.support.builds import SLUG, MemoryBuilds, build_fake_city

VERSION = f"{SLUG}.v1"
PERIOD = f"{VERSION}.mon-08"
FAILURES = [
    {
        "origin_hub": "H1",
        "destination_hub": "H6",
        "query": "pt_bike",
        "kind": "no_route",
        "message": "no public transport",
    },
    {
        "origin_hub": "H2",
        "destination_hub": "H3",
        "query": "car",
        "kind": "technical",
        "message": "timeout",
    },
]


@dataclass
class Built:
    reads: TripReads
    # The id of a version that was never created.
    unbuilt: str


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def built(request: pytest.FixtureRequest, tmp_path: Path) -> Built:
    if request.param == "fake":
        rig = MemoryBuilds()
        rig.add_draft()
        build_fake_city(rig, tmp_path, FAILURES)
        return Built(
            InMemoryTripReads(
                rig.instances, rig.datasets, rig.artifacts, rig.read_model, rig.route_failures
            ),
            f"{SLUG}.v9",
        )
    from pricing_demo.infrastructure.persistence.trip_reads import PostgresTripReads

    rig_postgres: Rig = request.getfixturevalue("rig")
    rig_postgres.settings.set_pricing_model({"route_failures": FAILURES})
    version = rig_postgres.draft()
    rig_postgres.build.execute(version)
    rig_postgres.process.execute()
    return Built(PostgresTripReads(rig_postgres.engine), f"{SLUG}.v9")


def test_an_unknown_or_unbuilt_instance_version_has_no_area(built: Built) -> None:
    assert built.reads.area("nope.v1") is None
    assert built.reads.area(built.unbuilt) is None


def test_the_area_of_a_built_version_holds_its_circle_hubs_stations_and_pairs(
    built: Built,
) -> None:
    area = built.reads.area(VERSION)

    assert area is not None
    assert area.radius_m == 3000
    assert area.min_od_distance_m == 900
    assert area.period_ids == {"mon-08": PERIOD}
    assert [hub.hub_id for hub in area.hubs] == ["H1", "H2", "H3", "H4", "H5", "H6"]
    assert len(area.stations) == 42
    assert area.bus_shapes is True
    assert len(area.hub_pairs) == 23
    assert ("H1", "H6") not in area.hub_pairs
    assert ("H1", "H2") in area.hub_pairs


def test_every_station_of_the_area_belongs_to_the_hub_that_lists_it(built: Built) -> None:
    area = built.reads.area(VERSION)

    assert area is not None
    assert len(area.station_hubs) == 42
    assert area.station_hubs["pts_FAKEH30"] == "H3"
    assert area.station_hubs["bss_fake_H4_1"] == "H4"


def test_the_options_of_a_pair_come_by_arc_id(built: Built) -> None:
    options = built.reads.pair_options(VERSION, "H1", "H3")

    assert sorted(option.mode for option in options) == ["car", "pt_bike", "pt_only"]
    assert [option.arc_id for option in options] == sorted(option.arc_id for option in options)
    assert {(option.origin_hub, option.destination_hub) for option in options} == {("H1", "H3")}


def test_a_pair_without_options_and_an_unbuilt_version_have_none(built: Built) -> None:
    assert built.reads.pair_options(VERSION, "H3", "H4") == []
    assert built.reads.pair_options(VERSION, "H1", "H6") == []
    assert built.reads.pair_options(built.unbuilt, "H1", "H3") == []


def test_the_failures_of_a_pair_are_those_of_the_routes_run(built: Built) -> None:
    found = built.reads.pair_failures(VERSION, "H1", "H6")

    assert [(item.query, item.kind) for item in found] == [("pt_bike", "no_route")]
    assert [item.query for item in built.reads.pair_failures(VERSION, "H2", "H3")] == ["car"]
    assert built.reads.pair_failures(VERSION, "H1", "H3") == []


def test_the_failures_of_another_version_are_not_returned(built: Built) -> None:
    assert built.reads.pair_failures(built.unbuilt, "H1", "H6") == []
