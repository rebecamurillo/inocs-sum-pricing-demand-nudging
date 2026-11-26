"""A build end to end on PostgreSQL: the API's use case queues it, the worker's loop pieces run
it with the fake city preparation and the real artefact store on a temporary folder."""

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.ports.city_preparation import PreparationRequest, Progress
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.run_build_step import BuildStepExecutor
from pricing_demo.domain.build_plan import BUILD_STEPS, STEP_OUTPUTS
from pricing_demo.domain.builds import RunActive
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.runs import Run, RunState, StepName, StepState
from pricing_demo.domain.system_status import ComponentName, ComponentStatus
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.graph_fingerprints import (
    FAKE_GRAPH_MANIFEST,
    FakeGraphFingerprints,
)
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.ids import UuidV7Source
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.build_sources import PostgresBuildSources
from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.package_fingerprints import (
    PostgresPackageFingerprints,
)
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.infrastructure.worker_build_sources import WorkerBuildSources
from tests.support.builds import all_available
from tests.support.runs import T0, later, make_run

pytestmark = pytest.mark.integration

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
SLUG = "geneva-3km"
FINGERPRINT = FAKE_FINGERPRINT.fingerprint


class SpyPreparation:
    """The fake city preparation, recording which steps it was asked to prepare."""

    def __init__(self, inner: FakeCityPreparation) -> None:
        self._inner = inner
        self.steps: list[StepName] = []

    def prepare(
        self, request: PreparationRequest, progress: Progress, stop: StopSignal
    ) -> StepOutcome:
        self.steps.append(request.step)
        return self._inner.prepare(request, progress, stop)


@dataclass
class Rig:
    engine: Engine
    data_dir: Path
    clock: FixedClock
    instances: PostgresCityInstances
    runs: PostgresRunRepository
    artifacts: PostgresArtifacts
    settings: PostgresFakeSettings
    planning: BuildPlanning
    build: BuildInstanceVersion
    process: ProcessNextRun
    preparation: SpyPreparation

    def draft(self, number: int = 1, based_on: str | None = None) -> str:
        """The first draft of the instance, valid (the package defaults tie two distances)."""
        if number == 1:
            parameters = replace(
                parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset),
                min_od_distance_m=900.0,
            )
            version = InstanceVersion(f"{SLUG}.v1", SLUG, 1, None, "draft", parameters, T0)
            self.instances.create(
                CityInstance(SLUG, "Geneva 3 km", DATASET.id, 2, T0),
                version,
                first_period(version.id, DATASET),
            )
            return version.id
        source = self.instances.get_version(based_on or f"{SLUG}.v1")
        assert source is not None
        return self.instances.create_draft(
            SLUG, source.id, source.parameters, T0, lambda v: first_period(v, DATASET)
        ).id

    def run_of(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        assert run is not None
        return run

    def rows(self, table: str) -> list[tuple[object, ...]]:
        with self.engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table}"))]

    def working(self, run_id: str) -> list[str]:
        folder = self.data_dir / "runs" / run_id
        return sorted(item.name for item in folder.iterdir()) if folder.exists() else []


@pytest.fixture
def rig(migrated_database: Engine, tmp_path: Path) -> Rig:
    engine = migrated_database
    clock = FixedClock(T0)
    waiter = FakeWaiter(clock)
    PostgresCityDatasets(engine).add(DATASET)
    PostgresPackageFingerprints(engine).record(FAKE_FINGERPRINT, T0)
    workers = PostgresWorkerRegistry(engine)
    workers.register("w-1", "host", 1, T0, FINGERPRINT)
    PostgresComponentReports(engine).write(
        ComponentStatus.ready(ComponentName.TRIP_PLANNER),
        "w-1",
        T0,
        {"graph_manifest": FAKE_GRAPH_MANIFEST},
    )
    instances = PostgresCityInstances(engine)
    datasets = PostgresCityDatasets(engine)
    artifacts = PostgresArtifacts(engine)
    runs = PostgresRunRepository(engine)
    builds = PostgresBuilds(engine)
    planning = BuildPlanning(
        instances, datasets, artifacts, PostgresBuildSources(engine), builds, all_available
    )
    settings = PostgresFakeSettings(engine)
    preparation = SpyPreparation(FakeCityPreparation(settings, waiter))
    executor = BuildStepExecutor(
        preparation,
        LocalArtifactStore(tmp_path),
        artifacts,
        runs,
        instances,
        datasets,
        WorkerBuildSources(lambda: FINGERPRINT, FakeGraphFingerprints(tmp_path / "graph")),
        clock,
    )
    registry = StepRegistry()
    for step in BUILD_STEPS:
        registry.register(step, executor, executor)
    return Rig(
        engine,
        tmp_path,
        clock,
        instances,
        runs,
        artifacts,
        settings,
        planning,
        BuildInstanceVersion(instances, datasets, builds, planning, UuidV7Source(), clock),
        ProcessNextRun(
            runs, registry, workers, WorkerIdentity("w-1", "host", 1, T0), clock, waiter
        ),
        preparation,
    )


