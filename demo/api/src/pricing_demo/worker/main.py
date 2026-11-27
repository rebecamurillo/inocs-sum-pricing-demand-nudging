"""The worker's composition root and entry point (`pricing-demo-worker`).

Like `bootstrap` and `asgi` for the API, this is the one place that builds the worker's
adapters and injects them. The API and the worker share only PostgreSQL.
"""

import argparse
import hashlib
import logging
import os
import signal
import socket
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path
from types import FrameType

from sqlalchemy import Engine

from pricing_demo.application.errors import (
    BikeStationFetchFailed,
    GraphBuildFailed,
    GtfsCopyChanged,
    InvalidStreetExtract,
    InvalidTimetable,
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    StreetExtractNotFound,
    UnknownCityDataset,
    VersionNotBuilt,
)
from pricing_demo.application.ingest_step import StepIngestion
from pricing_demo.application.ports.bike_station_feed import BikeStationFeed
from pricing_demo.application.ports.bus_shape_matcher import BusShapeMatcher
from pricing_demo.application.ports.city_preparation import CityPreparation
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.feed_shapes import FeedShapes
from pricing_demo.application.ports.package_fingerprints import PackageFingerprintReader
from pricing_demo.application.ports.pricing_solver import PricingSolver
from pricing_demo.application.ports.step_executor import StepExecutor
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.build_trip_planner_graph import BuildTripPlannerGraph
from pricing_demo.application.use_cases.collect_unreferenced import CollectUnreferenced
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.record_package_fingerprint import (
    RecordPackageFingerprint,
)
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.refresh_bike_stations import RefreshBikeStations
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.application.use_cases.run_build_step import BuildStepExecutor
from pricing_demo.application.use_cases.run_pricing_step import PricingModelStepExecutor
from pricing_demo.application.use_cases.run_simulation_step import TravellerSimulationStepExecutor
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.application.use_cases.show_basemap_bounds import ShowBasemapBounds
from pricing_demo.application.use_cases.verify_build import VerifyBuild
from pricing_demo.domain.build_plan import BUILD_STEPS
from pricing_demo.domain.build_verification import report_lines
from pricing_demo.domain.city_datasets import DisjointAreas
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.system_status import PROBED_COMPONENTS, ComponentName
from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.artifact_store.scratch import LocalScratchBuilds
from pricing_demo.infrastructure.city_data.feed_shapes import GtfsFeedShapes
from pricing_demo.infrastructure.city_data.files import LocalDatasetFiles
from pricing_demo.infrastructure.city_data.gtfs import ZipTimetableReader, ZipTimetableShapes
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from pricing_demo.infrastructure.clock import SystemClock
from pricing_demo.infrastructure.config.settings import (
    DEFAULT_GTFS,
    DEFAULT_OSM_DIR,
    DEMO_DIR,
    Settings,
)
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe, FakeSettingsSource
from pricing_demo.infrastructure.fakes.feed_shapes import FakeFeedShapes
from pricing_demo.infrastructure.fakes.graph_fingerprints import FakeGraphFingerprints
from pricing_demo.infrastructure.fakes.hold import HoldingStepExecutor
from pricing_demo.infrastructure.fakes.package_fingerprints import FakePackageFingerprintReader
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from pricing_demo.infrastructure.fakes.simulation_rule import FakeSimulationRule
from pricing_demo.infrastructure.persistence.artifacts import PostgresArtifacts
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.city_instances import PostgresCityInstances
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.package_fingerprints import (
    PostgresPackageFingerprints,
)
from pricing_demo.infrastructure.persistence.pricing_versions import PostgresPricingVersions
from pricing_demo.infrastructure.persistence.read_model import PostgresReadModel
from pricing_demo.infrastructure.persistence.route_failures import PostgresRouteFailures
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.simulations import PostgresSimulations
from pricing_demo.infrastructure.persistence.solves import PostgresSolves
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.package_fingerprint import (
    PackageFingerprintReader as PackageSourcesReader,
)
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.pricing_solver import PackagePricingSolver
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher
from pricing_demo.infrastructure.trip_planner.graph_builder import ComposeGraphBuilder
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints
from pricing_demo.infrastructure.trip_planner.graph_folder import LocalGraphFolder
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe
from pricing_demo.infrastructure.waiter import SystemWaiter
from pricing_demo.infrastructure.worker_build_sources import WorkerBuildSources

