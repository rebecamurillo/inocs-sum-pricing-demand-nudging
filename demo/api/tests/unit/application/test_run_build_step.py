import threading
from dataclasses import replace
from pathlib import Path

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.application.use_cases.run_build_step import NO_KEY_REASON, BuildStepExecutor
from pricing_demo.domain.build_plan import STEP_OUTPUTS, PlannedStep
from pricing_demo.domain.city_instances import InstanceVersion
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import Run, RunStep, StepName
from pricing_demo.infrastructure.fakes.build_sources import InMemoryBuildSources
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


class SpyIngestion:
    """Records what the world looked like when it was called, and can be told to fail."""

    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        self.failing = False
        self.seen: list[tuple[bool, dict[StepName, str]]] = []
        self.inner = rig.builds.ingestion(rig.files)

    def ingest(self, artifact, dataset, upstream):  # type: ignore[no-untyped-def]
        self.seen.append(
            (
                self.rig.builds.artifacts.get(artifact.input_key) is not None,
                dict(self.rig.builds.artifacts.links_of("geneva-3km.v1")),
            )
        )
        if self.failing:
            raise RuntimeError("the database is gone")
        self.rig.builds.read_model.ingest(
            IngestionBatch(artifact.input_key, artifact.step, {"ingested": 1, "failure_pct": 2.5})
        )
        return {"ingested": 1, "failure_pct": 2.5}


def with_spy() -> tuple[Rig, SpyIngestion]:
    rig = Rig()
    spy = SpyIngestion(rig)
    rig.executor = rig.builds.executor(rig.preparation, rig.files, spy)
    return rig, spy


def test_the_outputs_are_ingested_after_they_are_stored_and_before_the_step_is_linked() -> None:
    rig, spy = with_spy()
    run = queued(rig)

    outcome = rig.execute(run, AREA)

    assert spy.seen == [(True, {})]
    assert outcome.counts == {"ingested": 1, "failure_pct": 2.5}
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {AREA: rig.planned(AREA).input_key}


def test_the_artefact_carries_its_run_and_the_counts_the_step_reported() -> None:
    rig = Rig()
    run = queued(rig)
    key = rig.planned(AREA).input_key
    assert key is not None

    rig.execute(run, AREA)

    artifact = rig.builds.artifacts.get(key)
    assert artifact is not None
    assert (artifact.run_id, artifact.reported_counts) == (run.id, {"rows": 1})


def test_a_failed_ingestion_fails_the_step_keeps_the_artefact_and_links_nothing() -> None:
    rig, spy = with_spy()
    run = queued(rig)
    spy.failing = True
    key = rig.planned(AREA).input_key
    assert key is not None

    outcome = rig.execute(run, AREA)

    assert outcome.failure_code == "stage_error"
    assert outcome.failure_reason == "RuntimeError: the database is gone"
    assert rig.builds.artifacts.get(key) is not None
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {}


def test_the_next_execution_of_a_stored_step_only_ingests_it() -> None:
    rig, spy = with_spy()
    run = queued(rig)
    spy.failing = True
    rig.execute(run, AREA)
    requests, spy.failing = len(rig.preparation.requests), False
    calls = len(rig.files.calls)

    outcome = rig.execute(run, AREA)

    assert outcome.failure_code is None
    assert outcome.counts == {"ingested": 1, "failure_pct": 2.5}
    assert len(rig.preparation.requests) == requests
    assert len(rig.files.calls) == calls
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {AREA: rig.planned(AREA).input_key}


def test_a_step_whose_artefact_is_not_ingested_is_not_kept() -> None:
    rig, spy = with_spy()
    run = queued(rig)
    spy.failing = True
    rig.execute(run, AREA)

    assert rig.keep(run, AREA) is False
    assert rig.builds.artifacts.links_of("geneva-3km.v1") == {}

    spy.failing = False
    rig.execute(run, AREA)

    assert rig.keep(run, AREA) is True


def failure(origin: str, query: str) -> RouteFailure:
    return RouteFailure(origin, "H2", query, "no_route", "none", 1)  # type: ignore[arg-type]


def test_the_failed_queries_are_recorded_for_the_routes_step_with_its_period() -> None:
    rig = Rig()
    run = queued(rig)
    rig.preparation.route_failures = [failure("H1", "pt_bike"), failure("H3", "car")]

    rig.execute(run, ROUTES)

    assert rig.builds.route_failures.of_run(run.id) == [
        (failure("H1", "pt_bike"), "geneva-3km.v1.mon-08"),
        (failure("H3", "car"), "geneva-3km.v1.mon-08"),
    ]
    assert len(rig.builds.route_failures.of_step(run.id, 3)) == 2


