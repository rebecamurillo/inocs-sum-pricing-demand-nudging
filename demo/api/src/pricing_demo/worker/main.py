"""The worker's composition root and entry point (`pricing-demo-worker`).

Like `bootstrap` and `asgi` for the API, this is the one place that builds the worker's
adapters and injects them. The API and the worker share only PostgreSQL.
"""

import argparse
import logging
import os
import signal
import socket
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
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
)
from pricing_demo.application.ports.bike_station_feed import BikeStationFeed
from pricing_demo.application.ports.bus_shape_matcher import BusShapeMatcher
from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.build_trip_planner_graph import BuildTripPlannerGraph
from pricing_demo.application.use_cases.import_city_data import ImportCityData
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.refresh_bike_stations import RefreshBikeStations
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.city_datasets import DisjointAreas
from pricing_demo.domain.system_status import PROBED_COMPONENTS
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
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher
from pricing_demo.infrastructure.trip_planner.graph_builder import ComposeGraphBuilder
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints
from pricing_demo.infrastructure.trip_planner.graph_folder import LocalGraphFolder
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe
from pricing_demo.infrastructure.waiter import SystemWaiter

logger = logging.getLogger("pricing_demo.worker")


@dataclass(frozen=True)
class BuiltWorker:
    worker: RunWorker
    identity: WorkerIdentity
    engine: Engine


def worker_id_for(settings: Settings, host: str, pid: int) -> str:
    """`PRICING_DEMO_WORKER_ID` when set, otherwise `{host}-{pid}`."""
    return settings.worker_id or f"{host}-{pid}"


def build_probes(settings: Settings, engine: Engine) -> Sequence[ComponentProbe]:
    """The probes of the solver, the package and the trip planner, by adapter set. Only the
    worker builds them: the API process never loads the package."""
    if settings.adapters == "fake":
        fake_settings = PostgresFakeSettings(engine)
        return [FakeProbe(name, fake_settings) for name in PROBED_COMPONENTS]
    return [SolverProbe(), PackageProbe(), OtpProbe(settings.otp_url)]


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
    # No step executor exists yet: story 2-5 registers the first. The `fake` and the `real`
    # adapter set therefore build the same registry for now.
    registry = StepRegistry()
    logger.info("Adapter set: %s; data directory: %s", settings.adapters, settings.data_dir)
    worker = RunWorker(
        identity,
        workers,
        RecoverInterruptedRuns(repository, clock),
        ProcessNextRun(repository, registry, workers, identity, clock, waiter),
        ReportComponents(
            build_probes(settings, engine),
            PostgresComponentReports(engine),
            identity.id,
            clock,
            trip_planner_graph=FileGraphFingerprints(settings.otp_graph_dir),
        ),
        timedelta(seconds=settings.component_report_interval_s),
        clock,
        waiter,
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
    return root


def run_command(args: argparse.Namespace, settings: Settings) -> int:
    """Run one city data command; prints the new id (the manifest's path for `otp-graph`), or
    the reason on stderr (exit 1)."""
    engine = create_db_engine(settings.database_url)
    try:
        if args.command == "import-city-data":
            created = build_import_city_data(settings, engine).execute(args.gtfs, args.osm_dir)
        elif args.command == "otp-graph":
            manifest = build_build_trip_planner_graph(settings, engine).execute(args.dataset)
            print(manifest)
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