logger = logging.getLogger("pricing_demo.worker")


@dataclass(frozen=True)
class BuiltWorker:
    worker: RunWorker
    identity: WorkerIdentity
    engine: Engine


def worker_id_for(settings: Settings, host: str, pid: int) -> str:
    """`PRICING_DEMO_WORKER_ID` when set, otherwise `{host}-{pid}`."""
    return settings.worker_id or f"{host}-{pid}"


def build_probes(
    settings: Settings, engine: Engine, fake_settings: PostgresFakeSettings | None = None
) -> Sequence[ComponentProbe]:
    """The probes of the solver, the package and the trip planner, by adapter set. Only the
    worker builds them: the API process never loads the package. The fake probes read the
    fake settings the worker's other fakes read."""
    if settings.adapters == "fake":
        shared = fake_settings or PostgresFakeSettings(engine)
        return [FakeProbe(name, shared) for name in PROBED_COMPONENTS]
    return [SolverProbe(), PackageProbe(), OtpProbe(settings.otp_url)]


def build_fingerprint_reader(settings: Settings) -> PackageFingerprintReader:
    """What the worker reports about the pricing package, by adapter set."""
    if settings.adapters == "fake":
        return FakePackageFingerprintReader()
    return PackageSourcesReader(DEMO_DIR.parent / "sum_nsm_dynamic_pricing")


def build_graph_fingerprints(settings: Settings) -> FileGraphFingerprints:
    """The manifest and hash of the trip planner's graph; the fake set falls back to a fixed
    manifest when no graph was built, so the e2e stack's routes key exists."""
    if settings.adapters == "fake":
        return FakeGraphFingerprints(settings.otp_graph_dir)
    return FileGraphFingerprints(settings.otp_graph_dir)


def build_city_preparation(
    settings: Settings, fake_settings: PostgresFakeSettings | None, waiter: Waiter
) -> CityPreparation:
    """The adapter of the four build steps, by adapter set: the build and `verify-build` choose
    it here, so they cannot drift."""
    if fake_settings is not None:
        return FakeCityPreparation(fake_settings, waiter)
    return PackageCityPreparation(
        settings.data_dir,
        StageChild(),
        settings.otp_url,
        settings.otp_workers,
        settings.otp_retries,
        settings.otp_retry_wait_s,
    )


def register_build_steps(
    settings: Settings,
    registry: StepRegistry,
    engine: Engine,
    repository: PostgresRunRepository,
    clock: Clock,
    waiter: Waiter,
    fingerprint: RecordPackageFingerprint,
    graph: FileGraphFingerprints,
    fake_settings: PostgresFakeSettings | None,
) -> None:
    """The executor and keeper of the four build steps. The real city preparation runs steps
    1 to 4 of the package, each in a child process."""
    files = LocalArtifactStore(settings.data_dir)
    read_model = PostgresReadModel(engine)
    route_failures = PostgresRouteFailures(engine)
    preparation = build_city_preparation(settings, fake_settings, waiter)
    # The fake city has one route with a timetable shape and one without.
    feed_shapes: FeedShapes = (
        FakeFeedShapes(frozenset({"1"}))
        if fake_settings is not None
        else GtfsFeedShapes(settings.data_dir)
    )
    executor = BuildStepExecutor(
        preparation,
        files,
        PostgresArtifacts(engine),
        repository,
        PostgresCityInstances(engine),
        PostgresCityDatasets(engine),
        WorkerBuildSources(fingerprint.current, graph),
        clock,
        StepIngestion(files, read_model, route_failures, feed_shapes),
        read_model,
        route_failures,
    )
    for step in BUILD_STEPS:
        registry.register(step, executor, executor)