def test_a_re_executed_routes_step_starts_with_no_failure_of_the_earlier_attempt() -> None:
    rig = Rig()
    run = queued(rig)
    rig.builds.route_failures.add(run.id, 3, "p", failure("H9", "car"), T0)
    rig.builds.route_failures.add(run.id, 1, "p", failure("H8", "car"), T0)
    rig.preparation.outcomes = {ROUTES: StepOutcome.failed("trip_planner_unreachable", "down")}

    rig.execute(run, ROUTES)

    assert rig.builds.route_failures.of_step(run.id, 3) == []
    assert rig.builds.route_failures.of_step(run.id, 1) == [failure("H8", "car")]


def test_the_run_keeps_the_failure_rate_of_a_routes_step_that_is_done() -> None:
    rig, _ = with_spy()
    run = queued(rig)

    rig.execute(run, ROUTES)

    stored = rig.builds.runs.get(run.id)
    assert stored is not None
    assert stored.failure_pct == 2.5


def test_the_run_keeps_the_failure_rate_of_a_routes_step_that_is_kept() -> None:
    rig = Rig()
    first = queued(rig)
    rig.builds.read_model.ingest(
        IngestionBatch(
            rig.planned(ROUTES).input_key or "",
            ROUTES,
            {"failure_pct": 8.0},
        )
    )
    rig.builds.artifacts.add(
        Artifact(
            rig.planned(ROUTES).input_key or "",
            ROUTES,
            {},
            (),
            "p",
            FINGERPRINT,
            T0,
        )
    )

    assert rig.keep(first, ROUTES) is True

    stored = rig.builds.runs.get(first.id)
    assert stored is not None
    assert stored.failure_pct == 8.0


def test_the_log_excerpt_and_peak_memory_of_the_preparation_reach_the_done_outcome() -> None:
    rig = Rig()
    rig.preparation.outcomes = {
        AREA: StepOutcome.done({"rows": 1}, log_excerpt="the log", peak_rss_bytes=2048)
    }
    run = queued(rig)

    outcome = rig.execute(run, AREA)

    assert outcome.failure_code is None
    assert (outcome.log_excerpt, outcome.peak_rss_bytes) == ("the log", 2048)


def test_the_log_excerpt_of_a_failed_preparation_is_returned_as_it_is() -> None:
    rig = Rig()
    rig.preparation.outcomes = {
        AREA: StepOutcome.failed("stage_error", "x", log_excerpt="tb", peak_rss_bytes=1)
    }
    run = queued(rig)

    outcome = rig.execute(run, AREA)

    assert (outcome.failure_code, outcome.log_excerpt, outcome.peak_rss_bytes) == (
        "stage_error",
        "tb",
        1,
    )


def test_a_failed_ingestion_keeps_the_log_excerpt_and_peak_memory_of_the_preparation() -> None:
    rig, spy = with_spy()
    rig.preparation.outcomes = {
        AREA: StepOutcome.done({"rows": 1}, log_excerpt="the log", peak_rss_bytes=2048)
    }
    run = queued(rig)
    spy.failing = True

    outcome = rig.execute(run, AREA)

    assert (outcome.failure_code, outcome.log_excerpt, outcome.peak_rss_bytes) == (
        "stage_error",
        "the log",
        2048,
    )


def test_a_graph_built_from_another_timetable_is_refused_before_anything_runs() -> None:
    rig = Rig()
    rig.builds.sources = InMemoryBuildSources(FINGERPRINT, {"gtfs_sha256": "1" * 64})
    rig.executor = rig.builds.executor(rig.preparation, rig.files)
    run = queued(rig)

    outcome = rig.execute(run, ROUTES)

    assert outcome.failure_code == "timetable_mismatch"
    assert outcome.failure_reason == "the trip planner's timetable is not the city data's timetable"
    assert rig.preparation.requests == []
    assert rig.files.named("working_dir") == []


def test_a_graph_built_from_the_datasets_timetable_runs_the_routes_step() -> None:
    rig = Rig()
    run = queued(rig)

    outcome = rig.execute(run, ROUTES)

    assert outcome.failure_code is None
    assert [request.step for request in rig.preparation.requests] == [ROUTES]
