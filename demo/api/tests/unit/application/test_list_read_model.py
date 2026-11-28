from pathlib import Path

import pytest

from pricing_demo.application.use_cases.list_hub_pairs import ListHubPairs
from pricing_demo.application.use_cases.list_hubs import ListHubs
from pricing_demo.application.use_cases.list_route_failures import ListRouteFailures
from pricing_demo.application.use_cases.list_route_pairs import ListRoutePairs
from pricing_demo.application.use_cases.list_stations import ListStations
from pricing_demo.domain.city_instances import InstanceVersionNotFound, PeriodNotFound
from pricing_demo.domain.runs import RunNotFound
from tests.support.builds import MemoryBuilds, build_fake_city

PERIOD = "geneva-3km.v1.mon-08"
FAILURE = {
    "origin_hub": "H1",
    "destination_hub": "H2",
    "query": "car",
    "kind": "no_route",
    "message": "no car route",
}


class Rig:
    def __init__(self) -> None:
        self.builds = MemoryBuilds()
        self.builds.add_draft()
        args = (self.builds.instances, self.builds.artifacts, self.builds.read_model)
        self.stations = ListStations(*args)
        self.hubs = ListHubs(*args)
        self.hub_pairs = ListHubPairs(*args)
        self.route_pairs = ListRoutePairs(*args)
        self.failures = ListRouteFailures(self.builds.runs, self.builds.route_failures)


def test_a_built_version_lists_its_stations_hubs_and_pairs(tmp_path: Path) -> None:
    rig = Rig()
    build_fake_city(rig.builds, tmp_path)

    assert len(rig.stations.execute("geneva-3km.v1")) == 42
    assert len(rig.hubs.execute("geneva-3km.v1")) == 6
    assert len(rig.hub_pairs.execute("geneva-3km.v1", None)) == 24
    assert len(rig.hub_pairs.execute("geneva-3km.v1", PERIOD)) == 24


def test_a_built_version_lists_the_pairs_its_routes_step_routed(tmp_path: Path) -> None:
    rig = Rig()
    build_fake_city(rig.builds, tmp_path)

    pairs = rig.route_pairs.execute("geneva-3km.v1")

    assert len(pairs) == 24
    assert pairs[0].origin_hub == "H1"


def test_a_version_not_built_has_no_route_pairs_and_an_unknown_one_is_not_found() -> None:
    rig = Rig()

    assert rig.route_pairs.execute("geneva-3km.v1") == []
    with pytest.raises(InstanceVersionNotFound):
        rig.route_pairs.execute("nope.v1")


def test_a_version_that_is_not_built_has_nothing_to_list() -> None:
    rig = Rig()

    assert rig.stations.execute("geneva-3km.v1") == []
    assert rig.hubs.execute("geneva-3km.v1") == []
    assert rig.hub_pairs.execute("geneva-3km.v1", None) == []


def test_an_unknown_version_is_not_found() -> None:
    rig = Rig()

    for call in (
        lambda: rig.stations.execute("nope.v1"),
        lambda: rig.hubs.execute("nope.v1"),
        lambda: rig.hub_pairs.execute("nope.v1", None),
    ):
        with pytest.raises(InstanceVersionNotFound):
            call()


def test_a_period_that_is_not_the_versions_is_refused() -> None:
    rig = Rig()

    with pytest.raises(PeriodNotFound):
        rig.hub_pairs.execute("geneva-3km.v1", "other.mon-08")


def test_the_route_failures_of_a_run_come_with_their_period(tmp_path: Path) -> None:
    rig = Rig()
    run_id = build_fake_city(rig.builds, tmp_path, [FAILURE])

    ((failure, period),) = rig.failures.execute(run_id)

    assert (failure.origin_hub, failure.query, failure.kind, failure.attempts) == (
        "H1",
        "car",
        "no_route",
        1,
    )
    assert period == PERIOD


def test_an_unknown_run_is_not_found() -> None:
    with pytest.raises(RunNotFound):
        Rig().failures.execute("run-9")


def test_a_run_without_failures_lists_none(tmp_path: Path) -> None:
    rig = Rig()
    run_id = build_fake_city(rig.builds, tmp_path)

    assert rig.failures.execute(run_id) == []