def simulation_rule_source(fake_settings: FakeSettingsSource | None) -> Callable[[], BalancedScore]:
    """The traveller simulation rule the worker uses, read at each simulation and heartbeat:
    `balanced-score` version 1 in the real set, and in the fake set the version and weights
    the test-control `pricing-model` settings stage."""
    if fake_settings is None:
        return lambda: BalancedScore()
    return FakeSimulationRule(fake_settings).current


def lock_sha256(lock: Path) -> str:
    """The sha256 of the dependency lock file the worker runs from, recorded on every solve."""
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def register_pricing_steps(
    settings: Settings,
    registry: StepRegistry,
    engine: Engine,
    repository: PostgresRunRepository,
    clock: Clock,
    waiter: Waiter,
    identity: WorkerIdentity,
    fingerprint: RecordPackageFingerprint,
    graph: FileGraphFingerprints,
    fake_settings: PostgresFakeSettings | None,
    probes: Sequence[ComponentProbe],
    rule: Callable[[], BalancedScore],
) -> None:
    """The two steps of a pricing run. The pricing model runs the fake solver in the fake set
    and the package's solver in a stage child in the real one; the traveller simulation is the
    demonstrator's own domain code and runs in both sets (`balanced-score`, provisional until
    the model's author states the rule)."""
    files = LocalArtifactStore(settings.data_dir)
    artifacts = PostgresArtifacts(engine)
    solves = PostgresSolves(engine)
    pricing_versions = PostgresPricingVersions(engine)
    (solver_probe,) = [item for item in probes if item.component is ComponentName.SOLVER]
    solver: PricingSolver = (
        FakePricingSolver(fake_settings, waiter)
        if fake_settings is not None
        else PackagePricingSolver(
            StageChild(), version("pricing_demo"), lock_sha256(DEMO_DIR / "api" / "uv.lock")
        )
    )
    pricing_model = PricingModelStepExecutor(
        solver,
        solver_probe,
        PostgresComponentReports(engine),
        identity.id,
        files,
        artifacts,
        solves,
        pricing_versions,
        repository,
        WorkerBuildSources(fingerprint.current, graph),
        clock,
        PostgresReadModel(engine),
    )
    registry.register(StepName.PRICING_MODEL, pricing_model, pricing_model)
    simulation = TravellerSimulationStepExecutor(
        rule,
        pricing_versions,
        artifacts,
        solves,
        PostgresSimulations(engine),
        PostgresReadModel(engine),
        repository,
        clock,
        version("pricing_demo"),
    )
    # The test hold of step 5b exists in the fake set only; the keeper stays the inner executor.
    executor: StepExecutor = (
        simulation
        if fake_settings is None
        else HoldingStepExecutor(simulation, fake_settings, waiter)
    )
    registry.register(StepName.TRAVELLER_SIMULATION, executor, simulation)


