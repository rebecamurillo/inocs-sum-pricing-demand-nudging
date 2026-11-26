import threading
from dataclasses import replace
from pathlib import Path

from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.application.use_cases.run_build_step import NO_KEY_REASON, BuildStepExecutor
from pricing_demo.domain.build_plan import STEP_OUTPUTS, PlannedStep
from pricing_demo.domain.city_instances import InstanceVersion
from pricing_demo.domain.runs import Run, RunStep, StepName
from tests.support.builds import FINGERPRINT, MemoryBuilds, RecordingFiles, ScriptedPreparation
from tests.support.runs import T0

AREA, HUBS, ROUTES, TRAVELLERS = (
    StepName.AREA,
    StepName.HUBS,
    StepName.ROUTES,
    StepName.TRAVELLERS_AND_BIKES,
)


class Rig:
    def __init__(self) -> None:
        self.builds = MemoryBuilds()
        self.draft = self.builds.add_draft()
        self.files = RecordingFiles()
        self.preparation = ScriptedPreparation()
        self.executor: BuildStepExecutor = self.builds.executor(self.preparation, self.files)

    def version(self, version_id: str = "geneva-3km.v1") -> InstanceVersion:
        version = self.builds.instances.get_version(version_id)
        assert version is not None
        return version

    def planned(self, step: StepName, version_id: str = "geneva-3km.v1") -> PlannedStep:
        return self.builds.planning.plan(self.version(version_id)).step(step)

    def step_of(self, run: Run, step: StepName) -> RunStep:
        stored = self.builds.runs.get(run.id)
        assert stored is not None
        return next(item for item in stored.steps if item.step is step)

    def execute(self, run: Run, step: StepName, stop: threading.Event | None = None) -> StepOutcome:
        return self.executor.execute(run, self.step_of(run, step), stop or threading.Event())

    def keep(self, run: Run, step: StepName) -> bool:
        return self.executor.keep(run, self.step_of(run, step))


def queued(rig: Rig) -> Run:
    return rig.builds.build.execute(rig.draft.id)


def test_a_step_that_succeeds_stores_its_artefact_links_it_and_discards_the_working_directory() -> (
    None
):
    rig = Rig()
    run = queued(rig)
    key = rig.planned(AREA).input_key
    assert key is not None

    outcome = rig.execute(run, AREA)

    assert outcome.counts == {"rows": 1}
    assert outcome.failure_code is None
    working = Path("/work") / run.id / "area"
    assert rig.files.calls == [
        ("working_dir", run.id, AREA),
        ("store", AREA, key, STEP_OUTPUTS[AREA]),
    ]
    assert rig.files.discarded == [working]
    artifact = rig.builds.artifacts.get(key)
    assert artifact is not None
    assert (artifact.step, artifact.path, artifact.package_fingerprint, artifact.created_at) == (
        AREA,
        f"artifacts/area/{key}",
        FINGERPRINT,
        T0,
    )
    assert artifact.inputs == rig.planned(AREA).inputs
    assert [(f.name, f.sha256, f.bytes) for f in artifact.files] == [
        ("stations.json", "sha-stations.json", 10)
    ]
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {AREA: key}


def test_the_step_gets_its_parameters_the_data_set_and_the_period() -> None:
    rig = Rig()
    run = queued(rig)

    rig.execute(run, ROUTES)

    (request,) = rig.preparation.requests
    assert (request.run_id, request.step) == (run.id, ROUTES)
    assert request.working_dir == Path("/work") / run.id / "routes"
    assert request.parameters == rig.version().parameters
    assert request.dataset.id == "geneva-2026-11-26"
    assert request.period.id == "geneva-3km.v1.mon-08"