def test_a_build_runs_its_four_steps_and_stores_their_artefacts(rig: Rig) -> None:
    version = rig.draft()
    queued = rig.build.execute(version)

    assert rig.process.execute() is True

    run = rig.run_of(queued.id)
    assert run.state is RunState.SUCCEEDED
    assert [item.state for item in run.steps] == [StepState.DONE] * 4
    assert run.steps[0].counts == {"stops": 30, "bike_stations": 12}
    assert run.steps[3].counts["bike_stations"] == 12
    keys = [item.input_key for item in run.steps]
    assert all(keys)
    assert len(rig.rows("artifacts")) == 4
    assert rig.artifacts.links_of(version) == dict(zip(BUILD_STEPS, keys, strict=True))
    for step, key in zip(BUILD_STEPS, keys, strict=True):
        artifact = rig.artifacts.get(key or "")
        assert artifact is not None
        assert artifact.path == f"artifacts/{step.value}/{key}"
        assert [item.name for item in artifact.files] == list(STEP_OUTPUTS[step])
        for stored in artifact.files:
            content = (rig.data_dir / artifact.path / stored.name).read_bytes()
            assert (stored.sha256, stored.bytes) == (
                hashlib.sha256(content).hexdigest(),
                len(content),
            )


def test_a_successful_build_deletes_its_working_directories_and_leaves_read_only_artefacts(
    rig: Rig,
) -> None:
    queued = rig.build.execute(rig.draft())

    rig.process.execute()

    assert rig.working(queued.id) == []
    folders = sorted((rig.data_dir / "artifacts").glob("*/*"))
    assert len(folders) == 4
    assert all(folder.stat().st_mode & 0o222 == 0 for folder in folders)
    assert not list((rig.data_dir / "artifacts").glob("*/*.tmp-*"))


def test_the_next_draft_of_an_unchanged_version_keeps_every_step(rig: Rig) -> None:
    first = rig.draft()
    rig.build.execute(first)
    rig.process.execute()
    second = rig.draft(2, first)
    plan = rig.planning.plan(rig.instances.get_version(second))  # type: ignore[arg-type]
    assert [item.action for item in plan.steps] == ["kept"] * 4
    assert [item.causes for item in plan.steps] == [()] * 4
    assert all(item.last_duration_s is not None for item in plan.steps)
    rig.preparation.steps.clear()

    queued = rig.build.execute(second)
    rig.process.execute()

    run = rig.run_of(queued.id)
    assert run.state is RunState.SUCCEEDED
    assert [item.state for item in run.steps] == [StepState.KEPT] * 4
    assert rig.preparation.steps == []
    assert len(rig.rows("artifacts")) == 4
    assert len(rig.rows("instance_version_steps")) == 8
    assert rig.artifacts.links_of(second) == rig.artifacts.links_of(first)


def test_an_edit_rebuilds_only_the_steps_that_read_it(rig: Rig) -> None:
    first = rig.draft()
    rig.build.execute(first)
    rig.process.execute()
    second = rig.draft(2, first)
    rig.instances.update_draft_parameters(second, {"seed": 7})
    rig.preparation.steps.clear()

    plan = rig.planning.plan(rig.instances.get_version(second))  # type: ignore[arg-type]
    queued = rig.build.execute(second)
    rig.process.execute()

    assert [item.action for item in plan.steps] == ["kept", "kept", "kept", "rebuilt"]
    assert [cause.kind for cause in plan.steps[3].causes] == ["parameter"]
    assert plan.steps[3].causes[0].parameters == ("seed",)
    assert [item.state for item in rig.run_of(queued.id).steps] == [
        StepState.KEPT,
        StepState.KEPT,
        StepState.KEPT,
        StepState.DONE,
    ]
    assert rig.preparation.steps == [StepName.TRAVELLERS_AND_BIKES]
    assert len(rig.rows("artifacts")) == 5


