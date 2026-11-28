import threading
from pathlib import Path

import pytest

from pricing_demo.application.errors import VersionNotBuilt
from pricing_demo.application.use_cases.verify_build import VerifyBuild
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.scratch_builds import FakeScratchBuilds
from tests.support.builds import SLUG, MemoryBuilds, build_fake_city

VERSION = f"{SLUG}.v1"
FAILURES = [
    {
        "origin_hub": "H1",
        "destination_hub": "H4",
        "query": "pt_bike",
        "kind": "no_route",
        "message": "no path",
    }
]


class Rig:
    def __init__(self, tmp_path: Path, stored_failures: list[dict[str, str]] | None = None) -> None:
        self.tmp_path = tmp_path
        self.builds = MemoryBuilds()
        self.builds.add_draft()
        self.run_id = build_fake_city(self.builds, tmp_path, stored_failures or [])
        self.settings = InMemoryFakeSettings()
        self.scratch = FakeScratchBuilds(tmp_path)
        self.use_case = VerifyBuild(
            self.builds.instances,
            self.builds.datasets,
            self.builds.artifacts,
            LocalArtifactStore(tmp_path),
            self.builds.route_failures,
            FakeCityPreparation(self.settings, self.builds.waiter),
            self.scratch,
        )

    def snapshot(self) -> tuple[object, ...]:
        artifacts = self.builds.artifacts
        links = artifacts.links_of(VERSION)
        return (
            dict(links),
            [artifacts.get(key) for key in links.values()],
            self.builds.route_failures.of_run(self.run_id),
        )

    def folders(self) -> list[Path]:
        verify = self.tmp_path / "verify"
        return list(verify.iterdir()) if verify.exists() else []


def test_a_version_built_by_the_fake_verifies_as_a_match(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    result = rig.use_case.execute(VERSION, threading.Event())

    assert result.failure is None
    assert result.comparison is not None
    assert result.comparison.matches
    assert len(rig.scratch.removed) == 1
    assert rig.folders() == []


def test_a_build_with_route_failures_is_compared_by_pairs_and_matches(tmp_path: Path) -> None:
    rig = Rig(tmp_path, FAILURES)
    rig.settings.set_pricing_model({"route_failures": FAILURES})

    result = rig.use_case.execute(VERSION, threading.Event())

    assert result.comparison is not None
    assert result.comparison.matches
    assert result.comparison.steps[2].by_pairs


def test_a_failure_only_in_the_rebuild_leaves_the_pair_out_of_the_comparison(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path)
    rig.settings.set_pricing_model({"route_failures": FAILURES})

    result = rig.use_case.execute(VERSION, threading.Event())

    assert result.comparison is not None
    routes = result.comparison.steps[2]
    assert routes.by_pairs
    assert routes.matches  # the options of the pairs both builds have are equal
    assert list(routes.only_in) == [(("H1", "H4"), "stored")]
    # The fake draws the demands in one sequence: a pair left out shifts the later ones.
    assert result.comparison.steps[3].by_pairs
    assert result.comparison.steps[3].only_in == routes.only_in


def test_an_unknown_version_is_refused(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    with pytest.raises(InstanceVersionNotFound):
        rig.use_case.execute("nope.v1", threading.Event())

    assert rig.folders() == []


def test_a_version_whose_steps_are_not_all_linked_is_refused(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.builds.artifacts.drop_links(VERSION)

    with pytest.raises(VersionNotBuilt):
        rig.use_case.execute(VERSION, threading.Event())

    assert rig.folders() == []


def test_a_step_that_fails_in_the_rebuild_is_reported_with_its_code(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "hubs", "code": "trip_planner_unreachable"}}
    )
    before = rig.snapshot()

    result = rig.use_case.execute(VERSION, threading.Event())

    assert result.comparison is None
    assert result.failure is not None
    assert result.failure[:2] == (StepName.HUBS, "trip_planner_unreachable")
    assert result.failure[2]
    assert len(rig.scratch.removed) == 1
    assert rig.folders() == []
    assert rig.snapshot() == before


def test_a_stopped_rebuild_is_a_failure_and_leaves_no_folder(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    stop = threading.Event()
    stop.set()

    result = rig.use_case.execute(VERSION, stop)

    assert result.failure is not None
    assert result.failure[0] is StepName.AREA
    assert rig.folders() == []


def test_the_rebuild_does_not_change_what_is_stored(tmp_path: Path) -> None:
    rig = Rig(tmp_path, FAILURES)
    before = rig.snapshot()

    rig.use_case.execute(VERSION, threading.Event())

    assert rig.snapshot() == before
    assert not (tmp_path / "runs" / f"verify-{rig.scratch.removed[0].name}").exists()