def build_worker(settings: Settings) -> BuiltWorker:
    """Choose the adapters and wire them. Nothing here connects to the database."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings.database_url)
    repository = PostgresRunRepository(engine)
    workers = PostgresWorkerRegistry(engine)
    clock = SystemClock()
    waiter = SystemWaiter()
    host, pid = socket.gethostname(), os.getpid()
    identity = WorkerIdentity(worker_id_for(settings, host, pid), host, pid, clock.now())
    fake_settings = PostgresFakeSettings(engine) if settings.adapters == "fake" else None
    fingerprint = RecordPackageFingerprint(
        build_fingerprint_reader(settings), PostgresPackageFingerprints(engine), clock
    )
    graph = build_graph_fingerprints(settings)
    registry = StepRegistry()
    register_build_steps(
        settings, registry, engine, repository, clock, waiter, fingerprint, graph, fake_settings
    )
    probes = build_probes(settings, engine, fake_settings)
    rule = simulation_rule_source(fake_settings)
    register_pricing_steps(
        settings,
        registry,
        engine,
        repository,
        clock,
        waiter,
        identity,
        fingerprint,
        graph,
        fake_settings,
        probes,
        rule,
    )
    logger.info("Adapter set: %s; data directory: %s", settings.adapters, settings.data_dir)
    worker = RunWorker(
        identity,
        workers,
        RecoverInterruptedRuns(repository, clock),
        ProcessNextRun(repository, registry, workers, identity, clock, waiter),
        ReportComponents(
            probes,
            PostgresComponentReports(engine),
            identity.id,
            clock,
            trip_planner_graph=graph,
        ),
        timedelta(seconds=settings.component_report_interval_s),
        clock,
        waiter,
        fingerprint,
        collect=CollectUnreferenced(
            PostgresArtifacts(engine),
            LocalArtifactStore(settings.data_dir),
            repository,
            PostgresSimulations(engine),
        ),
        simulation_rule=lambda: SimulationRule.of(rule()).record(),
    )
    return BuiltWorker(worker, identity, engine)


def run_loop() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    built = build_worker(Settings())
    stop = threading.Event()

    def request_stop(signum: int, _: FrameType | None) -> None:
        logger.info("Signal %s: stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("Worker %s starting (pid %s)", built.identity.id, built.identity.pid)
    try:
        built.worker.start()
        built.worker.run(stop)
    finally:
        built.engine.dispose()
        logger.info("Worker %s stopped", built.identity.id)


COMMAND_ERRORS = (
    BikeStationFetchFailed,
    DisjointAreas,
    GraphBuildFailed,
    GtfsCopyChanged,
    InvalidStreetExtract,
    InvalidTimetable,
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    StreetExtractNotFound,
    UnknownCityDataset,
)


def build_bike_station_feed(settings: Settings) -> BikeStationFeed:
    """The one adapter that fetches the bike-station feed, by adapter set."""
    if settings.adapters == "fake":
        return FixtureBikeStationFeed()
    return PackageBikeStationFeed()


def build_bus_shape_matcher(settings: Settings) -> BusShapeMatcher:
    """The adapter that draws the bus legs on the streets, by adapter set."""
    if settings.adapters == "fake":
        return FakeBusShapeMatcher()
    return DockerPfaedleMatcher(settings.shape_tool_image)


def build_import_city_data(settings: Settings, engine: Engine) -> ImportCityData:
    return ImportCityData(
        PostgresCityDatasets(engine),
        ZipTimetableReader(),
        PbfStreetExtract(),
        LocalDatasetFiles(settings.data_dir),
        build_bike_station_feed(settings),
        build_bus_shape_matcher(settings),
        ZipTimetableShapes(),
        SystemClock(),
    )


def build_refresh_bike_stations(settings: Settings, engine: Engine) -> RefreshBikeStations:
    return RefreshBikeStations(
        PostgresCityDatasets(engine),
        LocalDatasetFiles(settings.data_dir),
        build_bike_station_feed(settings),
        SystemClock(),
    )


def build_build_trip_planner_graph(settings: Settings, engine: Engine) -> BuildTripPlannerGraph:
    """The graph build is the maintainer's command: both adapter sets run the real Compose build."""
    return BuildTripPlannerGraph(
        PostgresCityDatasets(engine),
        LocalDatasetFiles(settings.data_dir),
        LocalGraphFolder(settings.otp_graph_dir),
        ComposeGraphBuilder(DEMO_DIR, graph_dir=settings.otp_graph_dir),
    )


def build_verify_build(settings: Settings, engine: Engine) -> VerifyBuild:
    """Reads the stored build; the rebuild goes through the same preparation as a build."""
    fake_settings = PostgresFakeSettings(engine) if settings.adapters == "fake" else None
    return VerifyBuild(
        PostgresCityInstances(engine),
        PostgresCityDatasets(engine),
        PostgresArtifacts(engine),
        LocalArtifactStore(settings.data_dir),
        PostgresRouteFailures(engine),
        build_city_preparation(settings, fake_settings, SystemWaiter()),
        LocalScratchBuilds(settings.data_dir),
    )