def test_a_failure_at_the_routes_keeps_the_steps_done_and_the_same_post_resumes(
    rig: Rig,
) -> None:
    version = rig.draft()
    rig.settings.set_pricing_model(
        {"fail_at": {"step": "routes", "code": "trip_planner_unreachable"}}
    )
    failed = rig.build.execute(version)

    rig.process.execute()

    run = rig.run_of(failed.id)
    assert run.state is RunState.FAILED
    assert [item.state for item in run.steps] == [
        StepState.DONE,
        StepState.DONE,
        StepState.FAILED,
        StepState.PENDING,
    ]
    assert run.failure is not None
    assert (run.failure.step, run.failure.code) == ("routes", "trip_planner_unreachable")
    assert run.failure.reason == "the trip planner is not reachable at http://trip-planner.fake/otp"
    assert run.steps[2].reason == run.failure.reason
    assert rig.working(failed.id) == ["routes"]
    assert set(rig.artifacts.links_of(version)) == {StepName.AREA, StepName.HUBS}
    assert len(rig.rows("artifacts")) == 2

    rig.settings.set_pricing_model(None)
    rig.preparation.steps.clear()
    resumed = rig.build.execute(version)
    rig.process.execute()

    assert resumed.id != failed.id
    assert [item.state for item in rig.run_of(resumed.id).steps] == [
        StepState.KEPT,
        StepState.KEPT,
        StepState.DONE,
        StepState.DONE,
    ]
    assert rig.preparation.steps == [StepName.ROUTES, StepName.TRAVELLERS_AND_BIKES]
    assert rig.run_of(resumed.id).state is RunState.SUCCEEDED
    version_row = rig.instances.get_version(version)
    assert version_row is not None
    assert version_row.sealed_at == T0


def test_the_seal_and_the_run_are_one_transaction(rig: Rig) -> None:
    version = rig.draft()
    builds = PostgresBuilds(rig.engine)
    steps = make_run("broken", subject_id=version).steps
    broken = make_run("broken", subject_id=version, steps=(steps[0], steps[0]))

    with pytest.raises(IntegrityError):
        builds.queue_build(broken, later(1))

    stored = rig.instances.get_version(version)
    assert stored is not None
    assert (stored.status, stored.sealed_at) == ("draft", None)
    assert rig.rows("runs") == []


def test_two_posts_at_once_queue_one_run_and_refuse_the_other_as_run_active(rig: Rig) -> None:
    version = rig.draft()
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def post() -> None:
        barrier.wait()
        try:
            outcomes.append(rig.build.execute(version))
        except RunActive as refusal:
            outcomes.append(refusal)

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)

    assert sorted(type(item).__name__ for item in outcomes) == ["Run", "RunActive"]
    assert len(rig.rows("runs")) == 1
    refusal = next(item for item in outcomes if isinstance(item, RunActive))
    queued = next(item for item in outcomes if isinstance(item, Run))
    assert refusal.run_id == queued.id


def wait_until(condition: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    pytest.fail(f"Timed out waiting for {what}.")


def test_the_link_of_a_step_is_readable_while_the_next_step_is_held(rig: Rig) -> None:
    version = rig.draft()
    rig.settings.set_pricing_model({"hold_at": "hubs"})
    queued = rig.build.execute(version)
    worker = threading.Thread(target=rig.process.execute)
    worker.start()
    try:
        # The area link is written before the area step ends and the hubs step begins: wait
        # for the held hubs step, not for the link, or the states are read in between.
        wait_until(
            lambda: rig.run_of(queued.id).steps[1].state is StepState.RUNNING, "the held hubs step"
        )

        run = rig.run_of(queued.id)
        assert run.state is RunState.RUNNING
        assert [item.state for item in run.steps][:3] == [
            StepState.DONE,
            StepState.RUNNING,
            StepState.PENDING,
        ]
        assert set(rig.artifacts.links_of(version)) == {StepName.AREA}
    finally:
        rig.settings.release_run(queued.id)
        worker.join(20)

    assert rig.run_of(queued.id).state is RunState.SUCCEEDED
    assert len(rig.artifacts.links_of(version)) == 4


def test_a_paced_routes_step_reports_its_progress_in_the_run(rig: Rig) -> None:
    version = rig.draft()
    rig.settings.set_pricing_model({"routes_pace_ms": 1})
    queued = rig.build.execute(version)

    rig.process.execute()

    routes = rig.run_of(queued.id).steps[2]
    assert (routes.progress_done, routes.progress_total) == (24, 24)