def test_the_upstream_artefacts_are_copied_in_by_file_name() -> None:
    rig = Rig()
    run = queued(rig)
    keys = {step: rig.planned(step).input_key for step in (AREA, HUBS, ROUTES)}
    working = Path("/work") / run.id

    for step in (AREA, HUBS, ROUTES, TRAVELLERS):
        rig.execute(run, step)

    assert [item[1:] for item in rig.files.named("copy_upstream")] == [
        (AREA, keys[AREA], ("stations.json",), working / "hubs"),
        (HUBS, keys[HUBS], ("hubs.geojson",), working / "routes"),
        (AREA, keys[AREA], ("stations.json",), working / "travellers_and_bikes"),
        (HUBS, keys[HUBS], ("hubs.geojson",), working / "travellers_and_bikes"),
        (ROUTES, keys[ROUTES], ("od_routes.json",), working / "travellers_and_bikes"),
    ]
    assert len(rig.builds.artifacts.links_of("geneva-3km.v1")) == 4


def test_a_step_that_fails_keeps_its_working_directory_and_stores_nothing() -> None:
    rig = Rig()
    run = queued(rig)
    rig.preparation.outcomes = {ROUTES: StepOutcome.failed("trip_planner_unreachable", "down")}
    key = rig.planned(ROUTES).input_key
    assert key is not None

    outcome = rig.execute(run, ROUTES)

    assert (outcome.failure_code, outcome.failure_reason) == ("trip_planner_unreachable", "down")
    assert rig.files.named("store") == []
    assert rig.files.discarded == []
    assert rig.builds.artifacts.get(key) is None
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {}


def test_a_step_that_is_stopped_discards_its_working_directory_and_stores_nothing() -> None:
    rig = Rig()
    run = queued(rig)
    rig.preparation.outcomes = {AREA: StepOutcome.stopped_on_signal()}

    outcome = rig.execute(run, AREA)

    assert outcome.stopped is True
    assert rig.files.named("store") == []
    assert rig.files.discarded == [Path("/work") / run.id / "area"]


def test_a_step_whose_key_has_an_artefact_is_kept_and_linked_and_nothing_runs() -> None:
    rig = Rig()
    first = queued(rig)
    rig.execute(first, AREA)
    rig.builds.instances.create_draft(
        "geneva-3km",
        "geneva-3km.v1",
        rig.version().parameters,
        T0,
        lambda version: replace(
            rig.builds.instances.periods_of("geneva-3km.v1")[0],
            id=f"{version}.mon-08",
            instance_version_id=version,
        ),
    )
    second = rig.builds.build.execute("geneva-3km.v2")
    requests = len(rig.preparation.requests)
    calls = len(rig.files.calls)

    kept = rig.keep(second, AREA)

    assert kept is True
    key = rig.planned(AREA, "geneva-3km.v2").input_key
    assert rig.builds.artifacts.links_of("geneva-3km.v2") == {AREA: key}
    assert (len(rig.preparation.requests), len(rig.files.calls)) == (requests, calls)


def test_a_step_whose_key_has_no_artefact_is_not_kept() -> None:
    rig = Rig()
    run = queued(rig)

    assert rig.keep(run, AREA) is False
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {}


def test_a_step_with_no_key_is_not_kept_and_cannot_run() -> None:
    rig = Rig()
    run = queued(rig)
    # The graph's manifest disappeared after the build was queued.
    rig.builds.sources.manifest = None

    assert rig.keep(run, ROUTES) is False
    outcome = rig.execute(run, ROUTES)

    assert (outcome.failure_code, outcome.failure_reason) == ("stage_error", NO_KEY_REASON)
    assert rig.preparation.requests == []


def test_the_key_the_worker_computes_replaces_the_one_that_was_queued() -> None:
    rig = Rig()
    run = queued(rig)
    rig.builds.runs.update(
        run.id,
        lambda stored: replace(
            stored,
            steps=tuple(replace(item, input_key="stale") for item in stored.steps),
        ),
    )
    key = rig.planned(AREA).input_key

    rig.keep(run, AREA)
    rig.execute(run, HUBS)

    assert rig.step_of(run, AREA).input_key == key
    assert rig.step_of(run, HUBS).input_key == rig.planned(HUBS).input_key
    assert rig.step_of(run, ROUTES).input_key == "stale"


def test_the_progress_of_the_step_is_written_to_the_run() -> None:
    rig = Rig()
    run = queued(rig)
    rig.preparation.report_progress = True

    rig.execute(run, ROUTES)

    step = rig.step_of(run, ROUTES)
    assert (step.progress_done, step.progress_total) == (3, 24)