def build_show_basemap_bounds(engine: Engine) -> ShowBasemapBounds:
    return ShowBasemapBounds(PostgresCityDatasets(engine))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pricing-demo-worker")
    commands = root.add_subparsers(dest="command")
    importing = commands.add_parser(
        "import-city-data", help="import the timetable and a first bike-station snapshot"
    )
    importing.add_argument("--gtfs", type=Path, default=DEFAULT_GTFS)
    importing.add_argument("--osm-dir", type=Path, default=DEFAULT_OSM_DIR)
    commands.add_parser(
        "refresh-bike-stations", help="a new data set with the latest timetable and new stations"
    )
    graph = commands.add_parser(
        "otp-graph", help="build OpenTripPlanner's graph from a city data set"
    )
    graph.add_argument("--dataset", default=None, help="default: the most recent data set")
    bounds = commands.add_parser(
        "basemap-bounds",
        help="print a data set's id and its available area's bounding box (west,south,east,north)",
    )
    bounds.add_argument("--dataset", default=None, help="default: the most recent data set")
    verifying = commands.add_parser(
        "verify-build",
        help="rebuild an instance version's steps 1-4 with reuse off and compare them "
        "with the stored build",
    )
    verifying.add_argument("version", help="the instance version, e.g. geneva-3km.v1")
    return root


def run_verify_build(args: argparse.Namespace, settings: Settings, engine: Engine) -> int:
    """Print one line per step and the verdict: exit 0 when the builds match, 1 when they
    differ, 2 when the version cannot be verified or a rebuild step fails (reason on stderr)."""
    stop = threading.Event()
    # SIGINT and SIGTERM stop the rebuild: a stopped rebuild is a failure and leaves no folder.
    signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())
    signal.signal(signal.SIGINT, lambda signum, frame: stop.set())
    try:
        result = build_verify_build(settings, engine).execute(args.version, stop)
    except (InstanceVersionNotFound, VersionNotBuilt) as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:
        # Exit 1 means "the builds differ": any other error (a stored file missing or malformed,
        # the database unreachable) is a run that could not verify, exit 2.
        print(f"verify-build {args.version}: {error!r}", file=sys.stderr)
        return 2
    if result.failure is not None:
        step, code, reason = result.failure
        print(
            f"verify-build {args.version}: step {step.value} failed ({code}): {reason}",
            file=sys.stderr,
        )
        return 2
    assert result.comparison is not None
    for line in report_lines(args.version, result.comparison):
        print(line)
    return 0 if result.comparison.matches else 1


def run_command(args: argparse.Namespace, settings: Settings) -> int:
    """Run one city data command; prints the new id (the manifest's path for `otp-graph`, the id
    and the box for `basemap-bounds`, the report of `verify-build`), or the reason on stderr
    (exit 1; exit 2 for `verify-build`, whose exit 1 is a build that differs)."""
    engine = create_db_engine(settings.database_url)
    try:
        if args.command == "import-city-data":
            created = build_import_city_data(settings, engine).execute(args.gtfs, args.osm_dir)
        elif args.command == "otp-graph":
            manifest = build_build_trip_planner_graph(settings, engine).execute(args.dataset)
            print(manifest)
            return 0
        elif args.command == "verify-build":
            return run_verify_build(args, settings, engine)
        elif args.command == "basemap-bounds":
            shown = build_show_basemap_bounds(engine).execute(args.dataset)
            area = shown.area
            print(f"{shown.dataset_id} {area.min_lon},{area.min_lat},{area.max_lon},{area.max_lat}")
            return 0
        else:
            created = build_refresh_bike_stations(settings, engine).execute()
    except COMMAND_ERRORS as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(created.id)
    return 0


def main(argv: Sequence[str] | None = None) -> int | None:
    args = parser().parse_args(argv)
    if args.command is None:
        run_loop()
        return None
    return run_command(args, Settings())


if __name__ == "__main__":
    sys.exit(main())
