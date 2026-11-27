"""A build rig: the in-memory adapters wired the way the use cases of a build need them."""

import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.ingest_step import StepIngestion
from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifact, StoredFile
from pricing_demo.application.ports.city_preparation import (
    PreparationRequest,
    Progress,
    RouteFailed,
    ignore_route_failure,
)
from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.use_cases.build_instance_version import BuildInstanceVersion
from pricing_demo.application.use_cases.run_build_step import BuildStepExecutor
from pricing_demo.domain.build_plan import STEP_OUTPUTS
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import (
    CityInstance,
    InstanceVersion,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, SystemStatus
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.build_sources import InMemoryBuildSources
from pricing_demo.infrastructure.fakes.builds import InMemoryBuilds
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.feed_shapes import FakeFeedShapes
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.read_model import InMemoryReadModel
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.builds import PostgresBuilds
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from pricing_demo.infrastructure.persistence.route_failures import PostgresRouteFailures
from tests.support.runs import T0

FINGERPRINT = "f" * 64
MANIFEST = {"otp_image": "fake", "gtfs_sha256": "0" * 64}


def all_available() -> SystemStatus:
    return SystemStatus.of([ComponentStatus.ready(name) for name in ComponentName])


def unavailable(*names: ComponentName) -> SystemStatus:
    return SystemStatus.of(
        [
            ComponentStatus.unavailable(name, f"{name.value} is down.")
            if name in names
            else ComponentStatus.ready(name)
            for name in ComponentName
        ]
    )


DATASET_ID = "geneva-2026-11-26"
SLUG = "geneva-3km"


class SequentialIds:
    """Run identifiers `run-1`, `run-2`, ..."""

    def __init__(self) -> None:
        self._count = 0

    def new_run_id(self) -> str:
        self._count += 1
        return f"run-{self._count}"


class Status:
    """The system status a test sets; `planning` reads it at each call."""

    def __init__(self) -> None:
        self.value = all_available()

    def __call__(self) -> SystemStatus:
        return self.value


class MemoryBuilds:
    """The adapters of a build, in memory, with a clock and a fingerprint and a manifest."""

    def __init__(
        self,
        *,
        fingerprint: str | None = FINGERPRINT,
        manifest: bool = True,
        now: datetime = T0,
    ) -> None:
        self.clock = FixedClock(now)
        self.datasets = InMemoryCityDatasets()
        self.instances = InMemoryCityInstances()
        self.artifacts = InMemoryArtifacts()
        self.read_model = InMemoryReadModel()
        self.route_failures = InMemoryRouteFailures()
        self.feed_shapes = FakeFeedShapes(frozenset({"1"}))
        self.built = BuiltCounts(self.artifacts, self.read_model, self.route_failures)
        self.runs = InMemoryRunRepository()
        self.builds = InMemoryBuilds(self.runs, self.instances, self.artifacts, self.route_failures)
        self.sources = InMemoryBuildSources(fingerprint, MANIFEST if manifest else None)
        self.status = Status()
        self.ids = SequentialIds()
        self.waiter = FakeWaiter(self.clock)
        self.planning = BuildPlanning(
            self.instances, self.datasets, self.artifacts, self.sources, self.builds, self.status
        )
        self.build = BuildInstanceVersion(
            self.instances, self.datasets, self.builds, self.planning, self.ids, self.clock
        )

    def add_draft(self, *changes: tuple[str, float]) -> InstanceVersion:
        """The data set, the instance `geneva-3km` and its first draft, valid unless the
        changes say otherwise (the package defaults tie two distances, so one is moved)."""
        dataset = fake_city_dataset(DATASET_ID, T0)
        if self.datasets.get(DATASET_ID) is None:
            self.datasets.add(dataset)
        parameters = parameters_from_defaults(FAKE_FINGERPRINT.defaults, dataset.preset)
        parameters = replace(parameters, min_od_distance_m=900.0)
        parameters = parameters.replacing(dict(changes))
        draft = InstanceVersion(f"{SLUG}.v1", SLUG, 1, None, "draft", parameters, T0)
        self.instances.create(
            CityInstance(SLUG, "Geneva 3 km", DATASET_ID, 2, T0),
            draft,
            first_period(draft.id, dataset),
        )
        return draft

    def executor(
        self, preparation: object, files: ArtifactFiles, ingestion: object | None = None
    ) -> BuildStepExecutor:
        """`ingestion` defaults to one that stores the reported counts and reads no file, for
        the tests whose preparation writes none."""
        return BuildStepExecutor(
            preparation,  # type: ignore[arg-type]
            files,
            self.artifacts,
            self.runs,
            self.instances,
            self.datasets,
            self.sources,
            self.clock,
            ingestion or CountsOnlyIngestion(self.read_model),  # type: ignore[arg-type]
            self.read_model,
            self.route_failures,
        )

    def ingestion(self, files: ArtifactFiles) -> StepIngestion:
        """The real ingestion, reading the files `files` serves."""
        return StepIngestion(files, self.read_model, self.route_failures, self.feed_shapes)


def postgres_planning(
    engine: Engine, sources: object, status: Callable[[], SystemStatus] = all_available
) -> BuildPlanning:
    return BuildPlanning(
        PostgresCityInstances(engine),
        PostgresCityDatasets(engine),
        PostgresArtifacts(engine),
        sources,  # type: ignore[arg-type]
        PostgresBuilds(engine),
        status,
    )


def build_fake_city(
    rig: MemoryBuilds, folder: Path, route_failures: Sequence[Mapping[str, str]] = ()
) -> str:
    """Queue the build of the rig's draft and run its four steps with the fake preparation, the
    real ingestion and a local artefact store; returns the run id."""
    settings = InMemoryFakeSettings()
    settings.set_pricing_model({"route_failures": list(route_failures)})
    files = LocalArtifactStore(folder)
    executor = rig.executor(FakeCityPreparation(settings, rig.waiter), files, rig.ingestion(files))
    run = rig.build.execute(f"{SLUG}.v1")
    for step in STEP_OUTPUTS:
        stored = rig.runs.get(run.id)
        assert stored is not None
        item = next(candidate for candidate in stored.steps if candidate.step is step)
        if not executor.keep(stored, item):
            outcome = executor.execute(stored, item, threading.Event())
            assert outcome.failure_code is None, outcome.failure_reason
    return run.id


def postgres_built(engine: Engine) -> BuiltCounts:
    return BuiltCounts(
        PostgresArtifacts(engine), PostgresReadModel(engine), PostgresRouteFailures(engine)
    )


@dataclass
class RecordingFiles:
    """An `ArtifactFiles` that touches no disk: it records what it was asked."""

    calls: list[tuple[Any, ...]] = field(default_factory=list)
    discarded: list[Path] = field(default_factory=list)
    contents: dict[tuple[str, str], Any] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    kept_runs: set[str] | None = None
    failing: set[str] = field(default_factory=set)

    def remove_artifact(self, path: str) -> None:
        if path in self.failing:
            raise OSError(path)
        self.removed.append(path)

    def remove_working_dirs_except(self, run_ids: Collection[str]) -> None:
        self.kept_runs = set(run_ids)

    def working_dir(self, run_id: str, step: StepName) -> Path:
        self.calls.append(("working_dir", run_id, step))
        return Path("/work") / run_id / step.value

    def copy_upstream(self, step: StepName, key: str, names: Sequence[str], into: Path) -> None:
        self.calls.append(("copy_upstream", step, key, tuple(names), into))

    def store(
        self, step: StepName, key: str, working_dir: Path, names: Sequence[str]
    ) -> tuple[Path, tuple[StoredFile, ...]]:
        self.calls.append(("store", step, key, tuple(names)))
        return Path("artifacts") / step.value / key, tuple(
            StoredFile(name, f"sha-{name}", 10) for name in names
        )

    def discard(self, working_dir: Path) -> None:
        self.discarded.append(working_dir)

    def read_json(self, path: str, name: str) -> Any:
        self.calls.append(("read_json", path, name))
        return self.contents[(path, name)]

    def named(self, call: str) -> list[tuple[Any, ...]]:
        return [item for item in self.calls if item[0] == call]


@dataclass
class ScriptedPreparation:
    """A `CityPreparation` that answers each step with the outcome it was given."""

    outcomes: Mapping[StepName, StepOutcome] = field(default_factory=dict)
    requests: list[PreparationRequest] = field(default_factory=list)
    progress_calls: list[tuple[int, int]] = field(default_factory=list)
    report_progress: bool = False
    # The failed queries the routes step reports.
    route_failures: Sequence[RouteFailure] = ()

    def prepare(
        self,
        request: PreparationRequest,
        progress: Progress,
        stop: StopSignal,
        route_failed: RouteFailed = ignore_route_failure,
    ) -> StepOutcome:
        self.requests.append(request)
        if self.report_progress:
            progress(3, 24)
        if request.step is StepName.ROUTES:
            for failure in self.route_failures:
                route_failed(failure)
        return self.outcomes.get(request.step, StepOutcome.done({"rows": 1}))


def outputs_of(step: StepName) -> tuple[str, ...]:
    return STEP_OUTPUTS[step]


class CountsOnlyIngestion:
    """An ingestion that reads no file: it marks the artefact ingested with the counts the step
    reported (a routes step also has the rate the run keeps)."""

    def __init__(self, read_model: InMemoryReadModel) -> None:
        self._read_model = read_model

    def ingest(
        self, artifact: Artifact, dataset: CityDataset, upstream: Mapping[StepName, Artifact]
    ) -> Mapping[str, Any]:
        counts = dict(artifact.reported_counts)
        if artifact.step is StepName.ROUTES:
            counts.setdefault("failure_pct", 0.0)
        self._read_model.ingest(IngestionBatch(artifact.input_key, artifact.step, counts))
        return counts
